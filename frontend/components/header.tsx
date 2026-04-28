"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, LogOut, Search, User } from "lucide-react";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface HeaderProps {
  title: string;
  description?: string;
}

export function Header({ title, description }: HeaderProps) {
  const router = useRouter();

  async function handleLogout() {
    try {
      await authApi.logout();
    } catch {
      // The token should still be cleared locally if the server-side session is already gone.
    } finally {
      localStorage.removeItem("token");
      localStorage.removeItem("token_expires_at");
      localStorage.removeItem("principal_username");
      localStorage.removeItem("auth_mode");
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div>
        <h1 className="text-lg font-semibold">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            type="search"
            placeholder="搜索..."
            className="w-64 pl-8"
          />
        </div>

        {/* Notifications */}
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-4 w-4" />
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-primary" />
        </Button>

        <Button variant="ghost" size="icon" asChild>
          <Link href="/login" aria-label="登录">
            <User className="h-4 w-4" />
          </Link>
        </Button>

        <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="退出登录">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
