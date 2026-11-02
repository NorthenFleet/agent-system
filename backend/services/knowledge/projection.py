"""Fixed-release Markdown projection with leased Outbox delivery and drift detection.

Filesystem and PostgreSQL are deliberately not called atomic. A private generation
is completed before switching current.json; a lost DB receipt is safe to replay.
The common space lock serializes publication, withdrawal and pointer switching.
"""
import html
import json
import os
import random
import re
import stat
import time
from datetime import timedelta
from pathlib import Path

import sqlalchemy as sa
from models import knowledge_schema_v1 as t
from models.knowledge_projection_v2 import receipts
from services.knowledge.service import KnowledgeError, digest, ident, now, row


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode()


def plain(value):
    # Export untrusted source text as literal Markdown, never active HTML/images.
    value = html.escape(value, quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value)


class ProjectionService:
    def __init__(self, service, root):
        self.service, self.engine = service, service.engine
        path = Path(root).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise KnowledgeError('unsafe_projection_root', '需要专用的绝对投影目录', 503)
        self.root = path.resolve()
        if self.root == service.root or self.root in service.root.parents or service.root in self.root.parents:
            raise KnowledgeError('unsafe_projection_root', '来源与投影目录必须独立', 503)

    def _directory(self, path):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink() or path.resolve() != path or path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise KnowledgeError('unsafe_projection_root', '投影目录必须为当前用户所有且权限为 0700', 503)
        return path

    def _space_dir(self, sid):
        if not re.fullmatch(r'ks-[a-f0-9]{32}', sid):
            raise KnowledgeError('invalid_space', '投影空间标识不合法')
        self._directory(self.root)
        return self._directory(self.root / sid)

    def _read(self, path, limit=12 * 1024 * 1024):
        if path.is_symlink() or path.resolve() != path or not path.is_file() or path.stat().st_size > limit:
            raise KnowledgeError('projection_drift', '投影文件异常，需检查并重新生成', 409)
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            return stream.read(limit + 1)

    def _write(self, path, data):
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def inspect(self, conn, sid):
        directory = self.root / sid
        if not directory.exists():
            return {'status': 'missing', 'issues': ['current_missing']}
        if directory.is_symlink() or directory.resolve() != directory:
            return {'status': 'drift', 'issues': ['unsafe_directory']}
        pointer_path = directory / 'current.json'
        if not pointer_path.exists():
            return {'status': 'missing', 'issues': ['current_missing']}
        try:
            raw = self._read(pointer_path, 16384)
            pointer = json.loads(raw)
            generation = pointer['generation']
            if not re.fullmatch(r'g-[a-f0-9]{32}', generation) or pointer['space_id'] != sid:
                raise ValueError()
            folder = directory / 'generations' / generation
            manifest_raw = self._read(folder / 'manifest.json')
            manifest = json.loads(manifest_raw)
            issues = []
            if digest(manifest_raw) != pointer['manifest_sha256']:
                issues.append('manifest_hash')
            receipt = row(conn, receipts, pointer['event_id'])
            if receipt and receipt['result'].get('pointer_hash') and receipt['result']['pointer_hash'] != digest(raw):
                issues.append('pointer_hash')
            elif not receipt:
                issues.append('unknown_event')
            expected = manifest['files']
            if len(expected) > 1003:
                raise ValueError()
            for name, checksum in expected.items():
                rel = Path(name)
                if rel.is_absolute() or '..' in rel.parts:
                    raise ValueError()
                file_path = folder / rel
                if not file_path.exists() or digest(self._read(file_path)) != checksum:
                    issues.append('file_hash:' + name)
            actual = {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
            if actual != set(expected) | {'manifest.json'}:
                issues.append('file_set')
            return {'status': 'drift' if issues else 'ready', 'issues': issues, 'pointer': pointer}
        except (OSError, ValueError, KeyError, TypeError, KnowledgeError):
            return {'status': 'drift', 'issues': ['invalid_generation']}

    def health(self, actor, sid):
        with self.engine.begin() as conn:
            space = self.service.space(conn, actor, sid, lock=True)
            state = self.inspect(conn, sid)
            pointer = state.get('pointer', {})
            if state['status'] == 'ready' and (pointer.get('sequence') != space['sequence'] or pointer.get('access_epoch') != space['access_epoch']):
                state['status'] = 'lagging'
            events = [dict(r) for r in conn.execute(sa.select(t.outbox.c.id, t.outbox.c.event_type,
                t.outbox.c.status, t.outbox.c.attempts, receipts.c.error_code, receipts.c.next_attempt_at)
                .outerjoin(receipts, receipts.c.id == t.outbox.c.id).where(t.outbox.c.space_id == sid)
                .order_by(t.outbox.c.created_at.desc()).limit(50)).mappings()]
            return {**state, 'expected_sequence': space['sequence'], 'expected_epoch': space['access_epoch'], 'events': events}

    def claim(self):
        with self.engine.begin() as conn:
            stmt = sa.select(t.outbox).outerjoin(receipts, receipts.c.id == t.outbox.c.id).where(
                t.outbox.c.event_type.in_(['knowledge.published', 'knowledge.source_retracted']),
                sa.or_(t.outbox.c.status == 'pending',
                    sa.and_(t.outbox.c.status == 'retry', receipts.c.next_attempt_at <= now()),
                    sa.and_(t.outbox.c.status == 'processing', receipts.c.lease_until < now())))
            event = conn.execute(stmt.order_by(t.outbox.c.created_at, t.outbox.c.id)
                .with_for_update(of=t.outbox, skip_locked=True).limit(1)).mappings().first()
            if not event:
                return None
            previous = row(conn, receipts, event['id'])
            if event['attempts'] >= 8:
                conn.execute(t.outbox.update().where(t.outbox.c.id == event['id']).values(status='dead'))
                return None
            fence = (previous['fence'] if previous else 0) + 1
            values = {'fence': fence, 'lease_until': now() + timedelta(seconds=120),
                      'next_attempt_at': None, 'error_code': ''}
            if previous:
                conn.execute(receipts.update().where(receipts.c.id == event['id']).values(**values))
            else:
                conn.execute(receipts.insert().values(id=event['id'], space_id=event['space_id'], result={}, **values))
            conn.execute(t.outbox.update().where(t.outbox.c.id == event['id']).values(
                status='processing', attempts=event['attempts'] + 1))
            return {**dict(event), 'fence': fence, 'attempts': event['attempts'] + 1}

    def _fence(self, conn, event):
        # Lock order is always space -> outbox -> receipt for processing/replay.
        obj = conn.execute(sa.select(t.outbox).where(t.outbox.c.id == event['id']).with_for_update()).mappings().one()
        lease = row(conn, receipts, event['id'])
        if obj['status'] != 'processing' or lease['fence'] != event['fence'] or lease['lease_until'] <= now():
            raise KnowledgeError('projection_lease_conflict', '投影执行租约已失效', 409)
        return lease

    def _snapshot(self, conn, space, event):
        if event['event_type'] == 'knowledge.published':
            release = row(conn, t.releases, event['payload']['release_id'])
        else:
            release = conn.execute(sa.select(t.releases).where(t.releases.c.space_id == space['id'])
                .order_by(t.releases.c.sequence.desc()).limit(1)).mappings().first()
        manifest = release['manifest'] if release else {}
        sequence = release['sequence'] if release else 0
        if len(manifest) > 1000:
            raise KnowledgeError('projection_budget', '投影最多支持 1000 页')
        pages = {}
        for pid, number in manifest.items():
            page = row(conn, t.pages, pid)
            if page['status'] != 'active':
                continue
            try:
                pages[pid] = self.service._read_revision(conn, page, number)
            except KnowledgeError as exc:
                if exc.code != 'source_retracted':
                    raise
        edges = []
        for pid, page in pages.items():
            for link in conn.execute(sa.select(t.links).where(t.links.c.from_revision_id == page['revision_id'])).mappings():
                target = row(conn, t.revisions, link['to_revision_id'])
                target_id = target['page_id']
                # Resolve merged IDs to the active destination without deleting history.
                target_page = row(conn, t.pages, target_id)
                visited = set()
                while target_page and target_page['status'] == 'superseded' and target_id not in visited:
                    visited.add(target_id)
                    merged = conn.execute(sa.select(t.revisions.c.body_json).where(t.revisions.c.page_id == target_id,
                        t.revisions.c.revision_no == target_page['revision'])).scalar_one()
                    target_id = merged.get('superseded_by', '')
                    target_page = row(conn, t.pages, target_id)
                if target_id in pages and target_id != pid:
                    edges.append({'from': pid, 'to': target_id, 'relation': link['relation'], 'rationale': link['rationale'],
                        'from_revision': page['revision'], 'target_evidence_revision': target['revision_no'],
                        'target_evidence_page_id': target['page_id'], 'target_current_revision': pages[target_id]['revision']})
        return sequence, pages, edges

    def _files(self, space, sequence, pages, edges):
        result = {}
        kinds = {'source': 'sources', 'concept': 'concepts', 'entity': 'entities', 'synthesis': 'synthesis'}
        for pid, page in pages.items():
            body = page['body_json']
            front = {'page_id': pid, 'revision': page['revision'], 'type': body['type'], 'title': body['title'],
                'aliases': body.get('aliases', []), 'source_refs': sorted({r['source_version_id'] for r in page['citations']}),
                'content_hash': page['content_hash'], 'generated': True}
            text = '---\n' + '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in front.items()) + '\n---\n\n'
            text += '# ' + plain(body['title']) + '\n\n'
            refs = {ref['span_id']: ref for ref in page['citations']}
            for block in body['blocks']:
                text += plain(block['text']) + '\n\n'
                for span_id in block['span_ids']:
                    ref = refs[span_id]
                    text += f"来源：{ref['source_version_id']} / {span_id} / {json.dumps(ref['locator'], ensure_ascii=False)}\n\n"
            for edge in edges:
                if edge['from'] == pid:
                    # Stable link IDs; source-provided aliases cannot inject wiki links.
                    alias = re.sub(r'[\[\]|\n\r]', ' ', pages[edge['to']]['body_json']['title'])
                    text += f"[[{edge['to']}|{plain(alias)}]] · {edge['relation']} · {plain(edge['rationale'])}\n\n"
            result[f"wiki/{kinds[body['type']]}/{pid}.md"] = text.encode()
        result['index.md'] = ('# 知识索引\n\n' + '\n'.join(f"- [[{pid}]] · {plain(page['title'])}" for pid, page in pages.items())).encode()
        result['log.md'] = f"# 投影记录\n\n发布序号：{sequence}\n访问版本：{space['access_epoch']}\n".encode()
        result['graph-index.json'] = encoded({'nodes': [{'id': pid, 'title': p['title'], 'revision': p['revision']} for pid, p in pages.items()], 'edges': edges})
        if sum(map(len, result.values())) > 10 * 1024 * 1024:
            raise KnowledgeError('projection_budget', '投影超过 10 MiB 预算')
        return result

    def process(self, event):
        started = time.monotonic()
        with self.engine.begin() as conn:
            owner = row(conn, t.spaces, event['space_id'])['owner_user_id']
            space = self.service.space(conn, owner, event['space_id'], lock=True)
            lease = self._fence(conn, event)
            # Older release events may never downgrade current, even after withdrawal.
            if event['event_type'] == 'knowledge.published' and event['payload']['sequence'] < space['sequence']:
                conn.execute(t.outbox.update().where(t.outbox.c.id == event['id']).values(status='superseded'))
                return
            directory = self._space_dir(space['id'])
            state = self.inspect(conn, space['id'])
            if state['status'] == 'drift' and not lease['result'].get('regenerate'):
                raise KnowledgeError('projection_drift', '发现外部修改；保留差异后请明确重新生成', 409)
            sequence, pages, edges = self._snapshot(conn, space, event)
            files = self._files(space, sequence, pages, edges)
            generation = ident('g')
            generations = self._directory(directory / 'generations')
            folder = self._directory(generations / generation)
            for name, data in files.items():
                path = folder / name
                for ancestor in reversed(path.parent.relative_to(folder).parents):
                    if str(ancestor) != '.':
                        self._directory(folder / ancestor)
                self._directory(path.parent)
                self._write(path, data)
            manifest = {'space_id': space['id'], 'sequence': sequence, 'access_epoch': space['access_epoch'],
                        'pages': {pid: page['revision'] for pid, page in pages.items()},
                        'files': {name: digest(data) for name, data in files.items()}}
            manifest_data = encoded(manifest)
            self._write(folder / 'manifest.json', manifest_data)
            for name, checksum in manifest['files'].items():
                if digest(self._read(folder / name)) != checksum:
                    raise KnowledgeError('projection_hash', '生成文件校验失败', 409)
            for subdirectory in [folder, *[p for p in folder.rglob('*') if p.is_dir()], generations]:
                fd = os.open(subdirectory, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            pointer = {'space_id': space['id'], 'generation': generation, 'sequence': sequence,
                       'access_epoch': space['access_epoch'], 'event_id': event['id'], 'manifest_sha256': digest(manifest_data)}
            pointer_data = encoded(pointer)
            # Check the fence again immediately before exposing the complete generation.
            self._fence(conn, event)
            if time.monotonic() - started > 100:
                raise KnowledgeError('projection_budget', '投影处理超时')
            temporary = directory / ('.current-' + generation + '.json')
            self._write(temporary, pointer_data)
            if lease['result'].get('regenerate') and (directory / 'current.json').exists():
                # Preserve the exact externally modified pointer as well as its generation.
                self._write(directory / ('preserved-' + generation + '.json'), self._read(directory / 'current.json', 16384))
            os.replace(temporary, directory / 'current.json')
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            conn.execute(receipts.update().where(receipts.c.id == event['id']).values(lease_until=None,
                error_code='', result={'pointer_hash': digest(pointer_data), **pointer}))
            conn.execute(t.outbox.update().where(t.outbox.c.id == event['id']).values(status='completed'))
            self.service.audit(conn, owner, space['id'], 'projection.completed', event['id'],
                               {'sequence': sequence, 'epoch': space['access_epoch'], 'pages': len(pages)})

    def fail(self, event, exc):
        with self.engine.begin() as conn:
            owner = row(conn, t.spaces, event['space_id'])['owner_user_id']
            self.service.space(conn, owner, event['space_id'], lock=True)
            try:
                self._fence(conn, event)
            except KnowledgeError:
                return
            code = getattr(exc, 'code', 'projection_io_error')
            status = 'blocked_drift' if code == 'projection_drift' else ('dead' if event['attempts'] >= 8 else 'retry')
            delay = min(3600, 2 ** event['attempts']) + random.uniform(0, 1)
            conn.execute(t.outbox.update().where(t.outbox.c.id == event['id']).values(status=status))
            conn.execute(receipts.update().where(receipts.c.id == event['id']).values(error_code=code,
                lease_until=None, next_attempt_at=now() + timedelta(seconds=delay)))

    def run_once(self):
        event = self.claim()
        if not event:
            return False
        try:
            self.process(event)
        except Exception as exc:
            self.fail(event, exc)
        return True

    def replay(self, actor, sid, event_id, key, regenerate=False):
        with self.engine.begin() as conn:
            self.service.space(conn, actor, sid, lock=True)
            event = row(conn, t.outbox, event_id)
            if not event or event['space_id'] != sid:
                raise KnowledgeError('not_found', '事件不存在或不可访问', 404)
            def apply():
                conn.execute(sa.select(t.outbox).where(t.outbox.c.id == event_id).with_for_update()).one()
                lease = row(conn, receipts, event_id)
                if event['status'] == 'processing' and lease and lease['lease_until'] > now():
                    raise KnowledgeError('projection_busy', '投影正在处理', 409)
                if event['status'] == 'blocked_drift' and not regenerate:
                    raise KnowledgeError('projection_drift', '外部差异需要明确重新生成', 409)
                if lease:
                    # Keep the previous pointer hash until the new generation is ready.
                    conn.execute(receipts.update().where(receipts.c.id == event_id).values(
                        result={**lease['result'], 'regenerate': regenerate}, next_attempt_at=None))
                conn.execute(t.outbox.update().where(t.outbox.c.id == event_id).values(status='pending', attempts=0))
                self.service.audit(conn, actor, sid, 'projection.regenerate' if regenerate else 'projection.replay', event_id)
                return {'id': event_id, 'status': 'pending'}
            return self.service.idempotent(conn, actor, sid, 'projection.replay', key,
                                           {'event': event_id, 'regenerate': regenerate}, apply)
