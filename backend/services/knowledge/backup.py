"""Bounded logical KB backups and restoration into an empty isolated schema only.

These archives contain private plaintext. Store trusted copies with filesystem
access control. SHA-256 detects damage, not a malicious operator rewriting all
manifests. External authorities/WorkRun and PostgreSQL cluster recovery are not
part of this logical archive.
"""
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from models.knowledge_projection_v2 import metadata as projection
from models.knowledge_context_v3 import metadata as context
from models.knowledge_operations_v4 import metadata as operations
from services.knowledge.service import KnowledgeError, KnowledgeService, digest, now

TABLES = [*t.metadata.sorted_tables, *projection.sorted_tables, *context.sorted_tables, *operations.sorted_tables]
MAX_BYTES = 100 * 1024 * 1024


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      default=lambda v: v.isoformat() if isinstance(v, datetime) else str(v)).encode()


def private_directory(path, *, create=False):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        # /tmp on macOS is a system symlink: callers use resolved /private/tmp.
        raise KnowledgeError('unsafe_backup_root', '备份目录不允许符号链接')
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    if not path.is_dir() or path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise KnowledgeError('unsafe_backup_root', '备份目录必须由当前用户所有且权限为 0700')
    return path


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def read_private(path, maximum=MAX_BYTES):
    if path.is_symlink():
        raise KnowledgeError('unsafe_backup_file', '备份文件不可为符号链接')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise KnowledgeError('unsafe_backup_file', '备份文件必须为私有普通文件')
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise KnowledgeError('backup_budget', '备份超过本批运维预算')
    return data


def capture(service, destination):
    root = private_directory(destination, create=True)
    blobs = root / 'blobs'; blobs.mkdir(mode=0o700)
    total, files, tables = 0, {}, {}
    # Snapshot covers all KB tables consistently. Source blobs are immutable.
    with service.engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        with conn.begin():
            captured_at = now().isoformat()
            for table in TABLES:
                rows = list(conn.execute(sa.select(table).limit(100001)).mappings())
                if len(rows) > 100000:
                    raise KnowledgeError('backup_budget', '单表超过 100000 行，需要专用备份流程')
                records = [dict(r) for r in rows]
                data = encode(records); total += len(data)
                if total > MAX_BYTES:
                    raise KnowledgeError('backup_budget', '逻辑备份超过 100 MiB')
                write_private(root / (table.name + '.json'), data)
                tables[table.name] = {'sha256': digest(data), 'count': len(records)}
                if table is t.versions:
                    for version in records:
                        checksum = version['content_sha256']
                        if checksum in files:
                            continue
                        data = service.read_source_bytes(version); total += len(data)
                        if total > MAX_BYTES:
                            raise KnowledgeError('backup_budget', '逻辑备份超过 100 MiB')
                        write_private(blobs / checksum, data)
                        files[checksum] = len(data)
            spaces = [dict(r) for r in conn.execute(sa.select(t.spaces)).mappings()]
    manifest = {'format': 'kb-backup-v1', 'schema_revision': '20261006_knowledge_operations',
        'captured_at': captured_at, 'tables': tables, 'blobs': files, 'bytes': total,
        'space_ids': sorted(s['id'] for s in spaces)}
    write_private(root / 'manifest.json', encode(manifest))  # completion marker written last
    directory = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return manifest


def revocations(service, destination):
    """Separate current checkpoint, kept outside the backup being restored."""
    with service.engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        with conn.begin():
            spaces = [dict(r) for r in conn.execute(sa.select(t.spaces)).mappings()]
            revoked = sorted(conn.execute(sa.select(t.sources.c.id).where(t.sources.c.status != 'active')).scalars())
            payload = {'format': 'kb-revocations-v1', 'captured_at': now().isoformat(),
                'spaces': {s['id']: {'access_epoch': s['access_epoch'], 'status': s['status'],
                                    'owner_user_id': s['owner_user_id'], 'project_id': s['project_id']} for s in spaces},
                'source_ids': revoked}
    target = Path(destination).absolute()
    private_directory(target.parent)
    write_private(target, encode({'payload': payload, 'sha256': digest(payload)}))
    return payload


def verify(destination):
    root = private_directory(destination)
    manifest = json.loads(read_private(root / 'manifest.json'))
    if manifest['format'] != 'kb-backup-v1' or manifest['schema_revision'] != '20261006_knowledge_operations':
        raise KnowledgeError('backup_version', '备份版本不支持')
    if set(manifest['tables']) != {t.name for t in TABLES}:
        raise KnowledgeError('backup_inventory', '备份表清单不完整')
    total, rows = 0, {}
    private_directory(root / 'blobs')
    for table in TABLES:
        data = read_private(root / (table.name + '.json')); total += len(data)
        if total > MAX_BYTES:
            raise KnowledgeError('backup_budget', '备份超过总量预算')
        expected = manifest['tables'][table.name]
        if digest(data) != expected['sha256']:
            raise KnowledgeError('backup_hash_mismatch', '备份表哈希不匹配', 409)
        records = json.loads(data)
        if len(records) != expected['count'] or len(records) > 100000:
            raise KnowledgeError('backup_inventory', '备份记录数量不匹配')
        rows[table.name] = records
    for checksum, size in manifest['blobs'].items():
        if not re.fullmatch(r'[a-f0-9]{64}', checksum):
            raise KnowledgeError('backup_inventory', '来源哈希格式不合法')
        data = read_private(root / 'blobs' / checksum, 5 * 1024 * 1024); total += len(data)
        if digest(data) != checksum or len(data) != size:
            raise KnowledgeError('backup_hash_mismatch', '备份附件哈希不匹配', 409)
    if total != manifest['bytes'] or total > MAX_BYTES:
        raise KnowledgeError('backup_budget', '备份总量不一致或超出预算')
    actual_spaces = sorted(s['id'] for s in rows[t.spaces.name])
    if actual_spaces != manifest['space_ids'] or any(not re.fullmatch(r'ks-[a-f0-9]{32}', sid) for sid in actual_spaces):
        raise KnowledgeError('backup_inventory', '空间清单或标识不合法')
    for v in rows[t.versions.name]:
        if v['space_id'] not in actual_spaces or v['blob_ref'] != v['space_id'] + '/' + v['content_sha256']:
            raise KnowledgeError('backup_inventory', '来源路径清单不一致')
        if v['content_sha256'] not in manifest['blobs'] or manifest['blobs'][v['content_sha256']] != v['size_bytes']:
            raise KnowledgeError('backup_inventory', '备份缺少固定来源附件')
    return manifest, rows


def restore_isolated(engine, source_root, backup_root, revocation_file, project_check):
    """No general production restore entry point: empty sb_restore_<uuid> only."""
    manifest, rows = verify(backup_root)
    log_path = Path(revocation_file).absolute()
    private_directory(log_path.parent)
    journal = json.loads(read_private(log_path)); journal_data = journal['payload']
    if journal['sha256'] != digest(journal_data) or journal_data['format'] != 'kb-revocations-v1':
        raise KnowledgeError('revocation_hash_mismatch', '独立撤回清单校验失败')
    if datetime.fromisoformat(journal_data['captured_at']) < datetime.fromisoformat(manifest['captured_at']):
        raise KnowledgeError('revocation_stale', '撤回清单早于备份，禁止恢复查询')
    if not set(manifest['space_ids']) <= set(journal_data['spaces']):
        raise KnowledgeError('revocation_incomplete', '撤回清单缺少空间')
    root = Path(source_root).absolute()
    private_directory(root.parent)
    if root.exists():
        raise KnowledgeError('restore_target_not_empty', '恢复附件目录必须为新目录')
    service = KnowledgeService(engine, root, project_check=project_check)
    with engine.begin() as conn:
        schema = conn.execute(sa.text('select current_schema()')).scalar_one()
        if not re.fullmatch(r'sb_restore_[a-f0-9]{32}', schema):
            raise KnowledgeError('restore_isolation_required', '仅允许向隔离恢复 schema 写入')
        for table in TABLES:
            if conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one():
                raise KnowledgeError('restore_target_not_empty', '恢复目标表必须为空')
        for table in TABLES:
            # Machine-bound projection receipts are regenerated; do not restore leases.
            if table.name == 'kb_projection_receipts':
                continue
            for original in rows[table.name]:
                record = dict(original)
                for column in table.c:
                    if isinstance(column.type, sa.DateTime) and record[column.name] is not None:
                        record[column.name] = datetime.fromisoformat(record[column.name])
                if table is t.spaces:
                    current = journal_data['spaces'][record['id']]
                    if (record['owner_user_id'], record['project_id']) != (current['owner_user_id'], current['project_id']):
                        raise KnowledgeError('restore_scope_changed', '空间权限已变化，需要人工恢复策略')
                    record['access_epoch'] = max(record['access_epoch'], current['access_epoch']) + 1
                    record['status'] = current['status']
                elif table is t.sources and record['id'] in journal_data['source_ids']:
                    record['status'] = 'retracted'
                elif table is t.jobs:
                    record['work_run_id'] = ''
                    if record['stage'] in {'queued', 'compiling'}:
                        record.update(stage='failed', error_code='restored_manual_retry', lease_until=None, fence=record['fence'] + 1)
                elif table is t.outbox:
                    record.update(status='pending', attempts=0)
                elif table.name == 'kb_maintenance_runs':
                    record['work_run_id'] = ''
                conn.execute(table.insert().values(**record))
        for v in rows[t.versions.name]:
            data = read_private(Path(backup_root) / 'blobs' / v['content_sha256'], 5 * 1024 * 1024)
            service._store(v['space_id'], data)
        for s in rows[t.spaces.name]:
            service.audit(conn, 'restore-operator', s['id'], 'recovery.restored', schema,
                          {'backup_at': manifest['captured_at'], 'revocations_at': journal_data['captured_at']})
    return service
