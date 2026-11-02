"""PostgreSQL authority for reviewed knowledge; no import-time connections/writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import stat
import tempfile
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa

from models import knowledge_schema_v1 as t
from services.knowledge.contracts import Proposal


def now():
    return datetime.now(timezone.utc)


def ident(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(data).hexdigest()


class KnowledgeError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


def normalized(text):
    return unicodedata.normalize("NFKC", text).casefold().strip()


def row(conn, table, object_id):
    return conn.execute(sa.select(table).where(table.c.id == object_id)).mappings().first()


class KnowledgeService:
    def __init__(self, engine, source_root, *, project_check=None):
        if engine.dialect.name != "postgresql":
            raise KnowledgeError("authority_unavailable", "知识权威写入需要 PostgreSQL", 503)
        self.engine = engine
        configured_root = Path(source_root).expanduser()
        if not configured_root.is_absolute() or configured_root.is_symlink():
            raise KnowledgeError("unsafe_storage", "需要专用的绝对来源目录，不能使用符号链接", 503)
        self.root = configured_root.resolve()
        self.project_check = project_check or (lambda actor, project: False)

    def space(self, conn, actor, space_id, *, lock=False):
        stmt = sa.select(t.spaces).where(t.spaces.c.id == space_id,
                                        t.spaces.c.owner_user_id == actor,
                                        t.spaces.c.status == "active")
        if lock:
            stmt = stmt.with_for_update()
        result = conn.execute(stmt).mappings().first()
        if not result or (result["project_id"] and not self.project_check(actor, result["project_id"])):
            raise KnowledgeError("not_found", "知识空间不存在或不可访问", 404)
        return dict(result)

    def object_space(self, conn, actor, table, object_id, *, lock=False):
        obj = row(conn, table, object_id)
        if not obj:
            raise KnowledgeError("not_found", "对象不存在或不可访问", 404)
        space = self.space(conn, actor, obj["space_id"], lock=lock)
        # Re-read after acquiring the common space lock.
        return dict(row(conn, table, object_id)), space

    def audit(self, conn, actor, space_id, action, ref, details=None):
        conn.execute(t.audit.insert().values(id=ident("ka"), space_id=space_id,
            actor=actor, action=action, object_ref=ref, details=details or {}, created_at=now()))

    def idempotent(self, conn, actor, space_id, operation, key, payload, apply):
        if not key or len(key) > 160:
            raise KnowledgeError("idempotency_key_required", "需要有效的 Idempotency-Key")
        request_hash = digest(payload)
        found = conn.execute(sa.select(t.requests).where(
            t.requests.c.space_id == space_id, t.requests.c.actor == actor,
            t.requests.c.operation == operation, t.requests.c.request_key == key)).mappings().first()
        if found:
            if found["payload_hash"] != request_hash:
                raise KnowledgeError("idempotency_conflict", "相同请求键对应不同内容", 409)
            return found["response"]
        result = apply()
        conn.execute(t.requests.insert().values(id=ident("krq"), space_id=space_id, actor=actor,
            operation=operation, request_key=key, payload_hash=request_hash,
            response=result, created_at=now()))
        return result

    def create_space(self, actor, name, project_id, key):
        if not name.strip() or len(name) > 240:
            raise KnowledgeError("invalid_title", "请填写空间名称")
        if project_id and not self.project_check(actor, project_id):
            raise KnowledgeError("not_found", "项目不存在或不可访问", 404)
        # Serializes retries before the space row exists; scoped by authenticated actor.
        with self.engine.begin() as conn:
            lock_key = int(digest((actor, "create-space", key))[:15], 16)
            conn.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
            sid = "ks-" + digest((actor, key))[:32]
            existing = row(conn, t.spaces, sid)
            if not existing:
                conn.execute(t.spaces.insert().values(id=sid, owner_user_id=actor, name=name,
                    project_id=project_id, policy_revision="kb-policy-v1", status="active",
                    access_epoch=0, sequence=0, created_at=now()))
            return self.idempotent(conn, actor, sid, "space.create", key,
                {"name": name, "project_id": project_id}, lambda: {"id": sid, "name": name,
                    "project_id": project_id})

    def list_spaces(self, actor):
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(sa.select(t.spaces).where(
                t.spaces.c.owner_user_id == actor, t.spaces.c.status == "active")
                .order_by(t.spaces.c.created_at)).mappings()
                if not r["project_id"] or self.project_check(actor, r["project_id"])]

    def _store(self, sid, data):
        checksum = digest(data)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_uid != os.getuid() or stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise KnowledgeError("unsafe_storage", "来源根目录必须为当前用户所有且权限为 0700", 503)
        directory = self.root / sid
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or directory.resolve().parent != self.root:
            raise KnowledgeError("unsafe_storage", "来源目录不安全", 503)
        target = directory / checksum
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if target.is_symlink() or digest(target.read_bytes()) != checksum:
                raise KnowledgeError("source_hash_mismatch", "已存来源哈希不一致", 409)
        else:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        return f"{sid}/{checksum}"

    def read_source_bytes(self, version):
        expected = f"{version['space_id']}/{version['content_sha256']}"
        if version["blob_ref"] != expected:
            raise KnowledgeError("source_hash_mismatch", "来源定位不一致", 409)
        path = self.root / expected
        if path.parent.is_symlink() or path.is_symlink() or path.parent.resolve().parent != self.root:
            raise KnowledgeError("unsafe_storage", "来源路径不安全", 409)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as source:
            data = source.read(5 * 1024 * 1024 + 1)
        if digest(data) != version["content_sha256"]:
            raise KnowledgeError("source_hash_mismatch", "来源内容已变化", 409)
        return data

    def upload(self, actor, sid, name, data, key, *, _conn=None):
        if not data or len(data) > 5 * 1024 * 1024:
            raise KnowledgeError("source_size", "资料必须非空且不超过 5 MiB", 413)
        suffix = Path(name).suffix.lower()
        if suffix not in {".txt", ".md", ".pdf"} or len(name) > 240:
            raise KnowledgeError("unsupported_source", "首版支持 Markdown、TXT 和文本 PDF")
        if suffix == ".pdf" and not data.startswith(b"%PDF-"):
            raise KnowledgeError("invalid_pdf", "文件内容不是 PDF")
        if suffix != ".pdf":
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise KnowledgeError("invalid_encoding", "文本必须为 UTF-8") from exc
            if b"\x00" in data:
                raise KnowledgeError("invalid_text", "资料包含二进制内容")
        checksum = digest(data)
        from contextlib import nullcontext
        with (nullcontext(_conn) if _conn is not None else self.engine.begin()) as conn:
            self.space(conn, actor, sid, lock=True)
            def apply():
                found = conn.execute(sa.select(t.versions).where(t.versions.c.space_id == sid,
                    t.versions.c.content_sha256 == checksum)).mappings().first()
                if found:
                    return {"source_id": found["source_id"], "version_id": found["id"], "duplicate": True}
                blob = self._store(sid, data)
                source_id, version_id = ident("ksrc"), ident("ksv")
                conn.execute(t.sources.insert().values(id=source_id, space_id=sid, title=name,
                    kind="pdf" if suffix == ".pdf" else "text", status="active", created_at=now()))
                conn.execute(t.versions.insert().values(id=version_id, source_id=source_id,
                    space_id=sid, content_sha256=checksum, blob_ref=blob,
                    mime="application/pdf" if suffix == ".pdf" else "text/plain",
                    size_bytes=len(data), parse_status="received", parser_version="text-v1",
                    created_at=now()))
                self.audit(conn, actor, sid, "source.received", version_id, {"hash": checksum})
                return {"source_id": source_id, "version_id": version_id, "duplicate": False}
            return self.idempotent(conn, actor, sid, "source.upload", key,
                                   {"name": name, "hash": checksum}, apply)

    def list_objects(self, actor, sid, table, limit=50, offset=0):
        with self.engine.connect() as conn:
            self.space(conn, actor, sid)
            total = conn.execute(sa.select(sa.func.count()).select_from(table).where(table.c.space_id == sid)).scalar_one()
            items = [dict(r) for r in conn.execute(sa.select(table).where(table.c.space_id == sid)
                .order_by(table.c.created_at.desc(), table.c.id).limit(limit).offset(offset)).mappings()]
            return {"items": items, "total": total, "limit": limit, "offset": offset}

    def external_refs(self, conn, vid):
        from models.knowledge_operations_v4 import imports
        return [r['reference'] for r in conn.execute(sa.select(imports.c.reference).where(
            imports.c.source_version_id == vid)).mappings()]

    def get_source(self, actor, vid):
        with self.engine.connect() as conn:
            version, _ = self.object_space(conn, actor, t.versions, vid)
            source = row(conn, t.sources, version["source_id"])
            if source["status"] != "active":
                raise KnowledgeError("source_retracted", "来源已撤回", 409)
            result = {k: v for k, v in version.items() if k != "blob_ref"}
            result["title"] = source["title"]
            result["spans"] = self.source_spans(conn, vid)
            result["external_references"] = self.external_refs(conn, vid)
            return result

    def download_source(self, actor, vid):
        with self.engine.begin() as conn:
            version, _ = self.object_space(conn, actor, t.versions, vid, lock=True)
            source = row(conn, t.sources, version["source_id"])
            if source["status"] != "active":
                raise KnowledgeError("source_retracted", "来源已撤回", 409)
            return self.read_source_bytes(version), source["title"]

    def source_spans(self, conn, vid):
        values = [dict(r) for r in conn.execute(sa.select(t.spans).where(t.spans.c.source_version_id == vid)).mappings()]
        return sorted(values, key=lambda r: (r["locator"].get("page", 0), r["locator"].get("line_start", 0)))

    def get_job(self, actor, jid):
        with self.engine.connect() as conn:
            job, _ = self.object_space(conn, actor, t.jobs, jid)
            return job

    def retry_job(self, actor, jid, key):
        job = self.get_job(actor, jid)
        if job["stage"] not in {"failed", "cancelled"}:
            raise KnowledgeError("invalid_state", "只有失败或已取消的任务可重新入库", 409)
        return self.enqueue(actor, job["space_id"], job["source_version_id"], job["options"],
                            "retry-" + digest((jid, key)))

    def cancel_job(self, actor, jid, key):
        with self.engine.begin() as conn:
            job, space = self.object_space(conn, actor, t.jobs, jid, lock=True)
            def apply():
                if job["stage"] == "completed":
                    raise KnowledgeError("already_published", "内容已发布，不能通过取消任务撤销", 409)
                if job["change_set_id"]:
                    conn.execute(t.changes.update().where(t.changes.c.id == job["change_set_id"],
                        t.changes.c.status != "applied").values(status="rejected"))
                conn.execute(t.jobs.update().where(t.jobs.c.id == jid).values(stage="cancelled",
                    fence=job["fence"] + 1, lease_until=None))
                self.audit(conn, actor, space["id"], "ingest.cancelled", jid)
                return {"id": jid, "stage": "cancelled"}
            return self.idempotent(conn, actor, space["id"], "job.cancel", key, {"id": jid}, apply)

    def maintenance_candidate(self, actor, sid, request, key):
        from services.knowledge.maintenance import propose
        return propose(self, actor, sid, request, key)

    def maintenance_report(self, actor, sid):
        from services.knowledge.maintenance import report
        return report(self, actor, sid)

    def page_history(self, actor, pid):
        with self.engine.begin() as conn:
            page, _ = self.object_space(conn, actor, t.pages, pid, lock=True)
            # All history reads still enforce evidence withdrawal.
            result = []
            numbers = conn.execute(sa.select(t.revisions.c.revision_no).where(t.revisions.c.page_id == pid)
                .order_by(t.revisions.c.revision_no.desc()).limit(100)).scalars()
            for number in numbers:
                revision = self._read_revision(conn, page, number)
                result.append({"revision": number, "title": revision["title"], "content_hash": revision["content_hash"]})
            return {"items": result, "status": page["status"], "superseded_by":
                self._read_revision(conn, page)["body_json"].get("superseded_by", "")}

    def operations(self, actor, sid):
        with self.engine.connect() as conn:
            self.space(conn, actor, sid)
            groups = {}
            for name, table, column in [("jobs", t.jobs, t.jobs.c.stage), ("changes", t.changes, t.changes.c.status),
                                         ("outbox", t.outbox, t.outbox.c.status)]:
                groups[name] = {r[0]: r[1] for r in conn.execute(sa.select(column, sa.func.count())
                    .where(table.c.space_id == sid).group_by(column))}
            from services.knowledge.runtime import flag
            from services.knowledge.context import mode
            return {**groups, "projection_enabled": flag("SECOND_BRAIN_PROJECTION_ENABLED"), "context_mode": mode(),
                    "compiler": "extractive-v1"}

    def enqueue(self, actor, sid, vid, options, key):
        with self.engine.begin() as conn:
            self.space(conn, actor, sid, lock=True)
            v = row(conn, t.versions, vid)
            if not v or v["space_id"] != sid:
                raise KnowledgeError("not_found", "来源不存在或不可访问", 404)
            if row(conn, t.sources, v["source_id"])["status"] != "active":
                raise KnowledgeError("source_retracted", "来源已撤回", 409)
            def apply():
                existing_jobs = conn.execute(sa.select(t.jobs).where(t.jobs.c.space_id == sid,
                    t.jobs.c.source_version_id == vid,
                    t.jobs.c.stage.in_(["queued", "compiling", "awaiting_review", "completed"]))).mappings()
                for existing in existing_jobs:
                    if existing["options"] == options:
                        return {"id": existing["id"], "stage": existing["stage"], "duplicate": True}
                jid = ident("kj")
                conn.execute(t.jobs.insert().values(id=jid, space_id=sid, source_version_id=vid,
                    stage="queued", options=options, change_set_id="", work_run_id="",
                    error_code="", attempt=0, fence=0, created_at=now()))
                self.audit(conn, actor, sid, "ingest.queued", jid)
                return {"id": jid, "stage": "queued"}
            return self.idempotent(conn, actor, sid, "ingest", key, {"version": vid, "options": options}, apply)

    def claim_job(self):
        with self.engine.begin() as conn:
            job = conn.execute(sa.select(t.jobs).where(sa.or_(t.jobs.c.stage == "queued",
                sa.and_(t.jobs.c.stage == "compiling", t.jobs.c.lease_until < now())))
                .order_by(t.jobs.c.created_at).with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not job:
                return None
            if job["attempt"] >= 3:
                conn.execute(t.jobs.update().where(t.jobs.c.id == job["id"]).values(
                    stage="failed", error_code="retry_budget_exceeded", lease_until=None))
                return None
            update = {"stage": "compiling", "attempt": job["attempt"] + 1,
                      "fence": job["fence"] + 1, "lease_until": now() + timedelta(seconds=120)}
            conn.execute(t.jobs.update().where(t.jobs.c.id == job["id"]).values(**update))
            space = row(conn, t.spaces, job["space_id"])
            return {**dict(job), **update, "actor": space["owner_user_id"]}

    def _fenced_job(self, conn, job):
        current = conn.execute(sa.select(t.jobs).where(t.jobs.c.id == job["id"])
                               .with_for_update()).mappings().first()
        if not current or current["stage"] != "compiling" or current["fence"] != job["fence"] or current["lease_until"] <= now():
            raise KnowledgeError("lease_conflict", "入库执行租约已失效", 409)
        return current

    def parse(self, version):
        data = self.read_source_bytes(version)
        if version["mime"] == "application/pdf":
            with tempfile.TemporaryDirectory(prefix="kb-parse-") as tmp:
                src, dst = Path(tmp) / "source.pdf", Path(tmp) / "text.json"
                src.write_bytes(data)
                try:
                    result = subprocess.run([sys.executable, str(Path(__file__).with_name("parse_pdf.py")), str(src), str(dst)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                        env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"})
                except subprocess.TimeoutExpired as exc:
                    raise KnowledgeError("parse_timeout", "PDF 解析超过时间预算") from exc
                if result.returncode or not dst.exists():
                    raise KnowledgeError("parse_failed", "PDF 解析失败或解析器未就绪")
                if dst.stat().st_size > 500000:
                    raise KnowledgeError("budget_exceeded", "解析文本超过首版预算")
                parsed = json.loads(dst.read_text("utf-8"))
            if parsed.get("error"):
                raise KnowledgeError(parsed["error"], "PDF 无法完整提取；请核对是否需 OCR、解密或拆分")
            parts = parsed["pages"]
            text = "\n".join(parts)
            chunks = [(p.strip(), {"page": i + 1}) for i, p in enumerate(parts)]
        else:
            text = data.decode("utf-8-sig")
            chunks = []
            for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text):
                start = text[:match.start()].count("\n") + 1
                chunks.append((match.group().strip(), {"line_start": start,
                    "line_end": start + match.group().count("\n")}))
            if len(chunks) > 100:
                # Pack adjacent paragraphs without dropping text or inventing offsets.
                packed = []
                lines = text.splitlines()
                for content, locator in chunks:
                    if packed and len(packed[-1][0]) + len(content) + 2 <= 2000:
                        begin = packed[-1][1]["line_start"]
                        end = locator["line_end"]
                        packed[-1] = ("\n".join(lines[begin - 1:end]), {"line_start": begin, "line_end": end})
                    else:
                        packed.append((content, locator))
                chunks = packed
        if len(text) > 50000 or len(chunks) > 100 or any(len(c[0]) > 12000 for c in chunks):
            raise KnowledgeError("budget_exceeded", "来源超过首版段落预算，请拆分后导入")
        if not chunks:
            raise KnowledgeError("empty_source", "来源没有可解析文本")
        return chunks

    def compile_job(self, job, work_run_id=""):
        with self.engine.connect() as conn:
            version, _ = self.object_space(conn, job["actor"], t.versions, job["source_version_id"])
        chunks = self.parse(version)
        with self.engine.begin() as conn:
            space = self.space(conn, job["actor"], job["space_id"], lock=True)
            self._fenced_job(conn, job)
            source = row(conn, t.sources, version["source_id"])
            if source["status"] != "active":
                raise KnowledgeError("source_retracted", "来源已撤回", 409)
            stored_spans = []
            for i, (text, locator) in enumerate(chunks):
                span_id = "kspan-" + digest((version["id"], i, text))[:32]
                if not row(conn, t.spans, span_id):
                    conn.execute(t.spans.insert().values(id=span_id, source_version_id=version["id"],
                        locator=locator, text=text, text_sha256=digest(text.encode())))
                stored_spans.append({"block_id": f"b-{i}", "text": text, "span_ids": [span_id]})
            conn.execute(t.versions.update().where(t.versions.c.id == version["id"]).values(parse_status="ready"))
            source_page = "kp-" + digest((job["space_id"], version["id"]))[:32]
            old = row(conn, t.pages, source_page)
            operations = [{"page_id": source_page, "base_revision": old["revision"] if old else 0,
                           "type": "source", "title": source["title"], "blocks": stored_spans}]
            relations = []
            concept = job["options"].get("concept_title", "").strip()
            if concept:
                # Explicit user grouping only: no invented AI interpretation or automatic name merge.
                pid = job["options"].get("target_page_id") or ident("kp")
                current = row(conn, t.pages, pid)
                if current:
                    if current["space_id"] != space["id"] or current["type"] != "concept" or current["status"] != "active":
                        raise KnowledgeError("invalid_target", "概念页目标不可用", 409)
                    if current["revision"] != job["options"].get("base_revision"):
                        raise KnowledgeError("revision_conflict", "目标概念已变化，请重新生成候选", 409)
                    previous = conn.execute(sa.select(t.revisions).where(t.revisions.c.page_id == pid,
                        t.revisions.c.revision_no == current["revision"])).mappings().one()["body_json"]
                    blocks = previous["blocks"] + [dict(b, block_id=f"{job['id']}-{i}") for i, b in enumerate(stored_spans)]
                else:
                    if job["options"].get("target_page_id"):
                        raise KnowledgeError("not_found", "概念页不存在", 404)
                    blocks = stored_spans
                operations.append({"page_id": pid, "base_revision": current["revision"] if current else 0,
                    "type": "concept", "title": current["title"] if current else concept, "blocks": blocks})
                relations = [{"from_page_id": source_page, "to_page_id": pid, "relation": "MENTIONS",
                    "rationale": "用户指定的概念分组，原文摘录，待人工核对"},
                    {"from_page_id": pid, "to_page_id": source_page, "relation": "DERIVED_FROM",
                     "rationale": "保留固定来源定位"}]
            vids = {version["id"]}
            for page in operations:
                for block in page["blocks"]:
                    for span_id in block["span_ids"]:
                        vids.add(row(conn, t.spans, span_id)["source_version_id"])
            proposal = Proposal.model_validate({"space_epoch": space["access_epoch"],
                "source_version_ids": sorted(vids), "pages": operations, "links": relations,
                "extraction_mode": "extractive-v1"}).model_dump()
            self.validate(conn, space, proposal)
            cid = ident("kc")
            conn.execute(t.changes.insert().values(id=cid, space_id=space["id"], status="awaiting_review",
                payload=proposal, payload_hash=digest(proposal), review_actor="", review_reason="", created_at=now()))
            conn.execute(t.jobs.update().where(t.jobs.c.id == job["id"]).values(stage="awaiting_review",
                change_set_id=cid, work_run_id=work_run_id, lease_until=None, error_code=""))
            self.audit(conn, job["actor"], space["id"], "ingest.compiled", cid,
                       {"mode": "extractive-v1", "work_run_id": work_run_id})
            return {"id": cid, "payload_hash": digest(proposal)}

    def fail_job(self, job, error):
        with self.engine.begin() as conn:
            self.space(conn, job["actor"], job["space_id"], lock=True)
            self._fenced_job(conn, job)
            conn.execute(t.jobs.update().where(t.jobs.c.id == job["id"]).values(stage="failed",
                error_code=error.code if isinstance(error, KnowledgeError) else "execution_failed", lease_until=None))
            code = getattr(error, "code", "execution_failed")
            conn.execute(t.versions.update().where(t.versions.c.id == job["source_version_id"],
                t.versions.c.parse_status != "ready").values(parse_status="needs_ocr" if code == "needs_ocr" else "failed"))
            self.audit(conn, job["actor"], job["space_id"], "ingest.failed", job["id"], {"code": code})

    def validate(self, conn, space, proposal):
        if proposal["space_epoch"] != space["access_epoch"]:
            raise KnowledgeError("access_changed", "来源访问状态已变化，请重新生成候选", 409)
        allowed = set(proposal["source_version_ids"])
        for vid in allowed:
            v = row(conn, t.versions, vid)
            if not v or v["space_id"] != space["id"] or row(conn, t.sources, v["source_id"])["status"] != "active":
                raise KnowledgeError("invalid_evidence", "来源不可访问或已撤回", 409)
            self.read_source_bytes(v)
        ids = [p["page_id"] for p in proposal["pages"]]
        if len(ids) != len(set(ids)):
            raise KnowledgeError("duplicate_page", "修改集存在重复页面")
        for p in proposal["pages"]:
            existing = row(conn, t.pages, p["page_id"])
            if existing and (existing["space_id"] != space["id"] or existing["status"] != "active"):
                raise KnowledgeError("invalid_page", "页面不可访问", 404)
            if p["base_revision"] != (existing["revision"] if existing else 0):
                raise KnowledgeError("revision_conflict", "页面已变化，请重新生成修改集", 409)
            if existing and p["type"] != existing["type"]:
                raise KnowledgeError("type_change", "页面类型变化需要独立审核流程", 409)
            if len({b["block_id"] for b in p["blocks"]}) != len(p["blocks"]):
                raise KnowledgeError("duplicate_block", "段落标识重复")
            for b in p["blocks"]:
                for span_id in b["span_ids"]:
                    s = row(conn, t.spans, span_id)
                    if not s or s["source_version_id"] not in allowed:
                        raise KnowledgeError("invalid_evidence", "引用不在授权来源中")
                    if digest(s["text"].encode()) != s["text_sha256"]:
                        raise KnowledgeError("evidence_hash_mismatch", "引用内容校验失败", 409)
        targets = proposal.get("link_targets", {})
        for pid, revision in targets.items():
            target = row(conn, t.pages, pid)
            if not target or target["space_id"] != space["id"] or target["status"] != "active":
                raise KnowledgeError("invalid_page", "关系目标不可访问", 404)
            if target["revision"] != revision:
                raise KnowledgeError("revision_conflict", "关系目标修订已变化", 409)
            self._read_revision(conn, target)
        for p in proposal["pages"]:
            target_id = p.get("superseded_by", "")
            if target_id:
                target = next((x for x in proposal["pages"] if x["page_id"] == target_id), None)
                if not target or target_id == p["page_id"] or target.get("superseded_by") or target["type"] != p["type"] or p["type"] == "source":
                    raise KnowledgeError("invalid_merge", "合并目标必须为本修改集内同类型有效知识页")
        for link in proposal["links"]:
            if link["from_page_id"] not in ids or link["to_page_id"] not in set(ids) | set(targets):
                raise KnowledgeError("broken_link", "首版关系必须连接本修改集中的页面")

    def change(self, actor, cid):
        with self.engine.connect() as conn:
            c, _ = self.object_space(conn, actor, t.changes, cid)
            c["sources"] = []
            for vid in c["payload"]["source_version_ids"]:
                version = row(conn, t.versions, vid)
                source = row(conn, t.sources, version["source_id"])
                if source["status"] != "active":
                    raise KnowledgeError("source_retracted", "修改集来源已撤回", 409)
                c["sources"].append({"version_id": vid, "title": source["title"],
                    "spans": self.source_spans(conn, vid)})
            c["relation_targets"] = []
            included_sources = {source["version_id"] for source in c["sources"]}
            for pid, number in c["payload"].get("link_targets", {}).items():
                target = row(conn, t.pages, pid)
                if not target or target["space_id"] != c["space_id"] or target["status"] != "active":
                    raise KnowledgeError("invalid_page", "关系目标不可访问", 404)
                fixed = self._read_revision(conn, target, number)
                c["relation_targets"].append({"page_id": pid, "revision": number, "body_json": fixed["body_json"]})
                for ref in fixed["citations"]:
                    vid = ref["source_version_id"]
                    if vid not in included_sources:
                        included_sources.add(vid)
                        c["sources"].append({"version_id": vid, "title": ref["title"], "spans": self.source_spans(conn, vid)})
            for source in c["sources"]:
                source["external_references"] = self.external_refs(conn, source["version_id"])
            c["before"] = []
            for p in c["payload"]["pages"]:
                if p["base_revision"]:
                    rev = conn.execute(sa.select(t.revisions).where(t.revisions.c.page_id == p["page_id"],
                        t.revisions.c.revision_no == p["base_revision"])).mappings().one()
                    c["before"].append({"page_id": p["page_id"], "body_json": rev["body_json"]})
            return c

    def review(self, actor, cid, payload_hash, decision, reason, key):
        if decision not in {"approve", "reject"} or not reason.strip():
            raise KnowledgeError("invalid_review", "需要有效审核决定及说明")
        with self.engine.begin() as conn:
            c, space = self.object_space(conn, actor, t.changes, cid, lock=True)
            def apply():
                if c["payload_hash"] != payload_hash or digest(c["payload"]) != payload_hash:
                    raise KnowledgeError("review_stale", "审核内容已变化", 409)
                if c["status"] != "awaiting_review":
                    raise KnowledgeError("invalid_state", "修改集不在待审核状态", 409)
                if decision == "approve":
                    self.validate(conn, space, c["payload"])
                status = "approved" if decision == "approve" else "rejected"
                conn.execute(t.changes.update().where(t.changes.c.id == cid).values(
                    status=status, review_actor=actor, review_reason=reason))
                if decision == "reject":
                    conn.execute(t.jobs.update().where(t.jobs.c.change_set_id == cid).values(stage="cancelled"))
                self.audit(conn, actor, space["id"], f"change.{status}", cid, {"hash": payload_hash})
                return {"id": cid, "status": status}
            return self.idempotent(conn, actor, space["id"], f"review:{cid}", key,
                {"hash": payload_hash, "decision": decision, "reason": reason}, apply)

    def publish(self, actor, cid, payload_hash, key):
        with self.engine.begin() as conn:
            c, space = self.object_space(conn, actor, t.changes, cid, lock=True)
            def apply():
                if c["payload_hash"] != payload_hash or digest(c["payload"]) != payload_hash:
                    raise KnowledgeError("review_stale", "发布内容与批准不符", 409)
                if c["status"] == "applied":
                    r = conn.execute(sa.select(t.releases).where(t.releases.c.change_set_id == cid)).mappings().one()
                    return {"release_id": r["id"], "status": "applied", "projection_status": "pending"}
                if c["status"] != "approved" or not c["review_actor"]:
                    raise KnowledgeError("approval_required", "必须先审核具体修改集", 409)
                self.validate(conn, space, c["payload"])
                new_revs = {}
                for p in c["payload"]["pages"]:
                    pid, number, rid = p["page_id"], p["base_revision"] + 1, ident("kv")
                    if p["base_revision"]:
                        conn.execute(t.pages.update().where(t.pages.c.id == pid).values(title=p["title"], revision=number,
                            status="superseded" if p.get("superseded_by") else "active"))
                    else:
                        conn.execute(t.pages.insert().values(id=pid, space_id=space["id"], type=p["type"],
                            title=p["title"], revision=number, status="active", created_at=now()))
                    conn.execute(t.revisions.insert().values(id=rid, page_id=pid, revision_no=number,
                        body_json=p, content_hash=digest(p), change_set_id=cid, created_at=now()))
                    new_revs[pid] = rid
                    for b in p["blocks"]:
                        claim_id = ident("kclaim")
                        conn.execute(t.claims.insert().values(id=claim_id, page_revision_id=rid,
                            block_id=b["block_id"], text=b["text"], epistemic_status=b["epistemic_status"]))
                        for span_id in set(b["span_ids"]):
                            conn.execute(t.evidence.insert().values(claim_id=claim_id, source_span_id=span_id, stance="context"))
                target_revs = dict(new_revs)
                for pid, number in c["payload"].get("link_targets", {}).items():
                    target_revs[pid] = conn.execute(sa.select(t.revisions.c.id).where(
                        t.revisions.c.page_id == pid, t.revisions.c.revision_no == number)).scalar_one()
                # Relationships belong to immutable revisions. Carry existing outgoing
                # relations forward when revising a page; explicit proposals take precedence.
                explicit = {(l["from_page_id"], l["to_page_id"], l["relation"]) for l in c["payload"]["links"]}
                for p in c["payload"]["pages"]:
                    if not p["base_revision"]:
                        continue
                    old_rid = conn.execute(sa.select(t.revisions.c.id).where(t.revisions.c.page_id == p["page_id"],
                        t.revisions.c.revision_no == p["base_revision"])).scalar_one()
                    for old_link in conn.execute(sa.select(t.links).where(t.links.c.from_revision_id == old_rid)).mappings():
                        target = row(conn, t.revisions, old_link["to_revision_id"])
                        if (p["page_id"], target["page_id"], old_link["relation"]) in explicit:
                            continue
                        conn.execute(t.links.insert().values(id=ident("kl"), from_revision_id=new_revs[p["page_id"]],
                            to_revision_id=target_revs.get(target["page_id"], old_link["to_revision_id"]),
                            relation=old_link["relation"], rationale=old_link["rationale"]))
                for link in c["payload"]["links"]:
                    conn.execute(t.links.insert().values(id=ident("kl"),
                        from_revision_id=new_revs[link["from_page_id"]], to_revision_id=target_revs[link["to_page_id"]],
                        relation=link["relation"], rationale=link["rationale"]))
                sequence, release_id = space["sequence"] + 1, ident("krel")
                manifest = {p["id"]: p["revision"] for p in conn.execute(sa.select(t.pages).where(
                    t.pages.c.space_id == space["id"], t.pages.c.status == "active")).mappings()}
                conn.execute(t.releases.insert().values(id=release_id, space_id=space["id"],
                    sequence=sequence, change_set_id=cid, manifest=manifest, created_at=now()))
                conn.execute(t.spaces.update().where(t.spaces.c.id == space["id"]).values(sequence=sequence))
                conn.execute(t.changes.update().where(t.changes.c.id == cid).values(status="applied"))
                conn.execute(t.jobs.update().where(t.jobs.c.change_set_id == cid).values(stage="completed"))
                conn.execute(t.outbox.insert().values(id=ident("ke"), space_id=space["id"],
                    event_type="knowledge.published", payload={"release_id": release_id, "sequence": sequence},
                    status="pending", attempts=0, created_at=now()))
                self.audit(conn, actor, space["id"], "knowledge.published", release_id, {"hash": payload_hash})
                return {"release_id": release_id, "status": "applied", "projection_status": "pending"}
            return self.idempotent(conn, actor, space["id"], f"publish:{cid}", key, {"hash": payload_hash}, apply)

    def _read_revision(self, conn, p, number=None):
        rev = conn.execute(sa.select(t.revisions).where(t.revisions.c.page_id == p["id"],
            t.revisions.c.revision_no == (number or p["revision"]))).mappings().first()
        if not rev:
            raise KnowledgeError("not_found", "知识修订不存在", 404)
        if digest(rev["body_json"]) != rev["content_hash"]:
            raise KnowledgeError("revision_hash_mismatch", "知识修订内容校验失败", 409)
        refs = []
        for block in rev["body_json"]["blocks"]:
            for span_id in block["span_ids"]:
                span = row(conn, t.spans, span_id)
                if not span or digest(span["text"].encode()) != span["text_sha256"]:
                    raise KnowledgeError("evidence_hash_mismatch", "来源片段内容校验失败", 409)
                version = row(conn, t.versions, span["source_version_id"])
                if version["space_id"] != p["space_id"]:
                    raise KnowledgeError("invalid_evidence", "引用不在授权空间内", 409)
                source = row(conn, t.sources, version["source_id"])
                if source["status"] != "active":
                    raise KnowledgeError("source_retracted", "知识依据已撤回，等待复核", 409)
                refs.append({"span_id": span_id, "source_version_id": version["id"],
                    "title": source["title"], "locator": span["locator"], "text": span["text"]})
        return {**dict(p), "title": rev["body_json"]["title"], "revision_id": rev["id"], "revision": rev["revision_no"],
                "body_json": rev["body_json"], "content_hash": rev["content_hash"],
                "source_ref": f"kb-page:{p['id']}@{rev['revision_no']}", "citations": refs}

    def get_page(self, actor, pid, revision=None):
        with self.engine.begin() as conn:
            p, _ = self.object_space(conn, actor, t.pages, pid, lock=True)
            if p["status"] != "active" and not (p["status"] == "superseded" and revision):
                raise KnowledgeError("page_retracted", "知识页已撤回", 409)
            return self._read_revision(conn, p, revision)

    def retract_source(self, actor, vid, key):
        with self.engine.begin() as conn:
            version, space = self.object_space(conn, actor, t.versions, vid, lock=True)
            def apply():
                conn.execute(t.sources.update().where(t.sources.c.id == version["source_id"]).values(status="retracted"))
                conn.execute(t.spaces.update().where(t.spaces.c.id == space["id"]).values(access_epoch=space["access_epoch"] + 1))
                conn.execute(t.outbox.insert().values(id=ident("ke"), space_id=space["id"],
                    event_type="knowledge.source_retracted", payload={"source_version_id": vid},
                    status="pending", attempts=0, created_at=now()))
                self.audit(conn, actor, space["id"], "source.retracted", vid)
                return {"source_version_id": vid, "status": "retracted"}
            return self.idempotent(conn, actor, space["id"], "retract", key, {"version": vid}, apply)

    def query(self, actor, sid, query, limit=10):
        from services.knowledge.retrieval import retrieve
        with self.engine.begin() as conn:
            return retrieve(conn, self, actor, sid, query, limit)
