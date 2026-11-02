"""Read-only strict evaluation of captured real execution results; never edits history."""
import json
import sys
from pathlib import Path
from services.execution_evidence_service import ExecutionEvidenceService

source, target = map(Path, sys.argv[1:3])
data = json.loads(source.read_text())
service = ExecutionEvidenceService()
rows = []
for step in data.get('steps') or []:
    if not step.get('output'):
        continue
    result = service.enrich_result(step['contract'], {'structured_output': step['output']},
        success=True, enforcement={'mode': 'strict', 'enforced': True})
    rows.append({'step_id': step['id'], 'plan_version': step['plan_version'],
                 'live_status': step['status'], 'strict_quality': result['execution_quality']})
target.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
print(json.dumps(rows, ensure_ascii=False, indent=2))
