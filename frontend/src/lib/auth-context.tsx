"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { UNAUTHORIZED_EVENT, describeApiError, getApiBaseUrl } from "@/lib/api";

export interface PlayerProfile {
  user_id: number;
  full_name?: string | null;
  phone?: string | null;
  skill_level?: number | null;
  play_style?: string | null;
  matches_played?: number | null;
  matches_won?: number | null;
  win_rate?: number | null;
  date_of_birth?: string | null;
  age?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  purpose?: string | null;
}

export interface UserProfile {
  id: number;
  email: string;
  role: string;
  is_active?: boolean;
  player_profile?: PlayerProfile | null;
  owner_profile?: {
    user_id: number;
    full_name?: string | null;
    phone?: string | null;
    company_name?: string | null;
    bank_account?: string | null;
  } | null;
  staff_profile?: {
    user_id: number;
    venue_id?: number | null;
    venue_name?: string | null;
    owner_name?: string | null;
    full_name?: string | null;
    phone?: string | null;
  } | null;
}

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Đăng ký công khai luôn tạo tài khoản Người chơi. */
  register: (email: string, password: string, fullName: string, phone?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
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
        setUser(data);
      } else {
        // Token invalid
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
      }
    } catch {
      console.error("Failed to fetch user");
    }
  }, []);

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (storedToken) {
      setToken(storedToken);
      fetchUser(storedToken).finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [fetchUser]);

  // Máy chủ từ chối token (hết hạn, tài khoản bị khóa): đưa giao diện về trạng thái chưa đăng nhập
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
      throw new Error(describeApiError(err.detail, "Sai email hoặc mật khẩu"));
    }

    const data = await res.json();
    localStorage.setItem("token", data.access_token);
    setToken(data.access_token);
    await fetchUser(data.access_token);
  };

  const register = async (email: string, password: string, fullName: string, phone?: string) => {
    const apiBase = getApiBaseUrl();
    const res = await fetch(`${apiBase}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name: fullName, phone: phone || null }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(describeApiError(err.detail, "Đăng ký thất bại. Vui lòng kiểm tra lại thông tin."));
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    if (token) {
      await fetchUser(token);
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
