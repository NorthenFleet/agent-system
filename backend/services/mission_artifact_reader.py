"""Read registered task artifacts inside explicitly allowed delivery roots."""
from pathlib import Path
import hashlib
import os
import re
import stat


def read_artifact(artifact: dict) -> tuple[str, bytes]:
    default = Path(__file__).resolve().parents[2] / "docs" / "review"
    roots = [Path(p).resolve() for p in os.getenv("COMMAND_CENTER_ARTIFACT_ROOTS", str(default)).split(os.pathsep) if p]
    path = Path(str(artifact.get("uri") or ""))
    if not path.is_absolute() or any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("产物路径不可访问")
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root) for root in roots):
        raise ValueError("产物不在允许的交付目录中")
    expected = str(artifact.get("content_hash") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("产物缺少可验证的 SHA256")
    descriptor = os.open(resolved, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("产物必须是普通文件")
        data = source.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("产物超过5MB，请通过工作区查看")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("文件已变化，与该任务登记的版本不一致")
    return resolved.name, data
