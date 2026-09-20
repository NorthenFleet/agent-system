import { afterEach, describe, expect, it } from "vitest";
import { createHash, createHmac, randomUUID } from "crypto";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { Readable } from "stream";
import { registerApprovedProjectionRoutes } from "../src/http/approved-projection";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function fixture() {
  const dir = mkdtempSync(join(tmpdir(), "gm-approved-projection-"));
  roots.push(dir);
  const rootDb = join(dir, "graph-memory.db");
  const secretPath = join(dir, "bridge.key");
  const secret = "0123456789abcdef0123456789abcdef0123456789abcdef";
  writeFileSync(secretPath, secret);
  chmodSync(secretPath, 0o600);
  const routes = new Map<string, any>();
  registerApprovedProjectionRoutes({
    pluginConfig: { dbPath: rootDb, dashboardBridgeSecretPath: secretPath },
    registerHttpRoute(value: any) { routes.set(value.path, value); },
    logger: { error() {} },
  } as any);
  return { routes, secret };
}

function request(secret: string, path: string, permission: string, payload: Record<string, unknown>) {
  const body = Buffer.from(JSON.stringify(payload));
  const bodyHash = createHash("sha256").update(body).digest("hex");
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID().replaceAll("-", "");
  const requestId = randomUUID().replaceAll("-", "");
  const actorId = "3021-context";
  const actorRole = "service";
  const signature = createHmac("sha256", secret).update([
    "POST", path, timestamp, nonce, requestId, actorId, actorRole, permission, bodyHash,
  ].join("\n")).digest("hex");
  const req: any = Readable.from([body]);
  req.method = "POST";
  req.url = path;
  req.headers = {
    "x-gm-timestamp": timestamp,
    "x-gm-nonce": nonce,
    "x-gm-request-id": requestId,
    "x-gm-actor-id": actorId,
    "x-gm-actor-role": actorRole,
    "x-gm-permissions": permission,
    "x-gm-body-sha256": bodyHash,
    "x-gm-signature": signature,
  };
  return req;
}

function response() {
  return {
    statusCode: 0,
    body: "",
    headers: {} as Record<string, string>,
    setHeader(name: string, value: string) { this.headers[name] = value; },
    end(value: string) { this.body = value; },
  } as any;
}

describe("approved projection bridge", () => {
  it("upserts idempotently and retrieves only the requested user and scope", async () => {
    const { routes, secret } = fixture();
    const upsertPath = "/graph-memory/v1/upsert-projection";
    const retrievePath = "/graph-memory/v1/retrieve-context";
    const projection = {
      event_id: "event-1",
      event_type: "memory.published",
      aggregate_type: "project_memory",
      aggregate_id: "memory-1",
      source_ref: "project-memory:memory-1",
      user_id: "user-1",
      project_id: "project-1",
      agent_id: "optimus",
      visibility: "project",
      memory_key: "decision.approval",
      title: "审批约束",
      content: "计划必须批准后执行。",
      importance: "critical",
      confidence: 0.98,
      version: 1,
      status: "active",
      evidence_refs: ["mission:1"],
      content_hash: "hash-project-memory-1",
    };
    const upsertRes = response();
    await routes.get(upsertPath).handler(
      request(secret, upsertPath, "memory.write.projection", projection), upsertRes,
    );
    expect(upsertRes.statusCode).toBe(200);
    expect(JSON.parse(upsertRes.body).status).toBe("accepted");

    const replayRes = response();
    await routes.get(upsertPath).handler(
      request(secret, upsertPath, "memory.write.projection", projection), replayRes,
    );
    expect(JSON.parse(replayRes.body).status).toBe("already_applied");

    const retrieveRes = response();
    await routes.get(retrievePath).handler(request(
      secret, retrievePath, "memory.retrieve.context",
      { user_id: "user-1", project_id: "project-1", agent_id: "optimus", query: "审批", limit: 8 },
    ), retrieveRes);
    expect(retrieveRes.statusCode).toBe(200);
    expect(JSON.parse(retrieveRes.body).items).toMatchObject([{
      source_ref: "project-memory:memory-1",
      authority: "approved_projection",
      owner_user_id: "user-1",
      visibility: "project",
    }]);

    const otherUser = response();
    await routes.get(retrievePath).handler(request(
      secret, retrievePath, "memory.retrieve.context",
      { user_id: "user-2", project_id: "project-1", agent_id: "optimus", query: "审批" },
    ), otherUser);
    expect(JSON.parse(otherUser.body).items).toEqual([]);

    const otherProject = response();
    await routes.get(retrievePath).handler(request(
      secret, retrievePath, "memory.retrieve.context",
      { user_id: "user-1", project_id: "project-2", agent_id: "optimus", query: "审批" },
    ), otherProject);
    expect(JSON.parse(otherProject.body).items).toEqual([]);

    const inventoryPath = "/graph-memory/v1/projection-inventory";
    const inventoryRes = response();
    await routes.get(inventoryPath).handler(request(
      secret, inventoryPath, "memory.read.projection", { user_id: "user-1" },
    ), inventoryRes);
    expect(inventoryRes.statusCode).toBe(200);
    expect(JSON.parse(inventoryRes.body).items).toMatchObject([{
      source_ref: "project-memory:memory-1",
      owner_user_id: "user-1",
      project_id: "project-1",
      content_hash: "hash-project-memory-1",
      status: "active",
    }]);
  });

  it("rejects unsigned requests", async () => {
    const { routes } = fixture();
    const req: any = Readable.from([Buffer.from("{}")]);
    req.method = "POST";
    req.url = "/graph-memory/v1/retrieve-context";
    req.headers = {};
    const res = response();
    await routes.get(req.url).handler(req, res);
    expect(res.statusCode).toBe(401);
  });
});
