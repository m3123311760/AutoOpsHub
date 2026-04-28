"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  Clock,
  Plus,
  Trash2,
  PlayCircle,
  PauseCircle,
  Loader2,
  XCircle,
  Calendar,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { jobApi, runbookApi, type Job, type JobUpsertRequest, type RunbookSummary } from "@/lib/api";
import { formatDate } from "@/lib/utils";

interface JobsContentProps {
  workpiece: string;
}

export function JobsContent({ workpiece }: JobsContentProps) {
  const { data, error, isLoading } = useSWR(
    `jobs-${workpiece}`,
    () => jobApi.list(workpiece)
  );

  const { data: runbooksData } = useSWR(
    `runbooks-${workpiece}`,
    () => runbookApi.list(workpiece)
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState<JobUpsertRequest>({
    description: "",
    cron: "0 0 * * *",
    runbook_name: "",
    variables: {},
    enabled: true,
  });
  const [newName, setNewName] = useState("");
  const [variablesJson, setVariablesJson] = useState("{}");

  const jobs = data?.items || [];
  const runbooks = runbooksData?.items || [];

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !formData.cron.trim() || !formData.runbook_name) return;

    setIsSubmitting(true);
    try {
      const variables = JSON.parse(variablesJson);
      await jobApi.upsert(workpiece, newName.trim(), {
        ...formData,
        variables,
      });
      mutate(`jobs-${workpiece}`);
      setCreateOpen(false);
      setNewName("");
      setFormData({
        description: "",
        cron: "0 0 * * *",
        runbook_name: "",
        variables: {},
        enabled: true,
      });
      setVariablesJson("{}");
    } catch (err) {
      console.error("创建失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedJob) return;

    setIsSubmitting(true);
    try {
      await jobApi.delete(workpiece, selectedJob);
      mutate(`jobs-${workpiece}`);
      setDeleteOpen(false);
      setSelectedJob(null);
    } catch (err) {
      console.error("删除失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleEnabled = async (job: Job) => {
    try {
      const current = await jobApi.get(workpiece, job.job_name);
      await jobApi.update(workpiece, job.job_name, {
        job_name: current.job_name,
        description: current.description,
        cron: current.cron,
        runbook_name: current.runbook_name,
        variables: current.variables,
        enabled: !current.enabled,
      });
      mutate(`jobs-${workpiece}`);
    } catch (err) {
      console.error("更新失败:", err);
    }
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

  const enabledCount = jobs.filter((j) => j.enabled).length;

  return (
    <div className="space-y-6">
      {/* Header Actions */}
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground">
          共 {jobs.length} 个定时作业，{enabledCount} 个已启用
        </p>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建定时作业
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <form onSubmit={handleCreate}>
              <DialogHeader>
                <DialogTitle>新建定时作业</DialogTitle>
                <DialogDescription>
                  创建一个新的定时作业来自动执行运行手册
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="job-name">作业名称</Label>
                  <Input
                    id="job-name"
                    placeholder="输入作业名称"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="runbook">运行手册</Label>
                  <Select
                    value={formData.runbook_name || ""}
                    onValueChange={(value) =>
                      setFormData({ ...formData, runbook_name: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="选择运行手册" />
                    </SelectTrigger>
                    <SelectContent>
                      {runbooks.map((rb: RunbookSummary) => (
                        <SelectItem key={rb.name} value={rb.name}>
                          {rb.name} ({rb.type})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="cron">Cron 表达式</Label>
                  <Input
                    id="cron"
                    placeholder="0 0 * * *"
                    value={formData.cron}
                    onChange={(e) =>
                      setFormData({ ...formData, cron: e.target.value })
                    }
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    格式: 分 时 日 月 周
                  </p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="job-desc">描述</Label>
                  <Input
                    id="job-desc"
                    placeholder="输入描述（可选）"
                    value={formData.description}
                    onChange={(e) =>
                      setFormData({ ...formData, description: e.target.value })
                    }
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="job-vars">变量 (JSON)</Label>
                  <Textarea
                    id="job-vars"
                    className="h-24 font-mono text-sm"
                    value={variablesJson}
                    onChange={(e) => setVariablesJson(e.target.value)}
                    placeholder='{"key": "value"}'
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCreateOpen(false)}
                >
                  取消
                </Button>
                <Button type="submit" disabled={isSubmitting || runbooks.length === 0}>
                  {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  创建
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Jobs List */}
      {jobs.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="暂无定时作业"
          description="创建定时作业来自动执行运行手册"
          action={
            runbooks.length > 0 ? (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                创建定时作业
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">
                请先创建运行手册
              </p>
            )
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {jobs.map((job: Job) => (
            <Card
              key={job.job_name}
              className={`transition-colors ${
                job.enabled ? "hover:border-primary/50" : "opacity-60"
              }`}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className={`rounded-lg p-2 ${
                        job.enabled ? "bg-success/10" : "bg-muted"
                      }`}
                    >
                      <Clock
                        className={`h-4 w-4 ${
                          job.enabled ? "text-success" : "text-muted-foreground"
                        }`}
                      />
                    </div>
                    <div>
                      <h3 className="font-semibold">{job.job_name}</h3>
                      <p className="text-sm text-muted-foreground">
                        {job.description || "暂无描述"}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => toggleEnabled(job)}
                    >
                      {job.enabled ? (
                        <PauseCircle className="h-4 w-4 text-warning" />
                      ) : (
                        <PlayCircle className="h-4 w-4 text-success" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        setSelectedJob(job.job_name);
                        setDeleteOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">运行手册</span>
                    <span className="font-medium">{job.runbook_name}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Cron</span>
                    <code className="rounded bg-secondary px-2 py-0.5 text-xs">
                      {job.cron}
                    </code>
                  </div>
                  {job.next_run_at && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">下次执行</span>
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {formatDate(job.next_run_at)}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">状态</span>
                    <Badge variant={job.enabled ? "success" : "secondary"}>
                      {job.enabled ? "已启用" : "已禁用"}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除定时作业 &quot;{selectedJob}&quot; 吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
