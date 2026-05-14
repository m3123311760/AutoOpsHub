"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  ListTodo,
  Play,
  XCircle,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Loader2,
  RefreshCw,
  Eye,
  X,
  Terminal,
  RotateCcw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { TaskLogPanel, TaskLogDialog } from "@/components/task-log-viewer";
import { TaskParameterDialog } from "@/components/task-parameter-dialog";
import { runbookApi, taskApi, type ManifestVariable, type TaskSummary, type Task, type TerraformTaskAction } from "@/lib/api";
import { formatDate } from "@/lib/utils";

interface TasksContentProps {
  workpiece: string;
}

export function TasksContent({ workpiece }: TasksContentProps) {
  const { data, error, isLoading } = useSWR(
    `tasks-${workpiece}`,
    () => taskApi.list(workpiece),
    { refreshInterval: 5000 }
  );
  const { data: runbooksData } = useSWR(
    `runbooks-${workpiece}`,
    () => runbookApi.list(workpiece),
    { refreshInterval: 10000 }
  );

  const [detailOpen, setDetailOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [logTask, setLogTask] = useState<Task | null>(null);
  const [rerunTask, setRerunTask] = useState<Task | null>(null);
  const [rerunManifest, setRerunManifest] = useState<ManifestVariable[]>([]);
  const [rerunError, setRerunError] = useState("");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [destroyTask, setDestroyTask] = useState<TaskSummary | Task | null>(null);
  const [taskActionError, setTaskActionError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const tasks = data?.items || [];
  const runbookTypeByName = new Map((runbooksData?.items || []).map((runbook) => [runbook.name, runbook.type]));
  const getTaskRunbookType = (task: TaskSummary | Task) =>
    task.runbook_missing ? undefined : task.runbook_type || runbookTypeByName.get(task.runbook_name);

  // Sort by created_at desc
  const sortedTasks = [...tasks].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const canCreateFollowUpTask = (task: TaskSummary | Task) => !task.runbook_missing;
  const isTerraformTask = (task: TaskSummary | Task) =>
    canCreateFollowUpTask(task) && getTaskRunbookType(task) === "Terraform";

  const loadTaskDetail = async (taskId: string) => {
    try {
      setTaskActionError("");
      const task = await taskApi.get(workpiece, taskId);
      setSelectedTask(task);
      setDetailOpen(true);
    } catch (err) {
      console.error("加载任务详情失败:", err);
    }
  };

  const openTaskLog = async (taskId: string) => {
    try {
      const task = await taskApi.get(workpiece, taskId);
      setLogTask(task);
      setLogOpen(true);
    } catch (err) {
      console.error("加载任务日志失败:", err);
    }
  };

  const openRerunDialog = async (taskId: string) => {
    setIsSubmitting(true);
    setRerunError("");
    setRerunManifest([]);
    setRerunTask(null);
    try {
      const task = await taskApi.get(workpiece, taskId);
      if (task.runbook_missing) {
        setRerunTask(task);
        setRerunError("关联的运行手册已删除，不能重新运行该历史任务");
        setRerunOpen(true);
        return;
      }
      const manifest = await runbookApi.getManifest(workpiece, task.runbook_name);
      setRerunTask(task);
      setRerunManifest(manifest.items);
      setRerunOpen(true);
    } catch (err) {
      console.error("加载重新运行参数失败:", err);
      setRerunError(err instanceof Error ? err.message : "加载重新运行参数失败");
      setRerunOpen(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRerun = async (variables: Record<string, unknown>) => {
    if (!rerunTask) return;
    if (rerunTask.runbook_missing) {
      setRerunError("关联的运行手册已删除，不能重新运行该历史任务");
      return;
    }
    setIsSubmitting(true);
    setRerunError("");
    setLogTask(null);
    try {
      const response = await taskApi.rerun(rerunTask.task_id, variables);
      setRerunOpen(false);
      mutate(`tasks-${workpiece}`);
      setLogTask(response.task);
      setLogOpen(true);
    } catch (err) {
      console.error("重新运行失败:", err);
      setRerunError(err instanceof Error ? err.message : "重新运行失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  const runTerraformAction = async (task: TaskSummary | Task, action: TerraformTaskAction) => {
    if (!isTerraformTask(task)) return;
    setIsSubmitting(true);
    setLogTask(null);
    setTaskActionError("");
    try {
      const response = await taskApi.terraformAction(task.task_id, action);
      mutate(`tasks-${workpiece}`);
      setLogTask(response.task);
      setLogOpen(true);
      if (selectedTask?.task_id === task.task_id) {
        const updated = await taskApi.get(workpiece, task.task_id);
        setSelectedTask(updated);
      }
    } catch (err) {
      console.error(`Terraform ${action} 失败:`, err);
      setTaskActionError(err instanceof Error ? err.message : `Terraform ${action} 失败`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTerraformAction = (task: TaskSummary | Task, action: TerraformTaskAction) => {
    if (!isTerraformTask(task)) return;
    if (action === "destroy") {
      setDestroyTask(task);
      return;
    }
    runTerraformAction(task, action);
  };

  const confirmDestroy = async () => {
    if (!destroyTask) return;
    const task = destroyTask;
    setDestroyTask(null);
    await runTerraformAction(task, "destroy");
  };

  const handleConfirm = async () => {
    if (!selectedTask) return;

    setIsSubmitting(true);
    try {
      await taskApi.confirm(workpiece, selectedTask.task_id);
      mutate(`tasks-${workpiece}`);
      const updated = await taskApi.get(workpiece, selectedTask.task_id);
      setSelectedTask(updated);
    } catch (err) {
      console.error("确认执行失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!selectedTask) return;

    setIsSubmitting(true);
    try {
      await taskApi.cancel(workpiece, selectedTask.task_id);
      mutate(`tasks-${workpiece}`);
      const updated = await taskApi.get(workpiece, selectedTask.task_id);
      setSelectedTask(updated);
    } catch (err) {
      console.error("取消任务失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const statusCounts = {
    pending: tasks.filter((t) => t.status === "pending").length,
    ready: tasks.filter((t) => t.status === "ready").length,
    running: tasks.filter((t) => t.status === "running").length,
    success: tasks.filter((t) => t.status === "success").length,
    failed: tasks.filter((t) => t.status === "failed").length,
    canceled: tasks.filter((t) => t.status === "canceled").length,
  };

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-96 flex-col items-center justify-center gap-4">
        <XCircle className="h-12 w-12 text-destructive" />
        <p className="text-muted-foreground">加载失败</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {taskActionError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {taskActionError}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-6 gap-4">
        {Object.entries(statusCounts).map(([status, count]) => (
          <Card key={status}>
            <CardContent className="p-4 text-center">
              <div className="text-2xl font-bold">{count}</div>
              <StatusBadge status={status} className="mt-1" />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tasks List */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>任务列表</CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => mutate(`tasks-${workpiece}`)}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {sortedTasks.length === 0 ? (
            <EmptyState
              icon={ListTodo}
              title="暂无任务"
              description="通过运行手册触发任务来开始执行"
            />
          ) : (
            <div className="divide-y divide-border">
              {sortedTasks.map((task: TaskSummary) => (
                <div
                  key={task.task_id}
                  className="flex items-center justify-between py-4 transition-colors hover:bg-accent/50"
                >
                  <div className="flex items-center gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm">{task.task_id}</span>
                        <StatusBadge status={task.status} />
                        <Badge variant="outline" className="text-xs">
                          {task.source === "manual" ? "手动" : "定时"}
                        </Badge>
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        {task.runbook_name} · {formatDate(task.created_at)}
                        {task.runbook_missing && (
                          <Badge variant="destructive" className="ml-2 text-xs">
                            Runbook 已删除
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-1">
                    {isTerraformTask(task) && (
                      <TerraformActionButtons
                        task={task}
                        isSubmitting={isSubmitting}
                        onAction={handleTerraformAction}
                      />
                    )}
                    {canCreateFollowUpTask(task) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openRerunDialog(task.task_id)}
                      >
                        <RotateCcw className="mr-2 h-4 w-4" />
                        重跑
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openTaskLog(task.task_id)}
                    >
                      <Terminal className="mr-2 h-4 w-4" />
                      日志
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => loadTaskDetail(task.task_id)}
                    >
                      <Eye className="mr-2 h-4 w-4" />
                      查看
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Task Detail Dialog */}
      <Dialog
        open={detailOpen}
        onOpenChange={(open) => {
          setDetailOpen(open);
          if (!open) setTaskActionError("");
        }}
      >
        <DialogContent className="grid max-h-[92vh] max-w-[min(1120px,calc(100vw-2rem))] grid-rows-[auto_minmax(0,1fr)_auto]">
          <DialogHeader>
            <DialogTitle>任务详情</DialogTitle>
            <DialogDescription>
              {selectedTask?.task_id}
            </DialogDescription>
          </DialogHeader>
          {selectedTask && (
            <Tabs defaultValue="info" className="min-h-0 w-full overflow-hidden">
              <TabsList>
                <TabsTrigger value="info">基本信息</TabsTrigger>
                <TabsTrigger value="variables">变量</TabsTrigger>
                <TabsTrigger value="schedule">调度信息</TabsTrigger>
                <TabsTrigger value="logs">日志</TabsTrigger>
              </TabsList>
              <TabsContent value="info" className="max-h-[62vh] space-y-4 overflow-auto pr-2">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>状态</Label>
                    <div className="mt-1">
                      <StatusBadge status={selectedTask.status} />
                    </div>
                  </div>
                  <div>
                    <Label>来源</Label>
                    <div className="mt-1">
                      <Badge variant="outline">
                        {selectedTask.source === "manual" ? "手动触发" : "定时任务"}
                      </Badge>
                    </div>
                  </div>
                  <div>
                    <Label>运行手册</Label>
                    <div className="mt-1 flex items-center gap-2 font-medium">
                      {selectedTask.runbook_name}
                      {selectedTask.runbook_missing ? (
                        <Badge variant="destructive" className="text-xs">
                          Runbook 已删除
                        </Badge>
                      ) : getTaskRunbookType(selectedTask) ? (
                        <Badge variant="outline" className="text-xs">
                          {getTaskRunbookType(selectedTask)}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs">
                          类型未知
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div>
                    <Label>退出码</Label>
                    <div className="mt-1 font-mono">
                      {selectedTask.exit_code ?? "-"}
                    </div>
                  </div>
                  <div>
                    <Label>创建时间</Label>
                    <div className="mt-1">{formatDate(selectedTask.created_at)}</div>
                  </div>
                  <div>
                    <Label>开始时间</Label>
                    <div className="mt-1">
                      {selectedTask.started_at ? formatDate(selectedTask.started_at) : "-"}
                    </div>
                  </div>
                  <div>
                    <Label>结束时间</Label>
                    <div className="mt-1">
                      {selectedTask.ended_at ? formatDate(selectedTask.ended_at) : "-"}
                    </div>
                  </div>
                  <div>
                    <Label>更新时间</Label>
                    <div className="mt-1">{formatDate(selectedTask.updated_at)}</div>
                  </div>
                </div>
                {selectedTask.error_summary && (
                  <div>
                    <Label>错误信息</Label>
                    <div className="mt-1 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                      {selectedTask.error_summary}
                    </div>
                  </div>
                )}
              </TabsContent>
              <TabsContent value="variables" className="max-h-[62vh] overflow-auto">
                <pre className="rounded-lg bg-secondary p-4 text-sm overflow-auto max-h-64">
                  {JSON.stringify(selectedTask.variables, null, 2)}
                </pre>
              </TabsContent>
              <TabsContent value="schedule" className="max-h-[62vh] overflow-auto">
                <pre className="rounded-lg bg-secondary p-4 text-sm overflow-auto max-h-64">
                  {JSON.stringify(selectedTask.schedule, null, 2)}
                </pre>
              </TabsContent>
              <TabsContent value="logs" className="min-h-0">
                <TaskLogPanel workpiece={workpiece} taskId={selectedTask.task_id} initialTask={selectedTask} />
              </TabsContent>
            </Tabs>
          )}
          {taskActionError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {taskActionError}
            </div>
          )}
          <DialogFooter className="flex flex-wrap gap-2">
            {selectedTask?.status === "pending" || selectedTask?.status === "ready" ? (
              <>
                <Button
                  variant="outline"
                  onClick={handleCancel}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <X className="mr-2 h-4 w-4" />
                  )}
                  取消任务
                </Button>
                <Button onClick={handleConfirm} disabled={isSubmitting || selectedTask.runbook_missing}>
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-2 h-4 w-4" />
                  )}
                  确认执行
                </Button>
              </>
            ) : (
              <>
                {selectedTask && isTerraformTask(selectedTask) && (
                  <TerraformActionButtons
                    task={selectedTask}
                    isSubmitting={isSubmitting}
                    onAction={handleTerraformAction}
                  />
                )}
                <Button variant="outline" onClick={() => setDetailOpen(false)}>
                  关闭
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(destroyTask)} onOpenChange={(open) => !open && setDestroyTask(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认 Destroy</DialogTitle>
            <DialogDescription>
              将基于任务 {destroyTask?.task_id} 的 Terraform state 创建 destroy 任务。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDestroyTask(null)} disabled={isSubmitting}>
              取消
            </Button>
            <Button onClick={confirmDestroy} disabled={isSubmitting}>
              {isSubmitting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <AlertTriangle className="mr-2 h-4 w-4" />
              )}
              确认 Destroy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <TaskLogDialog
        open={logOpen}
        onOpenChange={setLogOpen}
        workpiece={workpiece}
        taskId={logTask?.task_id || null}
        initialTask={logTask}
      />

      <TaskParameterDialog
        open={rerunOpen}
        onOpenChange={setRerunOpen}
        title="重新运行任务"
        description={rerunTask ? `基于任务 ${rerunTask.task_id} 重新运行 ${rerunTask.runbook_name}` : "加载历史任务参数"}
        manifestItems={rerunManifest}
        initialValues={rerunTask?.variables}
        submitLabel="重新运行"
        isSubmitting={isSubmitting}
        errorText={rerunError}
        onSubmit={handleRerun}
      />
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-medium text-muted-foreground">{children}</div>;
}

function TerraformActionButtons({
  task,
  isSubmitting,
  onAction,
}: {
  task: TaskSummary | Task;
  isSubmitting: boolean;
  onAction: (task: TaskSummary | Task, action: TerraformTaskAction) => void;
}) {
  const disabled = isSubmitting || task.status === "running";
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Button variant="outline" size="sm" onClick={() => onAction(task, "plan")} disabled={disabled}>
        <Eye className="mr-2 h-4 w-4" />
        Plan
      </Button>
      <Button variant="outline" size="sm" onClick={() => onAction(task, "apply")} disabled={disabled}>
        <Play className="mr-2 h-4 w-4" />
        Apply
      </Button>
      <Button variant="outline" size="sm" onClick={() => onAction(task, "output")} disabled={disabled}>
        <Terminal className="mr-2 h-4 w-4" />
        Output
      </Button>
      <Button variant="outline" size="sm" onClick={() => onAction(task, "destroy")} disabled={disabled}>
        <AlertTriangle className="mr-2 h-4 w-4" />
        Destroy
      </Button>
    </div>
  );
}
