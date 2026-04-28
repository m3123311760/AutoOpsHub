const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Token management
function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token');
}

function setToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('auth_token', token);
  }
}

function removeToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('auth_token');
  }
}

function getAuthHeaders(): HeadersInit {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    removeToken();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    throw new Error('Unauthorized');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }
  if (response.status === 204) {
    return {} as T;
  }
  return response.json();
}

// Auth API
export interface LoginRequest {
  mode: 'local' | 'ldap' | 'ad';
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  principal: {
    username: string;
    auth_mode: string;
  };
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  revoked_at: string | null;
  api_key?: string;
}

export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await handleResponse<LoginResponse>(response);
    setToken(result.access_token);
    return result;
  },

  logout: async (): Promise<void> => {
    try {
      await fetch(`${API_BASE_URL}/api/auth/jwt/revoke`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
    } finally {
      removeToken();
    }
  },

  listApiKeys: async (): Promise<{ items: ApiKey[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/api-keys`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  createApiKey: async (name: string): Promise<ApiKey> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/api-keys`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ name }),
    });
    return handleResponse(response);
  },

  revokeApiKey: async (keyId: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/api-keys/${keyId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  isAuthenticated: (): boolean => {
    return !!getToken();
  },

  getToken,
  removeToken,
};

// Workpiece types and API
export interface WorkpieceMeta {
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

export interface WorkpieceDetail extends WorkpieceMeta {
  directory: string;
  stats: {
    runbooks: number;
    tasks: number;
    jobs: number;
    logs: number;
  };
}

export interface WorkpieceSetting {
  no_variable_strategy: {
    action: 'auto_execute' | 'auto_cancel' | 'schedule_execute' | 'schedule_cancel';
    delay_seconds: number;
  };
  optional_only_strategy: {
    action: 'auto_execute' | 'auto_cancel' | 'schedule_execute' | 'schedule_cancel';
    delay_seconds: number;
  };
  ready_strategy: {
    action: 'auto_execute' | 'auto_cancel' | 'schedule_execute' | 'schedule_cancel';
    delay_seconds: number;
  };
  required_missing_retention_seconds: number;
}

export const workpieceApi = {
  list: async (): Promise<{ items: WorkpieceMeta[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  get: async (name: string): Promise<WorkpieceDetail> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${name}`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  create: async (name: string, description: string = ''): Promise<WorkpieceMeta> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${name}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ description }),
    });
    return handleResponse(response);
  },

  update: async (name: string, data: { name?: string; description?: string }): Promise<WorkpieceMeta> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${name}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  },

  delete: async (name: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${name}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  getSetting: async (name: string): Promise<WorkpieceSetting> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${name}/setting`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  updateSetting: async (name: string, setting: WorkpieceSetting): Promise<WorkpieceSetting> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${name}/setting`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify(setting),
    });
    return handleResponse(response);
  },
};

// Runbook types and API
export interface ManifestVariable {
  name: string;
  display_name: string;
  direction: 'input' | 'output';
  required: boolean;
  default_value: string;
}

export interface RunbookSummary {
  name: string;
  type: 'Terraform' | 'Ansible' | 'Script' | 'Workflow';
  description: string;
  created_at: string;
  updated_at: string;
  manifest_summary: {
    variables: number;
  };
}

export interface RunbookDetail {
  name: string;
  type: 'Terraform' | 'Ansible' | 'Script' | 'Workflow';
  description: string;
  content: string;
  runtime: string | null;
  created_at: string;
  updated_at: string;
}

export const runbookApi = {
  list: async (workpiece: string): Promise<{ items: RunbookSummary[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/runbooks`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  getManifest: async (workpiece: string, runbookName: string): Promise<{ items: ManifestVariable[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/runbooks/${runbookName}/manifest`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  create: async (
    workpiece: string,
    name: string,
    data: {
      type: 'Terraform' | 'Ansible' | 'Script' | 'Workflow';
      description?: string;
      content: string;
      runtime?: string;
      manifest?: ManifestVariable[];
    }
  ): Promise<RunbookSummary> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/runbooks/${name}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  },

  delete: async (workpiece: string, name: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/runbooks/${name}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  trigger: async (
    workpiece: string,
    name: string,
    variables: Record<string, unknown> = {}
  ): Promise<{ task: TaskRecord; manifest: ManifestVariable[]; missing_required: string[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/runbooks/${name}/trigger`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ variables }),
    });
    return handleResponse(response);
  },
};

// Task types and API
export interface TaskRecord {
  task_id: string;
  source: 'manual' | 'job';
  runbook_name: string;
  variables: Record<string, unknown>;
  status: 'pending' | 'ready' | 'running' | 'success' | 'failed' | 'canceled';
  error_summary: string;
  schedule: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  exit_code: number | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface TaskSummary {
  task_id: string;
  runbook_name: string;
  source: 'manual' | 'job';
  status: 'pending' | 'ready' | 'running' | 'success' | 'failed' | 'canceled';
  created_at: string;
  updated_at: string;
  variables_summary: {
    count: number;
  };
}

export interface LogRecord {
  task_id: string;
  log_seq: number;
  ts: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export const taskApi = {
  list: async (workpiece: string): Promise<{ items: TaskSummary[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/tasks`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  get: async (workpiece: string, taskId: string): Promise<TaskRecord> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/tasks/${taskId}`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  updateVariables: async (
    workpiece: string,
    taskId: string,
    variables: Record<string, unknown>
  ): Promise<TaskRecord> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/tasks/${taskId}/variables`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({ variables }),
    });
    return handleResponse(response);
  },

  confirm: async (workpiece: string, taskId: string): Promise<{ task: TaskRecord }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/tasks/${taskId}/confirm`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  cancel: async (workpiece: string, taskId: string): Promise<TaskRecord> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/tasks/${taskId}/cancel`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  getLogs: async (workpiece: string, taskId: string, after: number = 0, limit: number = 200): Promise<{ items: LogRecord[] }> => {
    const response = await fetch(
      `${API_BASE_URL}/api/workpieces/${workpiece}/tasks/${taskId}/logs?after=${after}&limit=${limit}`,
      { headers: getAuthHeaders() }
    );
    return handleResponse(response);
  },

  streamLogs: (workpiece: string, taskId: string): EventSource => {
    const token = getToken();
    const url = `${API_BASE_URL}/api/workpieces/${workpiece}/tasks/${taskId}/logs/stream?follow=1`;
    return new EventSource(url);
  },
};

// Job types and API
export interface JobRecord {
  job_name: string;
  description: string;
  cron: string;
  runbook_name: string;
  variables: Record<string, unknown>;
  enabled: boolean;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  job_name: string;
  description: string;
  cron: string;
  runbook_name: string;
  enabled: boolean;
  next_run_at: string | null;
}

export const jobApi = {
  list: async (workpiece: string): Promise<{ items: JobSummary[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/jobs`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  get: async (workpiece: string, jobName: string): Promise<JobRecord> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/jobs/${jobName}`, {
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  create: async (
    workpiece: string,
    jobName: string,
    data: {
      description?: string;
      cron: string;
      runbook_name: string;
      variables?: Record<string, unknown>;
      enabled?: boolean;
    }
  ): Promise<JobRecord> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/jobs/${jobName}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  },

  update: async (
    workpiece: string,
    jobName: string,
    data: {
      job_name?: string;
      description?: string;
      cron: string;
      runbook_name?: string;
      variables?: Record<string, unknown>;
      enabled?: boolean;
    }
  ): Promise<JobRecord> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/jobs/${jobName}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  },

  delete: async (workpiece: string, jobName: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/jobs/${jobName}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },

  trigger: async (
    workpiece: string,
    jobName: string
  ): Promise<{ task: TaskRecord; manifest: ManifestVariable[]; missing_required: string[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/workpieces/${workpiece}/jobs/${jobName}/trigger`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    return handleResponse(response);
  },
};

// Health API
export const healthApi = {
  logging: async (): Promise<{
    backend_type: string;
    redis_configured: boolean;
    redis_reachable: boolean;
    degrade_reason: string | null;
    non_persistent_note: string;
  }> => {
    const response = await fetch(`${API_BASE_URL}/api/health/logging`);
    return handleResponse(response);
  },
};
