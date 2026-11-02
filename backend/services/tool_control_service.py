"""Durable tool intents/receipts, fenced by the existing step lease."""
import hashlib
import json

from services import controlled_file_tools as files


class ToolControlMixin:
    def _tool_authority(self, conn, step_id, lease_token):
        from services.command_center_service import InvalidMissionTransition, _iso, _loads
        cursor = conn.execute(
            """UPDATE mission_steps SET updated_at=updated_at WHERE id=? AND status='running'
               AND executor='isolated-code-v1' AND lease_token=? AND lease_expires_at>?
               AND EXISTS (SELECT 1 FROM orchestration_missions m WHERE m.id=mission_steps.mission_id
               AND m.status='running' AND m.plan_version=mission_steps.plan_version)""",
            (step_id, lease_token, _iso()),
        )
        if cursor.rowcount != 1:
            raise InvalidMissionTransition('tool_authority_expired')
        step = conn.execute('SELECT * FROM mission_steps WHERE id=?', (step_id,)).fetchone()
        row = conn.execute('SELECT metadata FROM mission_events WHERE mission_id=? AND event_key=?',
                           (step['mission_id'], f"code-workspace:{step_id}:{step['attempt_count']}")).fetchone()
        if not row:
            raise InvalidMissionTransition('workspace_receipt_missing')
        root = _loads(row['metadata'], {})['workspace']['execution_repo']
        return step, root

    def execute_controlled_tool(self, step_id: str, lease_token: str, call_id: str, action: str, args: dict) -> dict:
        from services.command_center_service import _loads
        if not isinstance(call_id, str) or not 1 <= len(call_id) <= 128:
            return {'ok':False, 'error':'invalid_call_id'}
        if not isinstance(action, str) or len(action) > 32 or not isinstance(args, dict):
            return {'ok':False, 'error':'invalid_tool_contract'}
        canonical = json.dumps({'action':action, 'args':args}, sort_keys=True, ensure_ascii=False)
        if len(canonical.encode()) > 262144:
            return {'ok':False, 'error':'input_budget_exceeded'}
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self.connect(immediate=True) as conn:
            step, root = self._tool_authority(conn, step_id, lease_token)
            prefix = f"tool:{step_id}:{step['attempt_count']}:"
            key = prefix + hashlib.sha256(call_id.encode()).hexdigest()
            if conn.execute('SELECT id FROM mission_events WHERE mission_id=? AND event_key=?', (step['mission_id'], key)).fetchone():
                self._add_event(conn, step['mission_id'], 'tool_rejected', 'running', 'running', 'tool-controller',
                                '重复工具调用被拒绝', {'step_id':step_id, 'reason':'duplicate_call_not_reexecuted'}, event_key=key + ':duplicate')
                return {'ok':False, 'error':'duplicate_call_not_reexecuted'}
            count = conn.execute("SELECT COUNT(*) AS count FROM mission_events WHERE mission_id=? AND event_type='tool_intent' AND event_key LIKE ?",
                                 (step['mission_id'], prefix + '%')).fetchone()['count']
            reason = ''
            relative = ''
            try:
                relative = files.validate(action, args)
            except (ValueError, UnicodeError) as exc:
                reason = str(exc)[:100]
            if count >= 64:
                self._add_event(conn, step['mission_id'], 'tool_rejected', 'running', 'running', 'tool-controller',
                                '工具调用预算耗尽', {'step_id':step_id, 'reason':'tool_call_budget_exhausted'}, event_key=prefix + 'budget')
                return {'ok':False, 'error':'tool_call_budget_exhausted'}
            intent = {'step_id':step_id, 'plan_version':step['plan_version'], 'attempt':step['attempt_count'],
                      'call_id':call_id, 'action':action, 'resource':relative, 'input_sha256':digest,
                      'decision':'deny' if reason else 'allow', 'reason':reason, 'policy_version':'tool-control-v1'}
            self._add_event(conn, step['mission_id'], 'tool_intent', 'running', 'running', 'tool-controller',
                            '工具调用前检查：' + intent['decision'], intent, event_key=key)
        # Intent is committed before filesystem mutation. Crashes leave an unresolved intent.
        if reason:
            return {'ok':False, 'error':reason}
        with self.connect(immediate=True) as conn:
            current, current_root = self._tool_authority(conn, step_id, lease_token)
            if current['attempt_count'] != step['attempt_count'] or current_root != root:
                return {'ok':False, 'error':'tool_authority_changed'}
            stored = conn.execute('SELECT metadata FROM mission_events WHERE mission_id=? AND event_key=?', (step['mission_id'], key)).fetchone()
            if not stored or _loads(stored['metadata'], {}).get('input_sha256') != digest:
                return {'ok':False, 'error':'tool_intent_mismatch'}
            try:
                operation = files.execute(root, action, args)
                output = operation.pop('output')
                receipt = {**intent, **operation, 'status':'completed'}
            except (OSError, ValueError, UnicodeError) as exc:
                output = ''
                receipt = {**intent, 'status':'unknown' if action in {'write','edit'} else 'error', 'error_type':type(exc).__name__}
            self._add_event(conn, step['mission_id'], 'tool_receipt', 'running', 'running', 'tool-controller',
                            '工具调用回执：' + receipt['status'], receipt, event_key=key + ':receipt')
            return {'ok':receipt['status'] == 'completed', 'output':output,
                    'error':'' if receipt['status'] == 'completed' else 'file_operation_failed', 'receipt':receipt}

    def tool_control_summary(self, step_id: str, attempt: int) -> dict:
        from services.command_center_service import _loads
        with self.connect() as conn:
            rows = conn.execute("SELECT event_type, metadata FROM mission_events WHERE event_key LIKE ? AND event_type IN ('tool_intent','tool_receipt','tool_rejected')",
                                (f'tool:{step_id}:{attempt}:%',)).fetchall()
        intents = [_loads(row['metadata'], {}) for row in rows if row['event_type'] == 'tool_intent']
        receipts = [_loads(row['metadata'], {}) for row in rows if row['event_type'] == 'tool_receipt']
        completed = {row['call_id'] for row in receipts}
        incomplete = sum(i['decision'] == 'allow' and i['call_id'] not in completed for i in intents)
        denied = sum(i['decision'] == 'deny' for i in intents) + sum(row['event_type'] == 'tool_rejected' for row in rows)
        unknown = sum(r['status'] == 'unknown' for r in receipts)
        return {'policy_version':'tool-control-v1', 'enforced':True, 'calls':len(intents), 'receipts':len(receipts),
                'denied':denied, 'incomplete':incomplete, 'unknown':unknown,
                'accepted':bool(receipts) and not (denied or incomplete or unknown)}
