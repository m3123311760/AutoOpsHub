"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  BookOpen,
  Plus,
  Play,
  Trash2,
  Code,
  FileCode,
  Terminal,
  GitBranch,
  Loader2,
  XCircle,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/empty-state";
import { runbookApi, type RunbookSummary, type RunbookUpsertRequest } from "@/lib/api";
import { formatDate } from "@/lib/utils";

interface RunbooksContentProps {
  workpiece: string;
}

const typeIcons = {
  Terraform: FileCode,
  Ansible: GitBranch,
  Script: Terminal,
  Workflow: Code,
};

const typeColors = {
  Terraform: "bg-purple-500/10 text-purple-500",
  Ansible: "bg-red-500/10 text-red-500",
  Script: "bg-blue-500/10 text-blue-500",
  Workflow: "bg-green-500/10 text-green-500",
};

export function RunbooksContent({ workpiece }: RunbooksContentProps) {
  const { data, error, isLoading } = useSWR(
    `runbooks-${workpiece}`,
    () => runbookApi.list(workpiece)
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedRunbook, setSelectedRunbook] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState<RunbookUpsertRequest>({
    type: "Script",
    description: "",
    content: "",
    runtime: "bash",
  });
  const [newName, setNewName] = useState("");
  const [triggerVariables, setTriggerVariables] = useState("{}");

  const runbooks = data?.items || [];

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !formData.content.trim()) return;

    setIsSubmitting(true);
    try {
      await runbookApi.upsert(workpiece, newName.trim(), formData);
      mutate(`runbooks-${workpiece}`);
      setCreateOpen(false);
      setNewName("");
      setFormData({ type: "Script", description: "", content: "", runtime: "bash" });
    } catch (err) {
      console.error("创建失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTrigger = async () => {
    if (!selectedRunbook) return;

    setIsSubmitting(true);
    try {
      const variables = JSON.parse(triggerVariables);
      await runbookApi.trigger(workpiece, selectedRunbook, variables);
      setTriggerOpen(false);
      setTriggerVariables("{}");
    } catch (err) {
      console.error("触发失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedRunbook) return;

    setIsSubmitting(true);
    try {
      await runbookApi.delete(workpiece, selectedRunbook);
      mutate(`runbooks-${workpiece}`);
      setDeleteOpen(false);
      setSelectedRunbook(null);
    } catch (err) {
      console.error("删除失败:", err);
    } finally {
      setIsSubmitting(false);
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

  return (
    <div className="space-y-6">
      {/* Header Actions */}
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground">共 {runbooks.length} 个运行手册</p>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建运行手册
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <form onSubmit={handleCreate}>
              <DialogHeader>
                <DialogTitle>新建运行手册</DialogTitle>
                <DialogDescription>
                  创建一个新的运行手册，支持 Terraform、Ansible、Script 和 Workflow 类型
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="name">名称</Label>
                    <Input
                      id="name"
                      placeholder="输入运行手册名称"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="type">类型</Label>
                    <Select
                      value={formData.type}
                      onValueChange={(value) =>
                        setFormData({ ...formData, type: value as RunbookUpsertRequest["type"] })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Script">Script</SelectItem>
                        <SelectItem value="Terraform">Terraform</SelectItem>
                        <SelectItem value="Ansible">Ansible</SelectItem>
                        <SelectItem value="Workflow">Workflow</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                {formData.type === "Script" && (
                  <div className="grid gap-2">
                    <Label htmlFor="runtime">Runtime</Label>
                    <Select
                      value={formData.runtime || "bash"}
                      onValueChange={(value) =>
                        setFormData({ ...formData, runtime: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="bash">Bash</SelectItem>
                        <SelectItem value="python">Python</SelectItem>
                        <SelectItem value="node">Node.js</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="grid gap-2">
                  <Label htmlFor="description">描述</Label>
                  <Input
                    id="description"
                    placeholder="输入描述（可选）"
                    value={formData.description}
                    onChange={(e) =>
                      setFormData({ ...formData, description: e.target.value })
                    }
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="content">内容</Label>
                  <Textarea
                    id="content"
                    placeholder="输入脚本内容..."
                    className="h-48 font-mono text-sm"
                    value={formData.content}
                    onChange={(e) =>
                      setFormData({ ...formData, content: e.target.value })
                    }
                    required
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
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  创建
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Runbooks Grid */}
      {runbooks.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="暂无运行手册"
          description="创建您的第一个运行手册来开始自动化运维任务"
          action={
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建运行手册
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {runbooks.map((runbook: RunbookSummary) => {
            const TypeIcon = typeIcons[runbook.type];
            const typeColor = typeColors[runbook.type];

            return (
              <Card
                key={runbook.name}
                className="group transition-colors hover:border-primary/50"
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className={`rounded-lg p-2 ${typeColor}`}>
                      <TypeIcon className="h-4 w-4" />
                    </div>
                    <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          setSelectedRunbook(runbook.name);
                          setTriggerOpen(true);
                        }}
                      >
                        <Play className="h-4 w-4 text-primary" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          setSelectedRunbook(runbook.name);
                          setDeleteOpen(true);
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <h3 className="font-semibold">{runbook.name}</h3>
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                    {runbook.description || "暂无描述"}
                  </p>
                  <div className="mt-4 flex items-center gap-2">
                    <Badge variant="outline">{runbook.type}</Badge>
                    <span className="text-sm text-muted-foreground">
                      {runbook.manifest_summary.variables} 变量
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    更新于 {formatDate(runbook.updated_at)}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Trigger Dialog */}
      <Dialog open={triggerOpen} onOpenChange={setTriggerOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>触发运行手册</DialogTitle>
            <DialogDescription>
              执行运行手册 &quot;{selectedRunbook}&quot;
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="variables">变量 (JSON)</Label>
              <Textarea
                id="variables"
                className="h-32 font-mono text-sm"
                value={triggerVariables}
                onChange={(e) => setTriggerVariables(e.target.value)}
                placeholder='{"key": "value"}'
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTriggerOpen(false)}>
              取消
            </Button>
            <Button onClick={handleTrigger} disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              执行
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除运行手册 &quot;{selectedRunbook}&quot; 吗？此操作不可撤销。
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
