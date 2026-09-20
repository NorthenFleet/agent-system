import { DatabaseSync, type DatabaseSyncInstance } from "@photostructure/sqlite";
import { createHash, createHmac, randomUUID, timingSafeEqual } from "crypto";
import { existsSync, readFileSync, statSync } from "fs";
import type { IncomingMessage, ServerResponse } from "http";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { resolvePath } from "../store/db";

const RETRIEVE_PATH = "/graph-memory/v1/retrieve-context";
const UPSERT_PATH = "/graph-memory/v1/upsert-projection";
const INVENTORY_PATH = "/graph-memory/v1/projection-inventory";
const DEFAULT_SECRET_PATH = "~/.openclaw/graph-memory-bridge.key";
const MAX_BODY_BYTES = 1_000_000;
const VALID_VISIBILITIES = new Set(["profile", "project", "agent"]);
const VALID_EVENTS = new Set(["memory.published", "memory.superseded", "memory.archived"]);

class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type Identity = { actorId: string; permissions: Set<string>; requestId: string };

function header(req: IncomingMessage, name: string): string {
  const raw = req.headers[name.toLowerCase()];
  return Array.isArray(raw) ? raw[0] ?? "" : raw ?? "";
}

function canonicalRequest(
  method: string, rawUrl: string, timestamp: string, nonce: string,
  requestId: string, actorId: string, actorRole: string,
  permissions: string, bodySha256: string,
): string {
  return [method.toUpperCase(), rawUrl, timestamp, nonce, requestId, actorId,
    actorRole, permissions, bodySha256].join("\n");
}

function projectionDb(rootDb: string): DatabaseSyncInstance {
  const db = new DatabaseSync(`${rootDb}.bridge.sqlite`);
  db.exec(`PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS gm_bridge_nonces (
      nonce TEXT PRIMARY KEY, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS gm_approved_projections (
      projection_id TEXT PRIMARY KEY,
      event_id TEXT NOT NULL UNIQUE,
      source_ref TEXT NOT NULL UNIQUE,
      owner_user_id TEXT NOT NULL,
      project_id TEXT NOT NULL DEFAULT '',
      agent_id TEXT NOT NULL DEFAULT '',
      visibility TEXT NOT NULL,
      memory_key TEXT NOT NULL DEFAULT '',
      title TEXT NOT NULL,
      content TEXT NOT NULL,
      importance TEXT NOT NULL DEFAULT 'normal',
      confidence REAL NOT NULL DEFAULT 0.8,
      version INTEGER NOT NULL DEFAULT 0,
      supersedes_ref TEXT,
      evidence_refs TEXT NOT NULL DEFAULT '[]',
      content_hash TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active',
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_gm_approved_scope
      ON gm_approved_projections(owner_user_id,visibility,project_id,agent_id,status);
  `);
  const columns = new Set(
    (db.prepare("PRAGMA table_info(gm_approved_projections)").all() as any[])
      .map(row => String(row.name)),
  );
  if (!columns.has("content_hash")) {
    db.exec("ALTER TABLE gm_approved_projections ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''");
  }
  return db;
}

async function readBody(req: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const value = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += value.length;
    if (size > MAX_BODY_BYTES) throw new HttpError(413, "request too large");
    chunks.push(value);
  }
  return Buffer.concat(chunks);
}

function secret(pathInput: string): Buffer {
  const path = resolvePath(pathInput);
  if (!existsSync(path)) throw new HttpError(503, "memory bridge unavailable");
  const stat = statSync(path);
  if ((stat.mode & 0o077) !== 0) throw new HttpError(503, "memory bridge unavailable");
  const value = readFileSync(path);
  if (value.length < 32) throw new HttpError(503, "memory bridge unavailable");
  return value;
}

function verify(
  req: IncomingMessage, body: Buffer, rootDb: string, secretPath: string,
  maxSkewSeconds: number, requiredPermission: string,
): Identity {
  const timestamp = header(req, "x-gm-timestamp");
  const nonce = header(req, "x-gm-nonce");
  const requestId = header(req, "x-gm-request-id");
  const actorId = header(req, "x-gm-actor-id");
  const actorRole = header(req, "x-gm-actor-role");
  const permissions = header(req, "x-gm-permissions");
  const suppliedBodyHash = header(req, "x-gm-body-sha256");
  const signature = header(req, "x-gm-signature");
  const bodyHash = createHash("sha256").update(body).digest("hex");
  if (!/^\d{10}$/.test(timestamp) || !/^[A-Za-z0-9_-]{16,128}$/.test(nonce)
      || !/^[A-Za-z0-9_-]{8,128}$/.test(requestId) || !actorId || !actorRole
      || !/^[a-f0-9]{64}$/i.test(signature) || suppliedBodyHash !== bodyHash) {
    throw new HttpError(401, "unauthorized");
  }
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - Number(timestamp)) > maxSkewSeconds) throw new HttpError(401, "unauthorized");
  const expected = createHmac("sha256", secret(secretPath))
    .update(canonicalRequest(req.method ?? "POST", req.url ?? "", timestamp, nonce,
      requestId, actorId, actorRole, permissions, bodyHash))
    .digest();
  const received = Buffer.from(signature, "hex");
  if (received.length !== expected.length || !timingSafeEqual(received, expected)) {
    throw new HttpError(401, "unauthorized");
  }
  const permissionSet = new Set(permissions.split(",").map(value => value.trim()).filter(Boolean));
  if (!permissionSet.has(requiredPermission)) throw new HttpError(403, "forbidden");
  const db = projectionDb(rootDb);
  try {
    const nowMs = Date.now();
    db.prepare("DELETE FROM gm_bridge_nonces WHERE expires_at<?").run(nowMs);
    try {
      db.prepare("INSERT INTO gm_bridge_nonces(nonce,expires_at,created_at) VALUES(?,?,?)")
        .run(nonce, nowMs + maxSkewSeconds * 1000, nowMs);
    } catch {
      throw new HttpError(401, "unauthorized");
    }
  } finally { db.close(); }
  return { actorId, permissions: permissionSet, requestId };
}

function objectBody(body: Buffer): Record<string, any> {
  try {
    const parsed = JSON.parse(body.toString("utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    return parsed;
  } catch { throw new HttpError(400, "invalid JSON body"); }
}

function requiredText(payload: Record<string, any>, key: string, max = 20_000): string {
  const value = String(payload[key] ?? "").trim();
  if (!value) throw new HttpError(400, `missing ${key}`);
  return value.slice(0, max);
}

function upsert(rootDb: string, payload: Record<string, any>): Record<string, unknown> {
  const eventId = requiredText(payload, "event_id", 200);
  const eventType = requiredText(payload, "event_type", 80);
  if (!VALID_EVENTS.has(eventType)) throw new HttpError(400, "invalid event_type");
  const sourceRef = requiredText(payload, "source_ref", 500);
  const userId = requiredText(payload, "user_id", 160);
  const visibility = requiredText(payload, "visibility", 40);
  if (!VALID_VISIBILITIES.has(visibility)) throw new HttpError(400, "invalid visibility");
  const title = requiredText(payload, "title", 300);
  const content = requiredText(payload, "content", 20_000);
  const now = Date.now();
  const projectionId = `approved-${createHash("sha256").update(sourceRef).digest("hex").slice(0, 24)}`;
  const db = projectionDb(rootDb);
  try {
    const replay = db.prepare("SELECT projection_id FROM gm_approved_projections WHERE event_id=?").get(eventId) as any;
    if (replay) return { status: "already_applied", projection_id: replay.projection_id };
    const existing = db.prepare("SELECT created_at FROM gm_approved_projections WHERE source_ref=?").get(sourceRef) as any;
    const status = eventType === "memory.archived" ? "archived" : String(payload.status ?? "active").slice(0, 40);
    db.prepare(`INSERT INTO gm_approved_projections
      (projection_id,event_id,source_ref,owner_user_id,project_id,agent_id,visibility,
       memory_key,title,content,importance,confidence,version,supersedes_ref,
       evidence_refs,content_hash,status,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(source_ref) DO UPDATE SET
        event_id=excluded.event_id,owner_user_id=excluded.owner_user_id,
        project_id=excluded.project_id,agent_id=excluded.agent_id,
        visibility=excluded.visibility,memory_key=excluded.memory_key,title=excluded.title,
        content=excluded.content,importance=excluded.importance,
        confidence=excluded.confidence,version=excluded.version,
        supersedes_ref=excluded.supersedes_ref,evidence_refs=excluded.evidence_refs,
        content_hash=excluded.content_hash,
        status=excluded.status,updated_at=excluded.updated_at`).run(
      projectionId, eventId, sourceRef, userId,
      String(payload.project_id ?? "").slice(0, 160),
      String(payload.agent_id ?? "").slice(0, 160), visibility,
      String(payload.memory_key ?? "").slice(0, 200), title, content,
      String(payload.importance ?? "normal").slice(0, 40),
      Math.max(0, Math.min(Number(payload.confidence ?? 0.8), 1)),
      Math.max(0, Number(payload.version ?? 0) || 0),
      payload.supersedes_ref ? String(payload.supersedes_ref).slice(0, 500) : null,
      JSON.stringify(Array.isArray(payload.evidence_refs) ? payload.evidence_refs.slice(0, 20) : []),
      String(payload.content_hash ?? "").slice(0, 128),
      status, existing?.created_at ?? now, now,
    );
    return { status: existing ? "upserted" : "accepted", projection_id: projectionId };
  } finally { db.close(); }
}

function inventory(rootDb: string, payload: Record<string, any>): Record<string, unknown> {
  const userId = String(payload.user_id ?? "").trim().slice(0, 160);
  const limit = Math.max(1, Math.min(Number(payload.limit ?? 5000) || 5000, 5000));
  const db = projectionDb(rootDb);
  try {
    const rows = (userId
      ? db.prepare(`SELECT source_ref,owner_user_id,project_id,agent_id,visibility,
          memory_key,content_hash,status,version,updated_at
          FROM gm_approved_projections WHERE owner_user_id=?
          ORDER BY source_ref LIMIT ?`).all(userId, limit)
      : db.prepare(`SELECT source_ref,owner_user_id,project_id,agent_id,visibility,
          memory_key,content_hash,status,version,updated_at
          FROM gm_approved_projections ORDER BY source_ref LIMIT ?`).all(limit)) as any[];
    return { items: rows, count: rows.length, truncated: rows.length >= limit };
  } finally { db.close(); }
}

function retrieve(rootDb: string, payload: Record<string, any>): Record<string, unknown> {
  const userId = requiredText(payload, "user_id", 160);
  const query = requiredText(payload, "query", 20_000).toLowerCase();
  const projectId = String(payload.project_id ?? "").slice(0, 160);
  const agentId = String(payload.agent_id ?? "").slice(0, 160);
  const limit = Math.max(1, Math.min(Number(payload.limit ?? 8) || 8, 20));
  const allowedScopes = new Set(
    (Array.isArray(payload.allowed_scopes) ? payload.allowed_scopes : ["profile", "project", "agent"])
      .map((value: unknown) => String(value)).filter(value => VALID_VISIBILITIES.has(value)),
  );
  const db = projectionDb(rootDb);
  try {
    const rows = db.prepare(`SELECT * FROM gm_approved_projections
      WHERE owner_user_id=? AND status='active'
        AND (visibility='profile'
          OR (visibility='project' AND project_id=?)
          OR (visibility='agent' AND agent_id=? AND (project_id='' OR project_id=?)))
      ORDER BY CASE importance WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
        updated_at DESC LIMIT 200`).all(userId, projectId, agentId, projectId) as any[];
    const terms = Array.from(new Set([
      query,
      ...(query.match(/[a-z0-9_.:/-]{2,}|[\u4e00-\u9fff]{2,}/g) ?? []),
    ].filter(Boolean))).slice(0, 16);
    const scored = rows.filter(row => allowedScopes.has(String(row.visibility))).map(row => {
      const haystack = `${row.memory_key} ${row.title} ${row.content}`.toLowerCase();
      const overlap = terms.filter(term => haystack.includes(term)).length;
      const base = row.importance === "critical" ? 0.94 : row.importance === "high" ? 0.86 : 0.72;
      return { row, score: Math.min(0.99, base + overlap * 0.02) };
    }).sort((a, b) => b.score - a.score || b.row.updated_at - a.row.updated_at).slice(0, limit);
    return {
      retrieval_mode: "approved-projection-sqlite",
      items: scored.map(({ row, score }) => ({
        node_id: row.projection_id,
        source_ref: row.source_ref,
        title: row.title,
        content: row.content,
        authority: "approved_projection",
        visibility: row.visibility,
        owner_user_id: row.owner_user_id,
        project_id: row.project_id,
        agent_id: row.agent_id,
        memory_key: row.memory_key,
        score,
        confidence: row.confidence,
        freshness_score: 0.8,
        relation_relevance: 0.5,
        version: row.version,
        supersedes_ref: row.supersedes_ref,
        evidence_refs: JSON.parse(row.evidence_refs || "[]"),
        relations: [],
      })),
    };
  } finally { db.close(); }
}

function writeJson(res: ServerResponse, status: number, body: unknown): true {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.end(JSON.stringify(body));
  return true;
}

export function registerApprovedProjectionRoutes(api: OpenClawPluginApi): void {
  const rootDb = resolvePath(String(api.pluginConfig?.dbPath ?? "~/.openclaw/graph-memory.db"));
  const secretPath = String(api.pluginConfig?.dashboardBridgeSecretPath ?? DEFAULT_SECRET_PATH);
  const maxSkewSeconds = Math.max(15, Math.min(
    Number(api.pluginConfig?.dashboardBridgeMaxSkewSeconds ?? 60), 300,
  ));
  for (const [path, permission] of [
    [RETRIEVE_PATH, "memory.retrieve.context"],
    [UPSERT_PATH, "memory.write.projection"],
    [INVENTORY_PATH, "memory.read.projection"],
  ] as const) {
    api.registerHttpRoute({
      path, auth: "plugin", match: "exact",
      handler: async (req, res) => {
        try {
          if ((req.method ?? "").toUpperCase() !== "POST") throw new HttpError(405, "method not allowed");
          const body = await readBody(req);
          verify(req, body, rootDb, secretPath, maxSkewSeconds, permission);
          const payload = objectBody(body);
          return writeJson(
            res,
            200,
            path === UPSERT_PATH
              ? upsert(rootDb, payload)
              : path === INVENTORY_PATH
                ? inventory(rootDb, payload)
                : retrieve(rootDb, payload),
          );
        } catch (error) {
          const status = error instanceof HttpError ? error.status : 500;
          if (status >= 500) api.logger.error(`[graph-memory] approved projection bridge failed request=${header(req, "x-gm-request-id") || randomUUID()}`);
          return writeJson(res, status, {
            detail: status === 401 ? "unauthorized" : status === 403 ? "forbidden"
              : status === 405 ? "method not allowed" : status === 503 ? "memory bridge unavailable"
              : status === 413 ? "request too large" : status === 400 ? String((error as Error).message)
              : "memory projection failed",
          });
        }
      },
    });
  }
}
