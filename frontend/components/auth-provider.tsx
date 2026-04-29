"use client";

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { authApi } from "@/lib/api";

const AUTH_STORAGE_KEYS = ["token", "token_expires_at", "principal_username", "auth_mode"];

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  requireAuth: boolean;
  logout: () => Promise<void>;
  checkAuth: () => boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [requireAuth, setRequireAuth] = useState(true);

  const checkAuth = useCallback(() => {
    const token = localStorage.getItem("token");
    const expiresAt = localStorage.getItem("token_expires_at");

    if (!token) {
      return false;
    }

    if (expiresAt) {
      const expiry = new Date(expiresAt);
      if (expiry <= new Date()) {
        for (const key of AUTH_STORAGE_KEYS) {
          localStorage.removeItem(key);
        }
        return false;
      }
    }

    return true;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout errors
    } finally {
      for (const key of AUTH_STORAGE_KEYS) {
        localStorage.removeItem(key);
      }
      setIsAuthenticated(false);
      router.push("/login");
    }
  }, [router]);

  useEffect(() => {
    let canceled = false;

    async function syncAuth() {
      let authRequired = true;
      try {
        authRequired = (await authApi.getAuthStatus()).require_auth;
      } catch {
        authRequired = true;
      }
      if (canceled) return;

      const authenticated = !authRequired || checkAuth();
      setRequireAuth(authRequired);
      setIsAuthenticated(authenticated);
      setIsLoading(false);

      if (authRequired && !authenticated && pathname !== "/login") {
        router.push(`/login?next=${encodeURIComponent(pathname)}`);
      }

      if (authRequired && authenticated && pathname === "/login") {
        router.push("/");
      }
    }

    void syncAuth();

    return () => {
      canceled = true;
    };
  }, [checkAuth, pathname, router]);

  // Don't render children until auth check is complete
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">加载中...</div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, requireAuth, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}
