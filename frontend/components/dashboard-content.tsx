"use client";

import Link from "next/link";
import useSWR from "swr";
import {
  FolderKanban,
  BookOpen,
  ListTodo,
  Clock,
  ArrowRight,
  Plus,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { workpieceApi, type Workpiece } from "@/lib/api";

const fetcher = () => workpieceApi.list();

export function DashboardContent() {
  const { data, error, isLoading } = useSWR("workpieces", fetcher);

  const workpieces = data?.items || [];
  
  // Calculate totals
  const totalRunbooks = workpieces.reduce((acc, wp) => acc + (wp.stats?.runbooks || 0), 0);
  const totalTasks = workpieces.reduce((acc, wp) => acc + (wp.stats?.tasks || 0), 0);
  const totalJobs = workpieces.reduce((acc, wp) => acc + (wp.stats?.jobs || 0), 0);

  const stats = [
    {
      title: "工作区",
      value: workpieces.length,
      icon: FolderKanban,
      href: "/workpieces",
      color: "text-primary",
      bgColor: "bg-primary/10",
    },
    {
      title: "运行手册",
      value: totalRunbooks,
      icon: BookOpen,
      href: "/workpieces",
      color: "text-info",
      bgColor: "bg-info/10",
    },
    {
      title: "任务",
      value: totalTasks,
      icon: ListTodo,
      href: "/workpieces",
      color: "text-warning",
      bgColor: "bg-warning/10",
    },
    {
      title: "定时作业",
      value: totalJobs,
      icon: Clock,
      href: "/workpieces",
      color: "text-success",
      bgColor: "bg-success/10",
    },
  ];

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
        <p className="text-muted-foreground">加载失败，请检查后端服务是否运行</p>
        <p className="text-sm text-muted-foreground">确保后端运行在 http://localhost:8000</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
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

      {/* Workpieces List */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>工作区</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              管理您的运维工作空间
            </p>
          </div>
          <Link href="/workpieces">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建工作区
            </Button>
          </Link>
        </CardHeader>
        <CardContent>
          {workpieces.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                <FolderKanban className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">暂无工作区</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                创建您的第一个工作区来开始管理运维任务
              </p>
              <Link href="/workpieces" className="mt-4">
                <Button>
                  <Plus className="mr-2 h-4 w-4" />
                  创建工作区
                </Button>
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {workpieces.map((workpiece: Workpiece) => (
                <Link
                  key={workpiece.name}
                  href={`/workpieces/${workpiece.name}`}
                  className="flex items-center justify-between py-4 transition-colors hover:bg-accent/50"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                      <FolderKanban className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <div className="font-medium">{workpiece.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {workpiece.description || "暂无描述"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <BookOpen className="h-4 w-4" />
                        {workpiece.stats?.runbooks || 0}
                      </span>
                      <span className="flex items-center gap-1">
                        <ListTodo className="h-4 w-4" />
                        {workpiece.stats?.tasks || 0}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        {workpiece.stats?.jobs || 0}
                      </span>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Start Guide */}
      <Card>
        <CardHeader>
          <CardTitle>快速开始</CardTitle>
          <p className="text-sm text-muted-foreground">
            了解如何使用 AutoOpsHub 管理您的运维任务
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-border p-4">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary">
                1
              </div>
              <h4 className="mt-3 font-semibold">创建工作区</h4>
              <p className="mt-1 text-sm text-muted-foreground">
                工作区是管理相关运维任务的容器，可以按项目或环境划分
              </p>
            </div>
            <div className="rounded-lg border border-border p-4">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary">
                2
              </div>
              <h4 className="mt-3 font-semibold">编写运行手册</h4>
              <p className="mt-1 text-sm text-muted-foreground">
                支持 Terraform、Ansible、Script 和 Workflow 四种类型
              </p>
            </div>
            <div className="rounded-lg border border-border p-4">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary">
                3
              </div>
              <h4 className="mt-3 font-semibold">执行任务</h4>
              <p className="mt-1 text-sm text-muted-foreground">
                手动触发或设置定时作业自动执行运行手册
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
