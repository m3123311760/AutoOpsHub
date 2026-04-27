"use client";

import { useState, useEffect } from "react";
import useSWR, { mutate } from "swr";
import { Settings, Loader2, XCircle, Save } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { workpieceApi, type WorkpieceSetting, type HandlingStrategy } from "@/lib/api";

interface SettingsContentProps {
  workpiece: string;
}

const actionLabels = {
  auto_execute: "自动执行",
  auto_cancel: "自动取消",
  schedule_execute: "延迟执行",
  schedule_cancel: "延迟取消",
};

export function SettingsContent({ workpiece }: SettingsContentProps) {
  const { data, error, isLoading } = useSWR(
    `setting-${workpiece}`,
    () => workpieceApi.getSetting(workpiece)
  );

  const [setting, setSetting] = useState<WorkpieceSetting | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setSetting(data);
    }
  }, [data]);

  const handleSave = async () => {
    if (!setting) return;

    setIsSaving(true);
    try {
      await workpieceApi.updateSetting(workpiece, setting);
      mutate(`setting-${workpiece}`);
    } catch (err) {
      console.error("保存失败:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const updateStrategy = (
    field: "no_variable_strategy" | "optional_only_strategy" | "ready_strategy",
    key: keyof HandlingStrategy,
    value: string | number
  ) => {
    if (!setting) return;
    setSetting({
      ...setting,
      [field]: {
        ...setting[field],
        [key]: value,
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !setting) {
    return (
      <div className="flex h-96 flex-col items-center justify-center gap-4">
        <XCircle className="h-12 w-12 text-destructive" />
        <p className="text-muted-foreground">加载失败</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Strategy Settings */}
      <Card>
        <CardHeader>
          <CardTitle>任务处理策略</CardTitle>
          <CardDescription>
            配置不同场景下任务的自动处理行为
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* No Variable Strategy */}
          <div className="rounded-lg border border-border p-4">
            <h4 className="font-medium">无变量策略</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              当运行手册没有定义任何变量时的处理方式
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>动作</Label>
                <Select
                  value={setting.no_variable_strategy.action}
                  onValueChange={(value) =>
                    updateStrategy("no_variable_strategy", "action", value)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(actionLabels).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>延迟时间（秒）</Label>
                <Input
                  type="number"
                  min={0}
                  value={setting.no_variable_strategy.delay_seconds}
                  onChange={(e) =>
                    updateStrategy(
                      "no_variable_strategy",
                      "delay_seconds",
                      parseInt(e.target.value) || 0
                    )
                  }
                />
              </div>
            </div>
          </div>

          {/* Optional Only Strategy */}
          <div className="rounded-lg border border-border p-4">
            <h4 className="font-medium">仅可选变量策略</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              当运行手册只有可选变量（无必填变量）时的处理方式
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>动作</Label>
                <Select
                  value={setting.optional_only_strategy.action}
                  onValueChange={(value) =>
                    updateStrategy("optional_only_strategy", "action", value)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(actionLabels).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>延迟时间（秒）</Label>
                <Input
                  type="number"
                  min={0}
                  value={setting.optional_only_strategy.delay_seconds}
                  onChange={(e) =>
                    updateStrategy(
                      "optional_only_strategy",
                      "delay_seconds",
                      parseInt(e.target.value) || 0
                    )
                  }
                />
              </div>
            </div>
          </div>

          {/* Ready Strategy */}
          <div className="rounded-lg border border-border p-4">
            <h4 className="font-medium">就绪策略</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              当所有必填变量都已提供时的处理方式
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>动作</Label>
                <Select
                  value={setting.ready_strategy.action}
                  onValueChange={(value) =>
                    updateStrategy("ready_strategy", "action", value)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(actionLabels).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>延迟时间（秒）</Label>
                <Input
                  type="number"
                  min={0}
                  value={setting.ready_strategy.delay_seconds}
                  onChange={(e) =>
                    updateStrategy(
                      "ready_strategy",
                      "delay_seconds",
                      parseInt(e.target.value) || 0
                    )
                  }
                />
              </div>
            </div>
          </div>

          {/* Retention Settings */}
          <div className="rounded-lg border border-border p-4">
            <h4 className="font-medium">缺失必填变量保留时间</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              当任务缺少必填变量时，保留等待用户补充的时间（秒）
            </p>
            <div className="mt-4 max-w-xs">
              <Input
                type="number"
                min={60}
                value={setting.required_missing_retention_seconds}
                onChange={(e) =>
                  setSetting({
                    ...setting,
                    required_missing_retention_seconds: parseInt(e.target.value) || 86400,
                  })
                }
              />
              <p className="mt-1 text-xs text-muted-foreground">
                当前设置: {Math.floor(setting.required_missing_retention_seconds / 3600)} 小时{" "}
                {Math.floor((setting.required_missing_retention_seconds % 3600) / 60)} 分钟
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={isSaving}>
          {isSaving ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          保存设置
        </Button>
      </div>
    </div>
  );
}
