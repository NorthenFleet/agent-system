---
name: memory-context
description: "Use the user-scoped 3021 memory inventory before answering what Optimus remembers or recalling prior decisions, preferences, project context, and experience."
metadata: { "openclaw": { "emoji": "🧠" } }
---

# 3021 Memory Context

3021 is the authoritative memory store. Local Markdown, the OpenClaw lexical
index, and graph-memory are auxiliary channels with independent scopes and
health. A missing daily file, a sandbox error, or `gm_stats` reporting zero
nodes must never be interpreted as 3021 having no memory.

Call this skill before answering any of these requests:

- “你记住了什么 / 有几层记忆 / 你了解我什么”
- “上次我们决定了什么 / 之前做到哪里了”
- a request that relies on remembered preferences, constraints, project
  decisions, or reviewed agent experience
- a claim that memory is missing, disconnected, or empty

Run:

```bash
python3 skills/memory-context/scripts/memory_context.py inspect \
  --query "<original user message, verbatim>"
```

Use this workspace-relative path exactly. In the current protected-skill
sandbox, `{baseDir}` is a read-tool path and is not a valid host `exec` path.

Add `--project-id <id>` only when the current project is known. The script
resolves the current Feishu sender to a bound 3021 profile. Never substitute a
different external user ID or query 3021 directly by guessing an internal ID.

Use the response in this order:

1. `remembered_items` and `retrieval.citations` for claims about remembered
   content.
2. `counts` for inventory totals. Say these are 3021 scoped counts.
3. `channels` and `degraded_channels` for diagnostics. Name the affected
   channel and its impact; do not generalize a channel failure to the whole
   memory system.

There is no fixed universal “four-layer” count. Explain the model as one
authoritative 3021 memory plane plus runtime conversation and auxiliary
retrieval channels. The private graph belongs only to the current agent;
global graph counts are isolated and must not be treated as Optimus memory.

If 3021 rejects the identity, state that the Feishu identity needs an active
administrator binding. If 3021 is unavailable, clearly label the answer as a
degraded local-only view; do not create replacement memory files and do not
claim that canonical memory is empty.

This skill is read-only apart from the audited context-pack snapshot created by
3021. It must not call `gm_record`, edit memory files, or publish a memory
candidate.
