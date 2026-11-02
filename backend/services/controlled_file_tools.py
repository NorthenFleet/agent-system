"""Filesystem primitives for the DR4 controller; no shell, network or symlinks."""
import hashlib
import os
import stat
from pathlib import PurePosixPath

MAX_BYTES = 131072


def validate(action: str, args: dict) -> str:
    keys = {"path"} | ({"content"} if action == "write" else {"old_text", "new_text"} if action == "edit" else set())
    if action not in {"read", "list", "write", "edit"} or not isinstance(args, dict) or set(args) != keys:
        raise ValueError("invalid_tool_contract")
    if any(not isinstance(v, str) for v in args.values()):
        raise ValueError("invalid_tool_contract")
    if any(len(v.encode()) > MAX_BYTES for v in args.values()):
        raise ValueError("input_budget_exceeded")
    path = args['path']
    if not path or len(path) > 1000 or '\x00' in path or '\\' in path:
        raise ValueError("invalid_path")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or '..' in parsed.parts or any(p.lower() == '.git' for p in parsed.parts):
        raise ValueError("path_outside_workspace")
    if path == '.' and action != 'list':
        raise ValueError("not_a_file")
    if action == 'edit' and not args['old_text']:
        raise ValueError("empty_edit_target")
    return str(parsed)


def execute(root: str, action: str, args: dict) -> dict:
    relative = validate(action, args)
    parts = PurePosixPath(relative).parts
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directories = parts if action == 'list' else parts[:-1]
        for component in directories:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        if action == 'list':
            names = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name.lower() == '.git':
                        continue
                    names.append(entry.name)
                    if len(names) > 512:
                        raise ValueError('directory_budget_exceeded')
            output = '\n'.join(sorted(names))
            return {'output':output, 'result_sha256':hashlib.sha256(output.encode()).hexdigest(), 'bytes':len(output.encode())}
        flags = os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_RDONLY if action == 'read' else os.O_RDWR)
        # New files use exclusive creation; existing hard links cannot be modified.
        try:
            fd = os.open(parts[-1], flags, dir_fd=directory)
        except FileNotFoundError:
            if action != 'write':
                raise
            fd = os.open(parts[-1], flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
                raise ValueError('unsafe_or_oversized_file')
            previous = os.read(fd, MAX_BYTES + 1)
            if len(previous) > MAX_BYTES:
                raise ValueError('file_budget_exceeded')
            before = hashlib.sha256(previous).hexdigest()
            if action == 'read':
                output = previous.decode('utf-8')
                return {'output':output, 'before_sha256':before, 'result_sha256':before, 'bytes':len(previous)}
            if action == 'edit':
                text = previous.decode('utf-8')
                if text.count(args['old_text']) != 1:
                    raise ValueError('edit_target_not_unique')
                content = text.replace(args['old_text'], args['new_text'], 1).encode()
            else:
                content = args['content'].encode()
            if len(content) > MAX_BYTES:
                raise ValueError('output_budget_exceeded')
            os.lseek(fd, 0, os.SEEK_SET)
            remaining = memoryview(content)
            while remaining:
                count = os.write(fd, remaining)
                if count <= 0:
                    raise OSError('short_write')
                remaining = remaining[count:]
            os.ftruncate(fd, len(content))
            os.fsync(fd)
            return {'output':'File operation completed', 'before_sha256':before,
                    'after_sha256':hashlib.sha256(content).hexdigest(), 'bytes':len(content)}
        finally:
            os.close(fd)
    finally:
        os.close(directory)
