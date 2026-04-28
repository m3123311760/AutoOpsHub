"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  BookOpen,
  ListTodo,
  Clock,
  Settings,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const mainNav: NavItem[] = [
  {
    title: "概览",
    href: "/",
    icon: LayoutDashboard,
  },
  {
    title: "工作区",
    href: "/workpieces",
    icon: FolderKanban,
  },
];

const workpieceNav: NavItem[] = [
  {
    title: "运行手册",
    href: "/runbooks",
    icon: BookOpen,
  },
  {
    title: "任务",
    href: "/tasks",
    icon: ListTodo,
  },
  {
    title: "定时作业",
    href: "/jobs",
    icon: Clock,
  },
  {
    title: "设置",
    href: "/settings",
    icon: Settings,
  },
];

interface SidebarProps {
  currentWorkpiece?: string;
}

export function Sidebar({ currentWorkpiece }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-border bg-card">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="flex h-14 items-center border-b border-border px-4">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <Terminal className="h-4 w-4 text-primary-foreground" />
            </div>
            <span className="text-lg font-semibold">AutoOpsHub</span>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto p-4">
          {/* Main Navigation */}
          <div className="space-y-1">
            {mainNav.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  {item.title}
                </Link>
              );
            })}
          </div>

          {/* Workpiece Navigation */}
          {currentWorkpiece && (
            <>
              <div className="my-4 border-t border-border" />
              <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {currentWorkpiece}
              </div>
              <div className="space-y-1">
                {workpieceNav.map((item) => {
                  const href = `/workpieces/${currentWorkpiece}${item.href}`;
                  const isActive = pathname === href;
                  return (
                    <Link
                      key={item.href}
                      href={href}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground"
                      )}
                    >
                      <item.icon className="h-4 w-4" />
                      {item.title}
                    </Link>
                  );
                })}
              </div>
            </>
          )}
        </nav>

        {/* Footer */}
        <div className="border-t border-border p-4">
          <div className="text-xs text-muted-foreground">
            AutoOpsHub v1.0.0
          </div>
        </div>
      </div>
    </aside>
  );
}
