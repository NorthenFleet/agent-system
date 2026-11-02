"""Stable bindings for evidence and criteria within an approved step."""
import hashlib
import json


def contract_items(step, field):
    scope = [step.get('idempotency_key'), step.get('id'), step.get('plan_version')]
    prefix = 'ev' if field == 'evidence_required' else 'ac'
    return [
        {'id': prefix + '-' + hashlib.sha256(json.dumps(
            [scope, field, index, str(value).strip()], ensure_ascii=False,
            separators=(',', ':'),
        ).encode()).hexdigest()[:20], 'text': str(value).strip()}
        for index, value in enumerate((step.get(field) or [])[:30])
        if str(value).strip()
    ]
