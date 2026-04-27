import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type TaskStatus = "pending" | "ready" | "running" | "success" | "failed" | "canceled";

const statusConfig: Record<TaskStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" }> = {
  pending: { label: "等待中", variant: "warning" },
  ready: { label: "就绪", variant: "info" },
  running: { label: "运行中", variant: "default" },
  success: { label: "成功", variant: "success" },
  failed: { label: "失败", variant: "destructive" },
  canceled: { label: "已取消", variant: "secondary" },
};

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status as TaskStatus] || { label: status, variant: "outline" as const };
  
  return (
    <Badge variant={config.variant} className={cn("font-medium", className)}>
      {status === "running" && (
        <span className="mr-1.5 h-2 w-2 animate-pulse rounded-full bg-current" />
      )}
      {config.label}
    </Badge>
  );
}
