"use client";

import useSWR, { mutate } from "swr";
import { AlertTriangle, Loader2, RefreshCw, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import { taskApi, type LogRecord, type Task } from "@/lib/api";
import { stripAnsi } from "@/lib/ansi";
import { formatDate } from "@/lib/utils";

interface TaskLogPanelProps {
  workpiece: string;
  taskId: string | null;
  initialTask?: Task | null;
}

interface TaskLogDialogProps extends TaskLogPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const terminalStatuses = new Set(["success", "failed", "canceled"]);
const logPageSize = 500;
const maxLogPages = 20;

function logLevelClass(level: LogRecord["level"]) {
  if (level === "error") return "text-red-300";
  if (level === "warn") return "text-amber-300";
  return "text-emerald-200";
}

function shouldPoll(task?: Task | null) {
  return !task || !terminalStatuses.has(task.status);
}

async function fetchTaskLogs(workpiece: string, taskId: string) {
  const items: LogRecord[] = [];
  let after = 0;
  for (let page = 0; page < maxLogPages; page += 1) {
    const response = await taskApi.getLogs(workpiece, taskId, { after, limit: logPageSize });
    items.push(...response.items);
    if (response.items.length < logPageSize) break;
    after = Math.max(...response.items.map((item) => item.log_seq));
  }
  return { items };
}

export function TaskLogPanel({ workpiece, taskId, initialTask }: TaskLogPanelProps) {
  const taskKey = taskId ? ["task-detail", workpiece, taskId] : null;
  const logsKey = taskId ? ["task-logs", workpiece, taskId] : null;

  const { data: task, isLoading: taskLoading } = useSWR(
    taskKey,
    () => taskApi.get(workpiece, taskId as string),
    {
      fallbackData: initialTask || undefined,
      refreshInterval: (current) => (shouldPoll(current) ? 1500 : 0),
    }
  );
  const { data: logs, error: logsError, isLoading: logsLoading } = useSWR(
    logsKey,
    () => fetchTaskLogs(workpiece, taskId as string),
    {
      refreshInterval: () => (shouldPoll(task) ? 1500 : 0),
    }
  );

  const records = logs?.items || [];
  const command = Array.isArray(task?.schedule?.runtime_command)
    ? task.schedule.runtime_command.map(String).join(" ")
    : "";

  const refresh = () => {
    if (taskKey) mutate(taskKey);
    if (logsKey) mutate(logsKey);
  };

  if (!taskId) {
    return <div className="rounded-md border p-4 text-sm text-muted-foreground">未选择任务</div>;
  }

  return (
    <div className="flex min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted/30 p-3">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm">{taskId}</span>
            {task?.status ? <StatusBadge status={task.status} /> : null}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {command || task?.runbook_name || "等待调度信息"}
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新
        </Button>
      </div>

      {task?.error_summary ? (
        <div className="flex gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{task.error_summary}</span>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border bg-zinc-950 text-zinc-100">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
          <div className="flex items-center gap-2 text-sm text-zinc-300">
            <Terminal className="h-4 w-4" />
            实时日志
          </div>
          {taskLoading || logsLoading || shouldPoll(task) ? (
            <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          ) : null}
        </div>
        <div className="h-[min(58vh,620px)] min-h-64 overflow-auto p-4 font-mono text-xs leading-6">
          {logsError ? (
            <div className="text-red-300">日志加载失败</div>
          ) : records.length === 0 ? (
            <div className="text-zinc-500">等待任务输出...</div>
          ) : (
            records.map((record) => (
              <div key={`${record.task_id}-${record.log_seq}`} className="grid grid-cols-[150px_56px_minmax(0,1fr)] gap-3">
                <span className="text-zinc-500">{formatDate(record.ts)}</span>
                <span className={logLevelClass(record.level)}>{record.level}</span>
                <span className="whitespace-pre-wrap break-words">{stripAnsi(record.message)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export function TaskLogDialog({ open, onOpenChange, workpiece, taskId, initialTask }: TaskLogDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="grid max-h-[92vh] max-w-[min(1120px,calc(100vw-2rem))] grid-rows-[auto_minmax(0,1fr)]">
        <DialogHeader>
          <DialogTitle>任务日志</DialogTitle>
          <DialogDescription>{taskId || "等待任务创建"}</DialogDescription>
        </DialogHeader>
        <TaskLogPanel workpiece={workpiece} taskId={taskId} initialTask={initialTask} />
      </DialogContent>
    </Dialog>
  );
}
