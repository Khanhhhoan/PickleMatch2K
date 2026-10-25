"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { TOKEN_KEY, UNAUTHORIZED_EVENT, describeApiError, getApiBaseUrl } from "@/lib/api";

export interface AdminUser {
  id: number;
  email: string;
  role: string;
  player_profile?: {
    full_name?: string;
    phone?: string;
  };
  owner_profile?: {
    full_name?: string;
    phone?: string;
    company_name?: string;
  };
}

interface AdminAuthContextType {
  user: AdminUser | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AdminAuthContext = createContext<AdminAuthContextType | undefined>(undefined);

/** Kiểm tra token đã lưu trong trình duyệt: trả về tài khoản Admin của nó; không dùng được nữa thì xóa token và trả về null. */
async function checkStoredToken(storedToken: string): Promise<AdminUser | null> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${storedToken}` },
    });
    const data = res.ok ? await res.json() : null;
    if (data?.role === "ADMIN") return data;
  } catch {
    // Không gọi được máy chủ: coi như chưa đăng nhập
  }
  localStorage.removeItem(TOKEN_KEY);
  return null;
}

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async (accessToken: string) => {
    try {
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/v1/users/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.role !== "ADMIN") {
          // Non-admin tried to access admin portal
          localStorage.removeItem(TOKEN_KEY);
          setToken(null);
          setUser(null);
          throw new Error("Tài khoản này không có quyền vào cổng quản trị.");
        }
        setUser(data);
      } else {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
      }
    } catch (err) {
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
      throw err;
    }
  }, []);

  // Lần đầu mở trang: kiểm tra token đã lưu xong mới đổ token và tài khoản vào state.
  // Token cũ không còn hợp lệ thì coi như chưa đăng nhập (trang chủ sẽ chuyển về màn đăng nhập)
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    let cancelled = false;
    (storedToken ? checkStoredToken(storedToken) : Promise.resolve(null)).then((admin) => {
      if (cancelled) return;
      setToken(admin ? storedToken : null);
      setUser(admin);
      setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Máy chủ từ chối token giữa phiên làm việc (hết hạn hoặc tài khoản bị khóa)
  useEffect(() => {
    const onUnauthorized = () => {
      setToken(null);
      setUser(null);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const login = async (email: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    const apiBase = getApiBaseUrl();
    const res = await fetch(`${apiBase}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(describeApiError(err.detail, "Sai email hoặc mật khẩu."));
    }

    const data = await res.json();
    const accessToken = data.access_token;

    // Verify role before setting token
    const meRes = await fetch(`${apiBase}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!meRes.ok) {
      throw new Error("Không xác thực được tài khoản. Vui lòng thử lại.");
    }

    const userData = await meRes.json();
    if (userData.role !== "ADMIN") {
      throw new Error("Tài khoản này không có quyền vào cổng quản trị.");
    }

    localStorage.setItem(TOKEN_KEY, accessToken);
    setToken(accessToken);
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    if (token) {
      await fetchUser(token);
    }
  };

  return (
    <AdminAuthContext.Provider value={{ user, token, isLoading, login, logout, refreshUser }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const context = useContext(AdminAuthContext);
  if (context === undefined) {
    throw new Error("useAdminAuth must be used within an AdminAuthProvider");
  }
  return context;
}
