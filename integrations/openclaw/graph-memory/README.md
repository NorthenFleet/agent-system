# 3021 approved-memory bridge

This directory contains the source and tests for the user-scoped graph-memory
bridge deployed into the local OpenClaw `graph-memory` plugin.

Deployment mapping:

- `approved-projection.ts` → `src/http/approved-projection.ts`
- `approved-projection.test.ts` → `test/approved-projection.test.ts`
- `openclaw-plugin-sdk.d.ts` → `src/openclaw-plugin-sdk.d.ts`

The plugin `index.ts` must import and register the route once:

```ts
import { registerApprovedProjectionRoutes } from "./src/http/approved-projection";

registerApprovedProjectionRoutes(api);
```

Use the version-aware deployer instead of copying these files manually:

```bash
python3 integrations/openclaw/graph-memory/deploy.py check
python3 integrations/openclaw/graph-memory/deploy.py deploy --restart
```

`check` exits with status 2 when an OpenClaw upgrade removed the bridge, changed
the plugin version without revalidation, or left stale compiled output. `deploy`
validates the plugin identity and compatible insertion anchors, creates a
recoverable backup, installs the bridge exactly once, builds it, runs the bridge
and dashboard HTTP tests, records the verified plugin version, and only then can
restart the Gateway. A failed build or test restores the backup automatically.
An explicit rollback is also available:

```bash
python3 integrations/openclaw/graph-memory/deploy.py rollback \
  --backup ~/.openclaw/backups/graph-memory-approved-bridge/<backup-id> \
  --restart
```

The bridge stores reviewed projections in
`graph-memory.db.bridge.sqlite`; it does not mix user-scoped content into the
native global or per-agent graph tables.

Schema v2 also exposes the signed, metadata-only
`/graph-memory/v1/projection-inventory` route. It is restricted to the
`memory.read.projection` permission and is used only for canonical/projection
reconciliation; memory content is not returned by this route.

Existing published candidates can be projected idempotently with:

```bash
backend/venv/bin/python backend/scripts/backfill_approved_graph_projections.py
```
