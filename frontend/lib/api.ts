const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const pathSegment = (value: string) => encodeURIComponent(value);

async function fetcher<T>(url: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options?.headers,
  };

  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(error.detail || "请求失败");
  }

  if (res.status === 204) {
    return null as T;
  }

  return res.json();
}

// Workpiece APIs
export const workpieceApi = {
  list: () => fetcher<{ items: Workpiece[] }>("/api/workpieces"),
  get: (name: string) => fetcher<WorkpieceDetail>(`/api/workpieces/${pathSegment(name)}`),
  create: (name: string, description: string) =>
    fetcher<Workpiece>(`/api/workpieces/${pathSegment(name)}`, {
      method: "POST",
      body: JSON.stringify({ description }),
    }),
  update: (name: string, data: { name?: string; description?: string }) =>
    fetcher<Workpiece>(`/api/workpieces/${pathSegment(name)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (name: string) =>
    fetcher<null>(`/api/workpieces/${pathSegment(name)}`, { method: "DELETE" }),
  getSetting: (name: string) =>
    fetcher<WorkpieceSetting>(`/api/workpieces/${pathSegment(name)}/setting`),
  updateSetting: (name: string, setting: WorkpieceSetting) =>
    fetcher<WorkpieceSetting>(`/api/workpieces/${pathSegment(name)}/setting`, {
      method: "PUT",
      body: JSON.stringify(setting),
    }),
};

// Runbook APIs
export const runbookApi = {
  list: (workpiece: string) =>
    fetcher<{ items: RunbookSummary[] }>(`/api/workpieces/${pathSegment(workpiece)}/runbooks`),
  get: (workpiece: string, name: string) =>
    fetcher<Runbook>(`/api/workpieces/${pathSegment(workpiece)}/runbooks/${pathSegment(name)}`),
  upsert: (workpiece: string, name: string, data: RunbookUpsertRequest) =>
    fetcher<Runbook>(`/api/workpieces/${pathSegment(workpiece)}/runbooks/${pathSegment(name)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delete: (workpiece: string, name: string) =>
    fetcher<null>(`/api/workpieces/${pathSegment(workpiece)}/runbooks/${pathSegment(name)}`, {
      method: "DELETE",
    }),
  getManifest: (workpiece: string, name: string) =>
    fetcher<{ items: ManifestVariable[] }>(
      `/api/workpieces/${pathSegment(workpiece)}/runbooks/${pathSegment(name)}/manifest`
    ),
  trigger: (workpiece: string, name: string, variables: Record<string, unknown>) =>
    fetcher<TriggerResponse>(`/api/workpieces/${pathSegment(workpiece)}/runbooks/${pathSegment(name)}/trigger`, {
      method: "POST",
      body: JSON.stringify({ variables }),
    }),
};

// Task APIs
export const taskApi = {
  list: (workpiece: string) =>
    fetcher<{ items: TaskSummary[] }>(`/api/workpieces/${pathSegment(workpiece)}/tasks`),
  get: (workpiece: string, taskId: string) =>
    fetcher<Task>(`/api/workpieces/${pathSegment(workpiece)}/tasks/${pathSegment(taskId)}`),
  updateVariables: (workpiece: string, taskId: string, variables: Record<string, unknown>) =>
    fetcher<Task>(`/api/workpieces/${pathSegment(workpiece)}/tasks/${pathSegment(taskId)}/variables`, {
      method: "PUT",
      body: JSON.stringify({ variables }),
    }),
  confirm: (workpiece: string, taskId: string) =>
    fetcher<{ task: Task }>(`/api/workpieces/${pathSegment(workpiece)}/tasks/${pathSegment(taskId)}/confirm`, {
      method: "POST",
    }),
  cancel: (workpiece: string, taskId: string) =>
    fetcher<Task>(`/api/workpieces/${pathSegment(workpiece)}/tasks/${pathSegment(taskId)}/cancel`, {
      method: "POST",
    }),
  getLogs: (workpiece: string, taskId: string) =>
    fetcher<{ items: LogRecord[] }>(`/api/workpieces/${pathSegment(workpiece)}/tasks/${pathSegment(taskId)}/logs`),
};

// Job APIs
export const jobApi = {
  list: (workpiece: string) =>
    fetcher<{ items: Job[] }>(`/api/workpieces/${pathSegment(workpiece)}/jobs`),
  get: (workpiece: string, name: string) =>
    fetcher<Job>(`/api/workpieces/${pathSegment(workpiece)}/jobs/${pathSegment(name)}`),
  upsert: (workpiece: string, name: string, data: JobUpsertRequest) =>
    fetcher<Job>(`/api/workpieces/${pathSegment(workpiece)}/jobs/${pathSegment(name)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (workpiece: string, name: string, data: JobUpsertRequest) =>
    fetcher<Job>(`/api/workpieces/${pathSegment(workpiece)}/jobs/${pathSegment(name)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (workpiece: string, name: string) =>
    fetcher<null>(`/api/workpieces/${pathSegment(workpiece)}/jobs/${pathSegment(name)}`, { method: "DELETE" }),
};

// Auth APIs
export const authApi = {
  login: (mode: "local" | "ldap" | "ad", username: string, password: string) =>
    fetcher<AuthLoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ mode, username, password }),
    }),
  logout: () =>
    fetcher<null>("/api/auth/jwt/revoke", { method: "POST" }),
};

// Types
export interface Workpiece {
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  stats?: {
    runbooks: number;
    tasks: number;
    jobs: number;
    logs: number;
  };
}

export interface WorkpieceDetail extends Workpiece {
  directory: string;
  stats: {
    runbooks: number;
    tasks: number;
    jobs: number;
    logs: number;
  };
}

export interface WorkpieceSetting {
  no_variable_strategy: HandlingStrategy;
  optional_only_strategy: HandlingStrategy;
  ready_strategy: HandlingStrategy;
  required_missing_retention_seconds: number;
}

export interface HandlingStrategy {
  action: "auto_execute" | "auto_cancel" | "schedule_execute" | "schedule_cancel";
  delay_seconds: number;
}

export interface RunbookSummary {
  name: string;
  type: "Terraform" | "Ansible" | "Script" | "Workflow";
  description: string;
  created_at: string;
  updated_at: string;
  manifest_summary: {
    variables: number;
  };
}

export interface Runbook extends RunbookSummary {
  content: string;
  runtime?: string;
}

export interface RunbookUpsertRequest {
  type: "Terraform" | "Ansible" | "Script" | "Workflow";
  description?: string;
  content: string;
  runtime?: string;
  manifest?: ManifestVariable[];
}

export interface ManifestVariable {
  name: string;
  display_name: string;
  direction: "input" | "output";
  required: boolean;
  default_value: string;
}

export interface TaskSummary {
  task_id: string;
  runbook_name: string;
  source: "manual" | "job";
  status: "pending" | "ready" | "running" | "success" | "failed" | "canceled";
  created_at: string;
  updated_at: string;
  variables_summary: {
    count: number;
  };
}

export interface Task extends TaskSummary {
  variables: Record<string, unknown>;
  error_summary: string;
  schedule: Record<string, unknown>;
  exit_code?: number;
  started_at?: string;
  ended_at?: string;
}

export interface TriggerResponse {
  task: Task;
  manifest: ManifestVariable[];
  missing_required: string[];
}

export interface Job {
  job_name: string;
  description: string;
  cron: string;
  runbook_name: string;
  variables: Record<string, unknown>;
  enabled: boolean;
  next_run_at?: string;
  created_at: string;
  updated_at: string;
}

export interface JobUpsertRequest {
  job_name?: string;
  description?: string;
  cron: string;
  runbook_name?: string;
  variables?: Record<string, unknown>;
  enabled?: boolean;
}

export interface LogRecord {
  task_id: string;
  log_seq: number;
  ts: string;
  level: "info" | "warn" | "error";
  message: string;
}

export interface AuthLoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  principal: {
    username: string;
    auth_mode: "local" | "ldap" | "ad";
  };
}

export { fetcher };
