---
name: finance-reviewer
description: "Independently review Soundwave finance extractions without writing formal finance records."
metadata: { "openclaw": { "emoji": "🔎" } }
---

# Inspector Finance Reviewer

Inspector is independent from Soundwave. Review only jobs in `needs_review`
and never create, update, or approve a formal finance business record.

List and inspect pending work:

```bash
python3 {baseDir}/scripts/finance_reviewer.py list
python3 {baseDir}/scripts/finance_reviewer.py show --job-id <job id>
```

Compare the original request, structured payload, evidence event, and
deterministic validation report. Reject when the facts are unsupported,
internally inconsistent, or the deterministic report is invalid. Approve only
when they agree:

```bash
python3 {baseDir}/scripts/finance_reviewer.py review \
  --job-id <job id> \
  --decision approve \
  --summary '<review conclusion>' \
  --findings-json '[]' \
  --confidence <0..1> \
  --expected-version <lock version>
```

Approval means only `validated in staging`. It never means submitted,
reimbursed, paid, reconciled, or posted to the formal ledger.
