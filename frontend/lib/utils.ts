import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateString: string) {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function getStatusColor(status: string) {
  switch (status) {
    case "pending":
      return "text-warning";
    case "ready":
      return "text-info";
    case "running":
      return "text-primary";
    case "success":
      return "text-success";
    case "failed":
      return "text-destructive";
    case "canceled":
      return "text-muted-foreground";
    default:
      return "text-foreground";
  }
}

export function getStatusBgColor(status: string) {
  switch (status) {
    case "pending":
      return "bg-warning/10";
    case "ready":
      return "bg-info/10";
    case "running":
      return "bg-primary/10";
    case "success":
      return "bg-success/10";
    case "failed":
      return "bg-destructive/10";
    case "canceled":
      return "bg-muted";
    default:
      return "bg-muted";
  }
}
