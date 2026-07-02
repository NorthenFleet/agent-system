"""Adapters for the external knowledge system stack.

The dashboard keeps its existing Obsidian graph index as the reliable local
fallback, while LightRAG and KAG are integrated as optional services.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from knowledge_manager import knowledge_manager


DEFAULT_LIGHTRAG_URL = "http://127.0.0.1:9621"
DEFAULT_LIGHTRAG_DIR = "/Users/apple/WorkSpace/knowledge-stack/lightrag"
DEFAULT_KAG_DIR = "/Users/apple/WorkSpace/knowledge-stack/KAG"
DEFAULT_KNOWLEDGE_VAULT = "/Users/apple/工作桌面/knowledge"
DEFAULT_OLLAMA_HOST = "http://192.168.1.5:11434"
DEFAULT_LIGHTRAG_LLM_MODEL = "qwen3.6:35b"
DEFAULT_LIGHTRAG_EMBEDDING_MODEL = "nomic-embed-text:latest"
DEFAULT_LIGHTRAG_EMBEDDING_DIM = "768"
IGNORED_VAULT_DIRS = {
    ".git",
    ".obsidian",
    ".venv",
    ".venv-ppt",
    "node_modules",
    "__pycache__",
    "tmp",
    "media",
    "assets",
}


class KnowledgeStackManager:
    def __init__(self) -> None:
        self.lightrag_url = os.getenv("LIGHTRAG_URL", DEFAULT_LIGHTRAG_URL).rstrip("/")
        self.lightrag_dir = Path(os.getenv("LIGHTRAG_DIR", DEFAULT_LIGHTRAG_DIR))
        self.kag_dir = Path(os.getenv("KAG_DIR", DEFAULT_KAG_DIR))

    def status(self) -> dict[str, Any]:
        local_stats = knowledge_manager.get_stats()
        lightrag = self._lightrag_status()
        kag = self._kag_status()
        return {
            "local": {
                "name": "Obsidian graph-index",
                "available": bool(local_stats.get("available")),
                "nodes": local_stats.get("nodes", 0),
                "edges": local_stats.get("edges", 0),
                "entity_types": local_stats.get("entity_types", {}),
                "index_path": local_stats.get("index_path", ""),
                "vault_path": local_stats.get("vault_path", ""),
                "build_time": local_stats.get("build_time"),
            },
            "lightrag": lightrag,
            "kag": kag,
        }

    def query(self, query: str, engine: str = "auto", mode: str = "mix", limit: int = 10) -> dict[str, Any]:
        clean_query = (query or "").strip()
        if not clean_query:
            return {"engine": "none", "query": query, "results": [], "answer": ""}

        if engine in {"auto", "lightrag"} and self._lightrag_status().get("running"):
            try:
                return self._lightrag_query(clean_query, mode=mode)
            except Exception as exc:  # Keep local search available when model backend is missing.
                if engine == "lightrag":
                    return {"engine": "lightrag", "query": clean_query, "error": str(exc), "results": []}

        local = knowledge_manager.search(clean_query, limit=limit)
        return {
            "engine": "local",
            "query": clean_query,
            "answer": "",
            "results": local.get("nodes", []),
            "total": local.get("total", 0),
        }

    def graph(self, source: str = "local", limit_edges: int = 260, node_type: str | None = None) -> dict[str, Any]:
        if source == "lightrag" and self._lightrag_status().get("running"):
            try:
                return {"source": "lightrag", **self._get_json("/graphs")}
            except Exception as exc:
                return {"source": "lightrag", "error": str(exc), "nodes": [], "relations": []}
        return {"source": "local", **knowledge_manager.graph(limit_edges=limit_edges, node_type=node_type)}

    def trigger_lightrag_scan(self) -> dict[str, Any]:
        return self._post_json("/documents/scan", {})

    def lightrag_documents(self) -> dict[str, Any]:
        return self._get_json("/documents", timeout=5)

    def lightrag_sources(self) -> dict[str, Any]:
        vault = self._vault_path()
        sources: list[dict[str, Any]] = []
        if not vault.exists():
            return {"vault_path": str(vault), "sources": sources}

        for child in sorted(vault.iterdir(), key=lambda path: path.name.lower()):
            if not child.is_dir() or child.name.startswith(".") or child.name in IGNORED_VAULT_DIRS:
                continue
            files = self._markdown_files(child, limit=5000)
            if not files:
                continue
            sources.append({
                "name": child.name,
                "path": child.name,
                "file_count": len(files),
                "size_bytes": sum(file.stat().st_size for file in files if file.exists()),
                "priority": self._source_priority(child.name),
            })
        sources.sort(key=lambda item: (item["priority"], item["path"]))
        return {"vault_path": str(vault), "sources": sources}

    def index_lightrag_batch(
        self,
        source_path: str,
        limit: int = 3,
        max_chars_per_file: int = 12000,
    ) -> dict[str, Any]:
        if not self._lightrag_status().get("running"):
            return {"status": "error", "message": "LightRAG is not running", "submitted": []}

        limit = max(1, min(int(limit or 3), 10))
        max_chars_per_file = max(1000, min(int(max_chars_per_file or 12000), 60000))
        source = self._resolve_vault_source(source_path)
        files = self._markdown_files(source, limit=limit)

        submitted = []
        errors = []
        for file_path in files:
            rel_path = file_path.relative_to(self._vault_path()).as_posix()
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue
                payload = {
                    "text": f"# {file_path.stem}\n\nSource: {rel_path}\n\n{content[:max_chars_per_file]}",
                    "file_source": rel_path,
                }
                response = self._post_json("/documents/text", payload, timeout=30)
                submitted.append({
                    "path": rel_path,
                    "chars": min(len(content), max_chars_per_file),
                    "track_id": response.get("track_id"),
                    "status": response.get("status"),
                })
            except Exception as exc:
                errors.append({"path": rel_path, "error": str(exc)})

        return {
            "status": "submitted" if submitted else "empty",
            "source": source.relative_to(self._vault_path()).as_posix(),
            "limit": limit,
            "submitted": submitted,
            "errors": errors,
        }

    def _lightrag_status(self) -> dict[str, Any]:
        installed = (self.lightrag_dir / ".venv/bin/lightrag-server").exists()
        runtime_config = self._lightrag_runtime_config()
        ollama = self._ollama_status(runtime_config["ollama_host"], runtime_config)
        status = {
            "name": "LightRAG",
            "installed": installed,
            "running": False,
            "ready": False,
            "url": self.lightrag_url,
            "working_dir": str(self.lightrag_dir),
            "model_backend": "ollama",
            "ollama_host": runtime_config["ollama_host"],
            "llm_model": runtime_config["llm_model"],
            "embedding_model": runtime_config["embedding_model"],
            "embedding_dim": runtime_config["embedding_dim"],
            "ollama": ollama,
            "message": "not installed" if not installed else "installed",
        }
        try:
            openapi = self._get_json("/openapi.json", timeout=2)
            if ollama["available"] and ollama["has_llm"] and ollama["has_embedding"]:
                message = (
                    "running; Ollama backend configured: "
                    f"{runtime_config['llm_model']} + "
                    f"{runtime_config['embedding_model']} ({runtime_config['embedding_dim']}d)"
                )
            elif ollama["available"]:
                message = (
                    "running; Ollama reachable but required models are missing: "
                    f"{runtime_config['llm_model']} / {runtime_config['embedding_model']}"
                )
            else:
                message = f"running; Ollama unreachable at {runtime_config['ollama_host']}"
            status.update({
                "running": True,
                "ready": True,
                "version": (openapi.get("info") or {}).get("version", ""),
                "message": message,
            })
        except Exception as exc:
            if installed:
                status["message"] = f"installed but not reachable: {exc}"
        return status

    def _lightrag_runtime_config(self) -> dict[str, str]:
        config = {
            "ollama_host": os.getenv("OLLAMA_HOST") or os.getenv("LLM_BINDING_HOST") or DEFAULT_OLLAMA_HOST,
            "llm_model": os.getenv("LIGHTRAG_LLM_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_LIGHTRAG_LLM_MODEL,
            "embedding_model": (
                os.getenv("LIGHTRAG_EMBEDDING_MODEL")
                or os.getenv("EMBEDDING_MODEL")
                or DEFAULT_LIGHTRAG_EMBEDDING_MODEL
            ),
            "embedding_dim": os.getenv("EMBEDDING_DIM") or DEFAULT_LIGHTRAG_EMBEDDING_DIM,
        }
        script = self.lightrag_dir / "start_lightrag.sh"
        if script.exists():
            for line in script.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line.startswith("export ") or "=" not in line:
                    continue
                key, value = line[len("export "):].split("=", 1)
                value = self._expand_shell_default(value.strip().strip('"').strip("'"))
                if key in {"LLM_BINDING_HOST", "EMBEDDING_BINDING_HOST", "OLLAMA_HOST"}:
                    config["ollama_host"] = value.rstrip("/")
                elif key == "LLM_MODEL":
                    config["llm_model"] = value
                elif key == "EMBEDDING_MODEL":
                    config["embedding_model"] = value
                elif key == "EMBEDDING_DIM":
                    config["embedding_dim"] = value
        return config

    def _expand_shell_default(self, value: str) -> str:
        if value.startswith("${") and value.endswith("}") and ":-" in value:
            return value[2:-1].split(":-", 1)[1]
        return value

    def _ollama_status(self, host: str, runtime_config: dict[str, str]) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [model.get("name") for model in payload.get("models", []) if model.get("name")]
            return {
                "available": True,
                "host": host,
                "models": models,
                "has_llm": runtime_config["llm_model"] in models,
                "has_embedding": runtime_config["embedding_model"] in models,
            }
        except Exception as exc:
            return {
                "available": False,
                "host": host,
                "models": [],
                "has_llm": False,
                "has_embedding": False,
                "error": str(exc),
            }

    def _kag_status(self) -> dict[str, Any]:
        installed = (self.kag_dir / ".git").exists()
        docker_available = self._command_available("docker")
        commit = ""
        if installed:
            try:
                commit = subprocess.check_output(
                    ["git", "-C", str(self.kag_dir), "rev-parse", "--short", "HEAD"],
                    text=True,
                    timeout=3,
                ).strip()
            except Exception:
                commit = ""
        return {
            "name": "OpenSPG KAG",
            "installed": installed,
            "running": False,
            "ready": False,
            "path": str(self.kag_dir),
            "commit": commit,
            "requires": ["Docker Compose", "OpenSPG service", "Python 3.10 env", "LLM credentials"],
            "docker_available": docker_available,
            "message": (
                "source installed; Docker/OpenSPG runtime not available on this mini"
                if installed and not docker_available else
                "source installed; runtime configuration pending" if installed else "not installed"
            ),
        }

    def _vault_path(self) -> Path:
        local_stats = knowledge_manager.get_stats()
        return Path(local_stats.get("vault_path") or os.getenv("KNOWLEDGE_VAULT_PATH", DEFAULT_KNOWLEDGE_VAULT))

    def _resolve_vault_source(self, source_path: str) -> Path:
        vault = self._vault_path().resolve()
        clean = (source_path or "").strip().strip("/")
        source = vault if not clean else (vault / clean).resolve()
        if source != vault and vault not in source.parents:
            raise ValueError("source_path must be inside the knowledge vault")
        if not source.exists() or not source.is_dir():
            raise ValueError(f"source_path not found: {source_path}")
        return source

    def _markdown_files(self, root: Path, limit: int = 5000) -> list[Path]:
        files: list[Path] = []
        for path in root.rglob("*.md"):
            if len(files) >= limit:
                break
            if any(part.startswith(".") or part in IGNORED_VAULT_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file():
                files.append(path)
        return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)

    def _source_priority(self, name: str) -> int:
        if name.startswith("06-项目库") or name.startswith("07-规范库") or name.startswith("16-智能体"):
            return 0
        if name.startswith("03-概念库") or name.startswith("05-模型库") or name.startswith("13-索引库"):
            return 1
        return 2

    def _lightrag_query(self, query: str, mode: str = "mix") -> dict[str, Any]:
        payload = {
            "query": query,
            "mode": mode,
            "only_need_context": True,
            "include_references": True,
            "include_chunk_content": False,
        }
        data = self._post_json("/query/data", payload, timeout=60)
        return {"engine": "lightrag", "query": query, "data": data, "results": []}

    def _get_json(self, path: str, timeout: int = 5) -> dict[str, Any]:
        with urllib.request.urlopen(self.lightrag_url + path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
        req = urllib.request.Request(
            self.lightrag_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _command_available(self, name: str) -> bool:
        try:
            subprocess.check_call(["which", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False


knowledge_stack_manager = KnowledgeStackManager()
