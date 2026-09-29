"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: string;
  manager_id: string | null;
  is_active: boolean;
  email_verified: boolean;
  avatar_color: string | null;
  // Tenant context — present on /auth/me and login responses.
  tenant_name: string | null;
  onboarding_completed: boolean | null;
}

export const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super Admin",
  company_admin: "Company Admin",
  sales_manager: "Sales Manager",
  sales_executive: "Sales Executive",
  telecaller: "Telecaller",
  marketing_executive: "Marketing Executive",
  channel_partner: "Channel Partner",
  customer_support: "Customer Support",
};

export const ADMIN_ROLES = new Set(["super_admin", "company_admin"]);
export const MANAGER_ROLES = new Set(["super_admin", "company_admin", "sales_manager"]);

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api<{ data: User }>("/auth/me");
      setUser(res.data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ data: { access_token: string; user: User } }>(
      "/auth/login",
      { method: "POST", body: { email, password } }
    );
    setToken(res.data.access_token);
    setUser(res.data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", body: {} });
    } catch {
      // best-effort server-side revocation
    }
    setToken(null);
    setUser(null);
    location.href = "/login";
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
