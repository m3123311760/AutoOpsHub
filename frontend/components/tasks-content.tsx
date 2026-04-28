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
import { taskApi, type TaskSummary, type Task } from "@/lib/api";
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

  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const tasks = data?.items || [];

  // Sort by created_at desc
  const sortedTasks = [...tasks].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const loadTaskDetail = async (taskId: string) => {
    try {
      const task = await taskApi.get(workpiece, taskId);
      setSelectedTask(task);
      setDetailOpen(true);
    } catch (err) {
      console.error("加载任务详情失败:", err);
    }
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
                      </div>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => loadTaskDetail(task.task_id)}
                  >
                    <Eye className="mr-2 h-4 w-4" />
                    查看
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Task Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>任务详情</DialogTitle>
            <DialogDescription>
              {selectedTask?.task_id}
            </DialogDescription>
          </DialogHeader>
          {selectedTask && (
            <Tabs defaultValue="info" className="w-full">
              <TabsList>
                <TabsTrigger value="info">基本信息</TabsTrigger>
                <TabsTrigger value="variables">变量</TabsTrigger>
                <TabsTrigger value="schedule">调度信息</TabsTrigger>
              </TabsList>
              <TabsContent value="info" className="space-y-4">
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
                    <div className="mt-1 font-medium">{selectedTask.runbook_name}</div>
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
              <TabsContent value="variables">
                <pre className="rounded-lg bg-secondary p-4 text-sm overflow-auto max-h-64">
                  {JSON.stringify(selectedTask.variables, null, 2)}
                </pre>
              </TabsContent>
              <TabsContent value="schedule">
                <pre className="rounded-lg bg-secondary p-4 text-sm overflow-auto max-h-64">
                  {JSON.stringify(selectedTask.schedule, null, 2)}
                </pre>
              </TabsContent>
            </Tabs>
          )}
          <DialogFooter>
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
                <Button onClick={handleConfirm} disabled={isSubmitting}>
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-2 h-4 w-4" />
                  )}
                  确认执行
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => setDetailOpen(false)}>
                关闭
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-medium text-muted-foreground">{children}</div>;
}
