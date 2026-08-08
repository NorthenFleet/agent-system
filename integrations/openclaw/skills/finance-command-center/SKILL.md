---
name: finance-command-center
description: "Route every finance conversation handled by Soundwave into the 3021 audited finance intake contract before replying."
metadata: { "openclaw": { "emoji": "🔊" } }
---

# Soundwave Finance Command Center

Soundwave is the user's finance contact. PostgreSQL in 3021 remains the only
authoritative finance store; chat history and agent memory are context only.

For every finance query or requested finance operation, first call:

```bash
python3 {baseDir}/scripts/finance_command_center.py route \
  --message "<original user message, verbatim>"
```

The expected action is `finance_intake` and the response must include a
`finance_job` whose `mode` is `shadow` and status is `shadow_read`. It records
the request in the PostgreSQL intake staging area and routes it to `soundwave`,
but it does not create a software/document mission and does not write any
formal budget, reimbursement, invoice, expense, payment, or bank record.

For reimbursement and invoice work, read the staged job and submit a
structured extraction. Use only facts present in the user's message or linked
evidence; leave unknown fields empty rather than inventing them:

```bash
python3 {baseDir}/scripts/finance_command_center.py show \
  --job-id <finance job id>

python3 {baseDir}/scripts/finance_command_center.py extract \
  --job-id <finance job id> \
  --payload-json '<structured JSON>' \
  --evidence '<short source reference>' \
  --confidence <0..1> \
  --expected-version <lock version>
```

The extraction is checked by deterministic rules and then moves to
`needs_review`. Soundwave must never review its own extraction; the independent
`inspector` agent performs that step. A failed deterministic check must be
reported as missing or inconsistent information, never bypassed.

During shadow mode, answer with analysis, clarification, or a proposed finance
draft only. Never claim that a budget, reimbursement, invoice, payment, or
reconciliation has been committed. Persist the exact visible answer:

```bash
python3 {baseDir}/scripts/finance_command_center.py respond \
  --message-id <3021 inbound message id> \
  --content "<exact answer sent to the user>"
```

If 3021 rejects the external identity, tell the user that the Feishu identity
must be bound by an administrator. Do not bypass the binding or call the
finance database directly.
