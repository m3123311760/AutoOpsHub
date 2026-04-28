import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

const captured = [];

globalThis.fetch = async (url, options) => {
  captured.push({ url: String(url), options });
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
  };
};

const { authApi, jobApi, runbookApi, taskApi, workpieceApi } = await import("./api.ts");
const { recentTasks, workpieceHref, workpieceRouteParam } = await import("./routes.ts");

afterEach(() => {
  captured.length = 0;
});

test("API clients encode dynamic path segments", async () => {
  await workpieceApi.create("team #1?", "demo");
  await runbookApi.get("team #1?", "deploy/prod?");
  await taskApi.getLogs("team #1?", "task#1?");
  await jobApi.update("team #1?", "nightly#1?", {
    cron: "0 0 * * *",
    enabled: false,
  });

  assert.equal(captured[0].url, "http://localhost:8000/api/workpieces/team%20%231%3F");
  assert.equal(
    captured[1].url,
    "http://localhost:8000/api/workpieces/team%20%231%3F/runbooks/deploy%2Fprod%3F"
  );
  assert.equal(
    captured[2].url,
    "http://localhost:8000/api/workpieces/team%20%231%3F/tasks/task%231%3F/logs"
  );
  assert.equal(
    captured[3].url,
    "http://localhost:8000/api/workpieces/team%20%231%3F/jobs/nightly%231%3F"
  );
});

test("fetcher only sends JSON content type when a body is present", async () => {
  await workpieceApi.list();
  await workpieceApi.create("team", "demo");

  assert.equal(captured[0].options.headers["Content-Type"], undefined);
  assert.equal(captured[1].options.headers["Content-Type"], "application/json");
});

test("auth API clients cover login and API key management", async () => {
  await authApi.login("local", "admin", "secret");
  await authApi.listApiKeys();
  await authApi.createApiKey("ci");
  await authApi.revokeApiKey("key#1?");

  assert.equal(captured[0].url, "http://localhost:8000/api/auth/login");
  assert.equal(captured[0].options.method, "POST");
  assert.deepEqual(JSON.parse(captured[0].options.body), {
    mode: "local",
    username: "admin",
    password: "secret",
  });
  assert.equal(captured[1].url, "http://localhost:8000/api/auth/api-keys");
  assert.equal(captured[1].options?.method, undefined);
  assert.equal(captured[2].url, "http://localhost:8000/api/auth/api-keys");
  assert.equal(captured[2].options.method, "POST");
  assert.equal(
    captured[3].url,
    "http://localhost:8000/api/auth/api-keys/key%231%3F"
  );
  assert.equal(captured[3].options.method, "DELETE");
});

test("workpiece route helper encodes only the workpiece path segment", () => {
  assert.equal(workpieceHref("team #1?"), "/workpieces/team%20%231%3F");
  assert.equal(
    workpieceHref("team #1?", "/runbooks"),
    "/workpieces/team%20%231%3F/runbooks"
  );
  assert.equal(
    workpieceHref("team%ready", "/tasks"),
    "/workpieces/team%25ready/tasks"
  );
});

test("workpiece route params are used without a second decode", () => {
  assert.equal(workpieceRouteParam("team%ready"), "team%ready");
  assert.equal(workpieceRouteParam("team%2Fready"), "team%2Fready");
});

test("recent tasks are sorted by creation time before limiting", () => {
  const tasks = [
    { task_id: "old", created_at: "2026-04-28T01:00:00Z" },
    { task_id: "newest", created_at: "2026-04-28T03:00:00Z" },
    { task_id: "middle", created_at: "2026-04-28T02:00:00Z" },
  ];

  assert.deepEqual(
    recentTasks(tasks, 2).map((task) => task.task_id),
    ["newest", "middle"]
  );
});
