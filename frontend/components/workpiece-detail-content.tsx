"use client";

import Link from "next/link";
import useSWR from "swr";
import {
  BookOpen,
  ListTodo,
  Clock,
  Settings,
  ArrowRight,
  Loader2,
  XCircle,
  FolderOpen,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { workpieceApi, runbookApi, taskApi, type RunbookSummary, type TaskSummary } from "@/lib/api";
import { recentTasks as selectRecentTasks, workpieceHref } from "@/lib/routes";
import { formatDate } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

interface WorkpieceDetailContentProps {
  workpiece: string;
}

export function WorkpieceDetailContent({ workpiece }: WorkpieceDetailContentProps) {
  const { data: detail, error: detailError, isLoading: detailLoading } = useSWR(
    `workpiece-${workpiece}`,
    () => workpieceApi.get(workpiece)
  );

  const { data: runbooksData } = useSWR(
    `runbooks-${workpiece}`,
    () => runbookApi.list(workpiece)
  );

  const { data: tasksData } = useSWR(
    `tasks-${workpiece}`,
    () => taskApi.list(workpiece)
  );

  const runbooks = runbooksData?.items || [];
  const tasks = tasksData?.items || [];
  const recentTasks = selectRecentTasks(tasks, 5);

  if (detailLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (detailError) {
    return (
      <div className="flex h-96 flex-col items-center justify-center gap-4">
        <XCircle className="h-12 w-12 text-destructive" />
        <p className="text-muted-foreground">加载失败</p>
      </div>
    );
  }

  const stats = [
    {
      title: "运行手册",
      value: detail?.stats.runbooks || 0,
      icon: BookOpen,
      href: workpieceHref(workpiece, "/runbooks"),
      color: "text-info",
      bgColor: "bg-info/10",
    },
    {
      title: "任务",
      value: detail?.stats.tasks || 0,
      icon: ListTodo,
      href: workpieceHref(workpiece, "/tasks"),
      color: "text-warning",
      bgColor: "bg-warning/10",
    },
    {
      title: "定时作业",
      value: detail?.stats.jobs || 0,
      icon: Clock,
      href: workpieceHref(workpiece, "/jobs"),
      color: "text-success",
      bgColor: "bg-success/10",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        {stats.map((stat) => (
          <Link key={stat.title} href={stat.href}>
            <Card className="transition-colors hover:border-primary/50">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {stat.title}
                </CardTitle>
                <div className={`rounded-lg p-2 ${stat.bgColor}`}>
                  <stat.icon className={`h-4 w-4 ${stat.color}`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Runbooks */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">运行手册</CardTitle>
            <Link href={workpieceHref(workpiece, "/runbooks")}>
              <Button variant="ghost" size="sm">
                查看全部
                <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {runbooks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <BookOpen className="h-8 w-8 text-muted-foreground" />
                <p className="mt-2 text-sm text-muted-foreground">暂无运行手册</p>
                <Link href={workpieceHref(workpiece, "/runbooks")} className="mt-4">
                  <Button size="sm">创建运行手册</Button>
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {runbooks.slice(0, 5).map((runbook: RunbookSummary) => (
                  <Link
                    key={runbook.name}
                    href={workpieceHref(workpiece, "/runbooks")}
                    className="flex items-center justify-between py-3 transition-colors hover:bg-accent/50"
                  >
                    <div>
                      <div className="font-medium">{runbook.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {runbook.type} · {runbook.manifest_summary.variables} 变量
                      </div>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Tasks */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">最近任务</CardTitle>
            <Link href={workpieceHref(workpiece, "/tasks")}>
              <Button variant="ghost" size="sm">
                查看全部
                <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {recentTasks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <ListTodo className="h-8 w-8 text-muted-foreground" />
                <p className="mt-2 text-sm text-muted-foreground">暂无任务</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {recentTasks.map((task: TaskSummary) => (
                  <Link
                    key={task.task_id}
                    href={workpieceHref(workpiece, "/tasks")}
                    className="flex items-center justify-between py-3 transition-colors hover:bg-accent/50"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm">{task.task_id}</span>
                        <StatusBadge status={task.status} />
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {task.runbook_name} · {formatDate(task.created_at)}
                      </div>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">工作区信息</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-muted-foreground">名称</dt>
              <dd className="mt-1">{detail?.name}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">描述</dt>
              <dd className="mt-1">{detail?.description || "暂无描述"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">创建时间</dt>
              <dd className="mt-1">{detail ? formatDate(detail.created_at) : "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">更新时间</dt>
              <dd className="mt-1">{detail ? formatDate(detail.updated_at) : "-"}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-sm font-medium text-muted-foreground">存储目录</dt>
              <dd className="mt-1 font-mono text-sm">{detail?.directory}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
