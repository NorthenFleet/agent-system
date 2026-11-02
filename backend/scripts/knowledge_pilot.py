"""Read-only authorities + private local pilot ledger; never changes rollout flags."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    preflight = sub.add_parser('preflight'); preflight.add_argument('--output', type=Path)
    init = sub.add_parser('init'); init.add_argument('--root', type=Path, required=True)
    init.add_argument('--owner', required=True); init.add_argument('--project-id', required=True); init.add_argument('--space-id', required=True)
    for name in ['observe', 'report']:
        sub.add_parser(name).add_argument('--root', type=Path, required=True)
    task = sub.add_parser('task'); task.add_argument('--root', type=Path, required=True)
    task.add_argument('--task-id', required=True); task.add_argument('--work-run-id', required=True); task.add_argument('--context-pack-id', required=True)
    review = sub.add_parser('review'); review.add_argument('--root', type=Path, required=True)
    review.add_argument('--file', type=Path, required=True)
    review.add_argument('--attest-human-review', action='store_true', required=True)
    args = parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file(): parser.error('environment file does not exist')
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    from services.knowledge.pilot import PilotLedger, observe, capture_task
    from services.knowledge.service import KnowledgeError, now
    from scripts.knowledge_preflight import check
    import sqlalchemy as sa
    try:
        if args.command == 'preflight':
            result = check()
            result.update({'format':'kb-pilot-preflight-v1', 'captured_at':now().isoformat(), 'production_modified':False,
                           'pilot_owner_configured':bool(os.getenv('SECOND_BRAIN_PILOT_OWNER_ID')),
                           'context_db_configured':bool(os.getenv('SECOND_BRAIN_PILOT_CONTEXT_DB')),
                           'not_checked': [] if result['checks']['postgresql_configured'] else ['knowledge_schema','workrun_schema'],
                           'scope':'explicit environment configuration; not live-process attestation'})
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result['ready'] else 1
        ledger = PilotLedger(args.root)
        if args.command == 'report':
            result = ledger.report()
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result['collection_criteria_met'] else 1
        if args.command == 'review':
            event = ledger.review(json.loads(args.file.read_text()))
        else:
            from services.knowledge.runtime import get_service, require_enabled
            if args.command == 'init':
                checked = check()
                if not checked['ready']:
                    raise KnowledgeError('pilot_preflight_failed','预检未通过，未创建试点记录',409)
                require_enabled()
                scope = {'owner':args.owner,'project_id':args.project_id,'space_id':args.space_id}
                health = observe(get_service(),scope,checked)
                if not health['healthy']:
                    raise KnowledgeError('pilot_unhealthy','当前不具备 shadow 试点条件',409)
                ledger.initialize(scope, checked)
                event = ledger.append('observation',health)
            elif args.command == 'observe':
                scope, _ = ledger.read()
                try:
                    require_enabled()
                    health = observe(get_service(),scope,check())
                except Exception as exc:
                    # Preserve failures in the observation window, without raw errors/DSNs.
                    health = {'healthy':False,'error_code':exc.code if isinstance(exc,KnowledgeError) else 'authority_unavailable'}
                event = ledger.append('observation',health)
            else:
                require_enabled()
                scope, _ = ledger.read()
                engines = []
                try:
                    for key in ['COMMAND_CENTER_DATABASE_URL','WORK_RUN_DATABASE_URL']:
                        value = os.getenv(key,'')
                        if not value or sa.engine.make_url(value).get_backend_name() != 'postgresql':
                            raise KnowledgeError('pilot_authority_required','需要显式配置 Mission 与 WorkRun PostgreSQL 权威',503)
                        engines.append(sa.create_engine(value,connect_args={'connect_timeout':3}))
                    path = Path(os.getenv('SECOND_BRAIN_PILOT_CONTEXT_DB','')).expanduser()
                    if not path.is_absolute() or not path.is_file() or any(p.is_symlink() for p in [path,*path.parents]):
                        raise KnowledgeError('pilot_context_db_required','需要明确的现有 Context Pack SQLite 文件',503)
                    def pack_reader(pid):
                        # mode=ro never creates a missing legacy database; no service singleton imports.
                        conn = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
                        conn.row_factory = sqlite3.Row
                        try:
                            record = conn.execute('SELECT id,user_id,project_id,mission_id,retrieval_health FROM context_packs WHERE id=?',(pid,)).fetchone()
                            return dict(record) if record else None
                        finally:
                            conn.close()
                    payload = capture_task(get_service(),scope,*engines,pack_reader,
                        task_id=args.task_id,work_run_id=args.work_run_id,context_pack_id=args.context_pack_id)
                    event = ledger.append('task',payload)
                finally:
                    for engine in engines: engine.dispose()
        print(json.dumps({'recorded':True,'kind':event['kind'],'event_hash':event['hash'],
                          'captured_at':event['captured_at'],'rollout_enabled':False},ensure_ascii=False))
        return 0
    except KnowledgeError as exc:
        print(json.dumps({'error_code':exc.code,'message':str(exc),'rollout_enabled':False},ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({'error_code':'pilot_input_or_authority_unavailable','rollout_enabled':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
