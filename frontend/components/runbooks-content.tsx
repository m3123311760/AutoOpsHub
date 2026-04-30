"use client";

import { useState, type InputHTMLAttributes } from "react";
import useSWR, { mutate } from "swr";
import {
  BookOpen,
  Plus,
  Play,
  Settings2,
  Trash2,
  Code,
  FileCode,
  Terminal,
  GitBranch,
  Loader2,
  Upload,
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
import { TaskLogDialog } from "@/components/task-log-viewer";
import { TaskParameterDialog } from "@/components/task-parameter-dialog";
import { runbookApi, type ManifestVariable, type RunbookSummary, type RunbookUpsertRequest, type Task } from "@/lib/api";
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

const readonlySystemVariables = new Set(["system.output", "system.runbook_file", "system.runbook_path"]);
const directoryInputProps = {
  webkitdirectory: "",
  directory: "",
} as InputHTMLAttributes<HTMLInputElement> & {
  webkitdirectory: string;
  directory: string;
};

export function RunbooksContent({ workpiece }: RunbooksContentProps) {
  const { data, error, isLoading } = useSWR(
    `runbooks-${workpiece}`,
    () => runbookApi.list(workpiece)
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [manifestOpen, setManifestOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [logTask, setLogTask] = useState<Task | null>(null);
  const [selectedRunbook, setSelectedRunbook] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [manifestItems, setManifestItems] = useState<ManifestVariable[]>([]);
  const [manifestDraft, setManifestDraft] = useState<ManifestVariable[]>([]);
  const [formData, setFormData] = useState<RunbookUpsertRequest>({
    type: "Script",
    description: "",
    content: "",
    runtime: "bash",
  });
  const [contentMode, setContentMode] = useState<"inline" | "files">("inline");
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [entryFile, setEntryFile] = useState("");
  const [newName, setNewName] = useState("");
  const [triggerError, setTriggerError] = useState("");

  const runbooks = data?.items || [];

  const openTriggerDialog = async (runbookName: string) => {
    setSelectedRunbook(runbookName);
    setTriggerOpen(true);
    setManifestItems([]);
    setTriggerError("");
    try {
      const manifest = await runbookApi.getManifest(workpiece, runbookName);
      setManifestItems(manifest.items);
    } catch (err) {
      console.error("加载 manifest 失败:", err);
      setTriggerError(err instanceof Error ? err.message : "加载 manifest 失败");
    }
  };

  const openManifestDialog = async (runbookName: string) => {
    setSelectedRunbook(runbookName);
    setManifestOpen(true);
    setManifestDraft([]);
    try {
      const manifest = await runbookApi.getManifest(workpiece, runbookName);
      setManifestDraft(manifest.items);
    } catch (err) {
      console.error("加载 manifest 失败:", err);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    if (contentMode === "files" && uploadFiles.length === 0) return;
    if (contentMode === "inline" && !formData.content.trim()) return;

    setIsSubmitting(true);
    try {
      if (contentMode === "files" && formData.type === "Terraform") {
        await runbookApi.upsertFiles(workpiece, newName.trim(), {
          type: "Terraform",
          description: formData.description,
          runtime: formData.runtime,
          entry_file: entryFile || undefined,
          files: uploadFiles,
        });
      } else {
        await runbookApi.upsert(workpiece, newName.trim(), formData);
      }
      mutate(`runbooks-${workpiece}`);
      setCreateOpen(false);
      setNewName("");
      setFormData({ type: "Script", description: "", content: "", runtime: "bash" });
      setContentMode("inline");
      setUploadFiles([]);
      setEntryFile("");
    } catch (err) {
      console.error("创建失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTrigger = async (variables: Record<string, unknown>) => {
    if (!selectedRunbook) return;

    setIsSubmitting(true);
    setTriggerError("");
    setLogTask(null);
    setLogOpen(true);
    try {
      const response = await runbookApi.trigger(workpiece, selectedRunbook, variables);
      setTriggerOpen(false);
      setLogTask(response.task);
      mutate(`tasks-${workpiece}`);
    } catch (err) {
      console.error("触发失败:", err);
      setTriggerError(err instanceof Error ? err.message : "触发失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleManifestSave = async () => {
    if (!selectedRunbook) return;

    setIsSubmitting(true);
    try {
      await runbookApi.upsertManifest(workpiece, selectedRunbook, manifestDraft);
      mutate(`runbooks-${workpiece}`);
      setManifestOpen(false);
    } catch (err) {
      console.error("保存 manifest 失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const updateManifestDraft = (index: number, patch: Partial<ManifestVariable>) => {
    setManifestDraft((items) =>
      items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item))
    );
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
                      onValueChange={(value) => {
                        const nextType = value as RunbookUpsertRequest["type"];
                        setFormData({ ...formData, type: nextType, runtime: nextType === "Script" ? formData.runtime || "bash" : formData.runtime });
                        setContentMode(nextType === "Terraform" ? "files" : "inline");
                      }}
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
                {formData.type === "Terraform" && (
                  <Tabs value={contentMode} onValueChange={(value) => setContentMode(value as "inline" | "files")}>
                    <TabsList>
                      <TabsTrigger value="files">文件包</TabsTrigger>
                      <TabsTrigger value="inline">Inline</TabsTrigger>
                    </TabsList>
                    <TabsContent value="files" className="space-y-3">
                      <div className="grid gap-2">
                        <Label htmlFor="entry-file">入口文件</Label>
                        <Input
                          id="entry-file"
                          placeholder="main.tf"
                          value={entryFile}
                          onChange={(e) => setEntryFile(e.target.value)}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="files">文件</Label>
                        <Input
                          id="files"
                          type="file"
                          multiple
                          {...directoryInputProps}
                          onChange={(e) => setUploadFiles(Array.from(e.target.files || []))}
                        />
                      </div>
                      {uploadFiles.length > 0 && (
                        <div className="max-h-32 overflow-y-auto rounded-md border p-2 text-sm">
                          {uploadFiles.map((file) => {
                            const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
                            return (
                              <div key={`${path}-${file.size}`} className="flex items-center justify-between gap-3 py-1">
                                <span className="truncate">{path}</span>
                                <span className="shrink-0 text-muted-foreground">{file.size} B</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </TabsContent>
                    <TabsContent value="inline" />
                  </Tabs>
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
                {contentMode === "inline" && (
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
                )}
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
                        onClick={() => openTriggerDialog(runbook.name)}
                      >
                        <Play className="h-4 w-4 text-primary" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openManifestDialog(runbook.name)}
                      >
                        <Settings2 className="h-4 w-4 text-muted-foreground" />
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
                    {runbook.content_mode === "files" && (
                      <Badge variant="secondary">
                        <Upload className="mr-1 h-3 w-3" />
                        {runbook.files_summary?.count || 0} 文件
                      </Badge>
                    )}
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

      <TaskParameterDialog
        open={triggerOpen}
        onOpenChange={setTriggerOpen}
        title="触发运行手册"
        description={`执行运行手册 "${selectedRunbook || ""}"`}
        manifestItems={manifestItems}
        submitLabel="执行"
        isSubmitting={isSubmitting}
        errorText={triggerError}
        onSubmit={handleTrigger}
      />

      {/* Manifest Dialog */}
      <Dialog open={manifestOpen} onOpenChange={setManifestOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>编辑 Manifest</DialogTitle>
            <DialogDescription>
              更新运行手册 &quot;{selectedRunbook}&quot; 的变量声明
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] space-y-3 overflow-y-auto py-4">
            {manifestDraft.map((item, index) => (
              <div key={item.name} className="grid gap-3 rounded-md border p-3">
                <div className="grid gap-3 md:grid-cols-[1.4fr_1fr_120px_90px]">
                  <div className="grid gap-2">
                    <Label htmlFor={`manifest-name-${index}`}>变量名</Label>
                    <Input id={`manifest-name-${index}`} value={item.name} readOnly />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor={`manifest-display-${index}`}>显示名</Label>
                    <Input
                      id={`manifest-display-${index}`}
                      value={item.display_name}
                      onChange={(e) => updateManifestDraft(index, { display_name: e.target.value })}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>方向</Label>
                    <Select
                      value={item.direction}
                      disabled={readonlySystemVariables.has(item.name)}
                      onValueChange={(value) =>
                        updateManifestDraft(index, { direction: value as ManifestVariable["direction"] })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="input">Input</SelectItem>
                        <SelectItem value="output">Output</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <Label>必填</Label>
                    <Select
                      value={item.required ? "true" : "false"}
                      disabled={readonlySystemVariables.has(item.name)}
                      onValueChange={(value) => updateManifestDraft(index, { required: value === "true" })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="false">否</SelectItem>
                        <SelectItem value="true">是</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor={`manifest-default-${index}`}>默认值</Label>
                  <Input
                    id={`manifest-default-${index}`}
                    value={item.default_value}
                    onChange={(e) => updateManifestDraft(index, { default_value: e.target.value })}
                  />
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setManifestOpen(false)}>
              取消
            </Button>
            <Button onClick={handleManifestSave} disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              保存
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

      <TaskLogDialog
        open={logOpen}
        onOpenChange={setLogOpen}
        workpiece={workpiece}
        taskId={logTask?.task_id || null}
        initialTask={logTask}
      />
    </div>
  );
}
