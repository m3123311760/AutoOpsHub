"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR, { mutate } from "swr";
import {
  FolderKanban,
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
  BookOpen,
  ListTodo,
  Clock,
  Loader2,
  XCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { workpieceApi, type Workpiece } from "@/lib/api";
import { workpieceHref } from "@/lib/routes";
import { formatDate } from "@/lib/utils";

const fetcher = () => workpieceApi.list();

export function WorkpiecesContent() {
  const { data, error, isLoading } = useSWR("workpieces", fetcher);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedWorkpiece, setSelectedWorkpiece] = useState<string | null>(null);
  const [formData, setFormData] = useState({ name: "", description: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const workpieces = data?.items || [];

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    setIsSubmitting(true);
    try {
      await workpieceApi.create(formData.name.trim(), formData.description);
      mutate("workpieces");
      setCreateOpen(false);
      setFormData({ name: "", description: "" });
    } catch (err) {
      console.error("创建失败:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedWorkpiece) return;

    setIsSubmitting(true);
    try {
      await workpieceApi.delete(selectedWorkpiece);
      mutate("workpieces");
      setDeleteOpen(false);
      setSelectedWorkpiece(null);
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
        <p className="text-muted-foreground">加载失败，请检查后端服务是否运行</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Actions */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-muted-foreground">
            共 {workpieces.length} 个工作区
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建工作区
            </Button>
          </DialogTrigger>
          <DialogContent>
            <form onSubmit={handleCreate}>
              <DialogHeader>
                <DialogTitle>新建工作区</DialogTitle>
                <DialogDescription>
                  创建一个新的工作区来组织您的运维任务
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">名称</Label>
                  <Input
                    id="name"
                    placeholder="输入工作区名称"
                    value={formData.name}
                    onChange={(e) =>
                      setFormData({ ...formData, name: e.target.value })
                    }
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="description">描述</Label>
                  <Textarea
                    id="description"
                    placeholder="输入工作区描述（可选）"
                    value={formData.description}
                    onChange={(e) =>
                      setFormData({ ...formData, description: e.target.value })
                    }
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
                  {isSubmitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  创建
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Workpieces Grid */}
      {workpieces.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="暂无工作区"
          description="创建您的第一个工作区来开始管理运维任务"
          action={
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建工作区
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workpieces.map((workpiece: Workpiece) => (
            <Card
              key={workpiece.name}
              className="group transition-colors hover:border-primary/50"
            >
              <CardContent className="p-0">
                <Link
                  href={workpieceHref(workpiece.name)}
                  className="block p-6"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                      <FolderKanban className="h-5 w-5 text-primary" />
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="opacity-0 group-hover:opacity-100"
                      onClick={(e) => {
                        e.preventDefault();
                        setSelectedWorkpiece(workpiece.name);
                        setDeleteOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                  <div className="mt-4">
                    <h3 className="font-semibold">{workpiece.name}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                      {workpiece.description || "暂无描述"}
                    </p>
                  </div>
                  <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
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
                  <div className="mt-4 text-xs text-muted-foreground">
                    更新于 {formatDate(workpiece.updated_at)}
                  </div>
                </Link>
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
              确定要删除工作区 &quot;{selectedWorkpiece}&quot; 吗？此操作不可撤销，所有相关的运行手册、任务和定时作业都将被删除。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isSubmitting}
            >
              {isSubmitting && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
