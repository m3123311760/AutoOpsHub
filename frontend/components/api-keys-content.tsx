"use client";

import { FormEvent, useState } from "react";
import useSWR from "swr";
import { Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { ApiKeyCreateResponse, authApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ApiKeysContent() {
  const { data, error, isLoading, mutate } = useSWR("auth-api-keys", () => authApi.listApiKeys());
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ApiKeyCreateResponse | null>(null);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setSubmitting(true);
    try {
      const result = await authApi.createApiKey(name.trim() || "default");
      setCreated(result);
      setName("");
      await mutate();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建 API Key 失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRevoke(keyId: string) {
    setMessage("");
    try {
      await authApi.revokeApiKey(keyId);
      await mutate();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "撤销 API Key 失败");
    }
  }

  async function copyCreatedKey() {
    if (!created) return;
    await navigator.clipboard.writeText(created.api_key);
    setMessage("API Key 已复制");
  }

  const keys = data?.items || [];

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
              <KeyRound className="h-5 w-5" />
            </div>
            <CardTitle>创建 API Key</CardTitle>
            <CardDescription>用于脚本、CI 或外部系统调用受保护接口。</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleCreate}>
              <div className="space-y-2">
                <Label htmlFor="key-name">名称</Label>
                <Input
                  id="key-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="ci-deploy"
                />
              </div>
              <Button type="submit" disabled={submitting}>
                <Plus className="h-4 w-4" />
                {submitting ? "创建中..." : "创建"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>已创建的 API Key</CardTitle>
            <CardDescription>只展示前缀和状态；完整密钥只会在创建后显示一次。</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading && <p className="text-sm text-muted-foreground">加载中...</p>}
            {error && <p className="text-sm text-destructive">{error.message}</p>}
            {!isLoading && !error && keys.length === 0 && (
              <p className="text-sm text-muted-foreground">暂无 API Key。</p>
            )}
            <div className="space-y-3">
              {keys.map((key) => (
                <div
                  key={key.id}
                  className="grid gap-3 rounded-lg border border-border bg-background/40 p-4 md:grid-cols-[1fr_auto]"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{key.name || "未命名"}</span>
                      <span className="rounded-md bg-secondary px-2 py-1 font-mono text-xs text-muted-foreground">
                        {key.key_prefix}
                      </span>
                      {key.revoked_at && (
                        <span className="rounded-md bg-destructive/10 px-2 py-1 text-xs text-destructive">
                          已撤销
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      创建于 {formatDate(key.created_at)}
                      {key.revoked_at ? `，撤销于 ${formatDate(key.revoked_at)}` : ""}
                    </p>
                  </div>
                  {!key.revoked_at && (
                    <Button variant="destructive" size="sm" onClick={() => handleRevoke(key.id)}>
                      <Trash2 className="h-4 w-4" />
                      撤销
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {created && (
        <Card>
          <CardHeader>
            <CardTitle>新 API Key</CardTitle>
            <CardDescription>请立即保存，刷新或离开页面后将无法再次查看完整密钥。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 md:flex-row md:items-center">
            <code className="min-w-0 flex-1 overflow-x-auto rounded-md bg-secondary px-3 py-2 text-sm">
              {created.api_key}
            </code>
            <Button variant="outline" onClick={copyCreatedKey}>
              <Copy className="h-4 w-4" />
              复制
            </Button>
          </CardContent>
        </Card>
      )}

      {message && (
        <div className="rounded-md border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          {message}
        </div>
      )}
    </div>
  );
}
