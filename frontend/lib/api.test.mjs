import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { readFileSync } from "node:fs";

const captured = [];
let nextResponse = null;

globalThis.fetch = async (url, options) => {
  captured.push({ url: String(url), options });
  const response = nextResponse || {
    ok: true,
    status: 200,
    json: async () => ({}),
  };
  nextResponse = null;
  return response;
};

const { authApi, jobApi, runbookApi, taskApi, workpieceApi } = await import("./api.ts");
const { stripAnsi } = await import("./ansi.ts");
const { safeLoginRedirectTarget } = await import("./auth-routes.ts");
const { buildInitialManifestValues, collectManifestInputVariables, parseJsonVariableText } = await import("./manifest-form.ts");
const { recentTasks, workpieceHref, workpieceRouteParam } = await import("./routes.ts");

afterEach(() => {
  captured.length = 0;
  nextResponse = null;
  delete globalThis.window;
});

test("API clients encode dynamic path segments", async () => {
  await workpieceApi.create("team #1?", "demo");
  await runbookApi.get("team #1?", "deploy/prod?");
  await taskApi.getLogs("team #1?", "task#1?");
  await taskApi.rerun("task#1?", { region: "west" });
  await taskApi.terraformAction("task#1?", "destroy", { region: "west" });
  await taskApi.getLogs("team #1?", "task#1?", { after: 500, limit: 500 });
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
    "http://localhost:8000/api/tasks/task%231%3F/rerun"
  );
  assert.equal(
    captured[4].url,
    "http://localhost:8000/api/tasks/task%231%3F/terraform/actions"
  );
  assert.equal(
    captured[5].url,
    "http://localhost:8000/api/workpieces/team%20%231%3F/tasks/task%231%3F/logs?after=500&limit=500"
  );
  assert.equal(
    captured[6].url,
    "http://localhost:8000/api/workpieces/team%20%231%3F/jobs/nightly%231%3F"
  );
});

test("task API sends terraform action request body", async () => {
  await taskApi.terraformAction("task-1", "plan", { region: "west" });

  assert.equal(captured[0].options.method, "POST");
  assert.deepEqual(JSON.parse(captured[0].options.body), {
    action: "plan",
    variables: { region: "west" },
  });
});

test("tasks page gates rerun and terraform actions by runbook resolution", () => {
  const source = readFileSync(new URL("../components/tasks-content.tsx", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");

  assert.match(apiSource, /runbook_type: RunbookType \| null/);
  assert.match(apiSource, /runbook_missing: boolean/);
  assert.match(source, /const canCreateFollowUpTask = \(task: TaskSummary \| Task\) => !task\.runbook_missing/);
  assert.match(source, /getTaskRunbookType\(task\) === "Terraform"/);
  assert.match(source, /Runbook 已删除/);
  assert.match(source, /确认 Destroy/);
  assert.match(source, /onAction\(task, "plan"\)/);
  assert.match(source, /onAction\(task, "apply"\)/);
  assert.match(source, /onAction\(task, "output"\)/);
  assert.match(source, /onAction\(task, "destroy"\)/);
});

test("fetcher only sends JSON content type when a body is present", async () => {
  await workpieceApi.list();
  await workpieceApi.create("team", "demo");

  assert.equal(captured[0].options.headers["Content-Type"], undefined);
  assert.equal(captured[1].options.headers["Content-Type"], "application/json");
});

test("runbook API can submit multipart file package upserts without JSON content type", async () => {
  const file = new File(["resource {}"], "main.tf", { type: "text/plain" });

  await runbookApi.upsertFiles("team", "tf-package", {
    type: "Terraform",
    description: "multi",
    entry_file: "main.tf",
    files: [file],
  });

  assert.equal(
    captured[0].url,
    "http://localhost:8000/api/workpieces/team/runbooks/tf-package"
  );
  assert.equal(captured[0].options.method, "POST");
  assert.equal(captured[0].options.headers["Content-Type"], undefined);
  assert.equal(captured[0].options.body instanceof FormData, true);
});

test("runbook file package picker enables directory selection to preserve relative paths", () => {
  const source = readFileSync(new URL("../components/runbooks-content.tsx", import.meta.url), "utf8");

  assert.match(source, /webkitdirectory/);
  assert.match(source, /\bdirectory\b/);
});

test("task log viewer polls incrementally from cached log sequence", () => {
  const source = readFileSync(new URL("../components/task-log-viewer.tsx", import.meta.url), "utf8");

  assert.match(source, /logCacheRef/);
  assert.match(source, /items\.reduce\(\(max, item\) => Math\.max\(max, item\.log_seq\), 0\)/);
  assert.doesNotMatch(source, /let after = 0;/);
});

test("task parameter dialog keeps actions reachable when many variables render", () => {
  const source = readFileSync(new URL("../components/task-parameter-dialog.tsx", import.meta.url), "utf8");

  assert.match(source, /max-h-\[min\(92vh,760px\)\]/);
  assert.match(source, /grid-rows-\[auto_minmax\(0,1fr\)_auto\]/);
  assert.match(source, /overflow-y-auto/);
  assert.match(source, /shrink-0/);
});

test("tasks page exposes direct terraform action controls", () => {
  const source = readFileSync(new URL("../components/tasks-content.tsx", import.meta.url), "utf8");

  assert.match(source, /terraformAction/);
  assert.match(source, /runbookTypeByName/);
  assert.match(source, /getTaskRunbookType/);
  assert.match(source, /Plan/);
  assert.match(source, /Apply/);
  assert.match(source, /Destroy/);
  assert.match(source, /Output/);
  assert.match(source, /确认 Destroy/);
});

test("auth API clients cover login and API key management", async () => {
  await authApi.getAuthStatus();
  await authApi.login("local", "admin", "secret");
  await authApi.listApiKeys();
  await authApi.createApiKey("ci");
  await authApi.revokeApiKey("key#1?");

  assert.equal(captured[0].url, "http://localhost:8000/api/health/auth");
  assert.equal(captured[0].options?.method, undefined);
  assert.equal(captured[1].url, "http://localhost:8000/api/auth/login");
  assert.equal(captured[1].options.method, "POST");
  assert.deepEqual(JSON.parse(captured[1].options.body), {
    mode: "local",
    username: "admin",
    password: "secret",
  });
  assert.equal(captured[2].url, "http://localhost:8000/api/auth/api-keys");
  assert.equal(captured[2].options?.method, undefined);
  assert.equal(captured[3].url, "http://localhost:8000/api/auth/api-keys");
  assert.equal(captured[3].options.method, "POST");
  assert.equal(
    captured[4].url,
    "http://localhost:8000/api/auth/api-keys/key%231%3F"
  );
  assert.equal(captured[4].options.method, "DELETE");
});

test("fetcher redirects protected 401 responses to login with a return path", async () => {
  const removed = [];
  globalThis.window = {
    location: {
      pathname: "/workpieces/team",
      search: "?tab=jobs",
      href: "",
    },
    localStorage: {
      getItem: (key) => (key === "token" ? "stale-token" : null),
      removeItem: (key) => removed.push(key),
    },
  };
  nextResponse = {
    ok: false,
    status: 401,
    json: async () => ({ detail: "认证失败" }),
  };

  await assert.rejects(() => workpieceApi.list(), /认证失败/);

  assert.deepEqual(removed, [
    "token",
    "token_expires_at",
    "principal_username",
    "auth_mode",
  ]);
  assert.equal(
    globalThis.window.location.href,
    "/login?next=%2Fworkpieces%2Fteam%3Ftab%3Djobs"
  );
});

test("login 401 responses stay on the login page for inline errors", async () => {
  globalThis.window = {
    location: {
      pathname: "/login",
      search: "",
      href: "",
    },
    localStorage: {
      getItem: () => null,
      removeItem: () => {},
    },
  };
  nextResponse = {
    ok: false,
    status: 401,
    json: async () => ({ detail: "认证失败" }),
  };

  await assert.rejects(() => authApi.login("local", "admin", "bad"), /认证失败/);

  assert.equal(globalThis.window.location.href, "");
});

test("login redirect target only allows local absolute paths", () => {
  assert.equal(safeLoginRedirectTarget("/workpieces/team?tab=jobs"), "/workpieces/team?tab=jobs");
  assert.equal(safeLoginRedirectTarget("javascript:alert(1)"), "/");
  assert.equal(safeLoginRedirectTarget("https://evil.example/phish"), "/");
  assert.equal(safeLoginRedirectTarget("//evil.example/phish"), "/");
  assert.equal(safeLoginRedirectTarget("workpieces/team"), "/");
  assert.equal(safeLoginRedirectTarget(null), "/");
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

test("manifest form helpers initialize defaults and collect editable input variables", () => {
  const manifest = [
    { name: "environment", direction: "input", default_value: "local" },
    { name: "system.host", direction: "input", default_value: "localhost" },
    { name: "system.set_runtime", direction: "input", default_value: "terraform apply" },
    { name: "system.output", direction: "output", default_value: "" },
  ];

  const values = buildInitialManifestValues(manifest);
  values["system.set_runtime"] = "";
  assert.deepEqual(values, {
    environment: "local",
    "system.host": "localhost",
    "system.set_runtime": "",
    "system.output": "",
  });

  assert.deepEqual(collectManifestInputVariables(manifest, values), {
    environment: "local",
    "system.host": "localhost",
    "system.set_runtime": "",
  });
});

test("manifest form helper reports malformed fallback JSON as a validation error", () => {
  assert.deepEqual(parseJsonVariableText('{"region":"west"}'), { region: "west" });
  assert.throws(() => parseJsonVariableText('{"region":'), /有效 JSON/);
});

test("stripAnsi removes terminal color and style escape sequences", () => {
  assert.equal(
    stripAnsi("\u001b[0m\u001b[1mInitializing the backend...\u001b[0m"),
    "Initializing the backend..."
  );
  assert.equal(stripAnsi("  \u001b[32m+\u001b[0m create"), "  + create");
});
