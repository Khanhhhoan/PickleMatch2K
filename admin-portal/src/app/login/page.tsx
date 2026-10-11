"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAdminAuth } from "@/lib/auth-context";

export default function AdminLoginPage() {
  const router = useRouter();
  const { login, user } = useAdminAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already logged in as Admin, redirect to dashboard
  React.useEffect(() => {
    if (user && user.role === "ADMIN") {
      router.replace("/");
    }
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email, password);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Đăng nhập thất bại. Vui lòng kiểm tra lại tài khoản Admin.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#101c31] p-4 relative">
      <div className="w-full max-w-md bg-white border border-[#e8edf3] rounded-2xl shadow-xl shadow-black/20 p-8 relative z-10">
        {/* Header */}
        <div className="flex flex-col items-center text-center mb-7">
          <div className="w-14 h-14 flex items-center justify-center rounded-2xl bg-white p-2 shadow-sm border border-[#e8edf3] mb-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/images/logo_transparent.png" alt="PickleMatch2K" className="w-full h-full object-contain" />
          </div>
          <div className="flex items-center">
            <span className="text-xl font-black tracking-tight text-[#17253d]">PickleMatch</span>
            <span className="ml-1.5 px-1.5 py-0.5 rounded-md bg-[#476cf3] text-white font-black text-[10px] tracking-wider uppercase">2K</span>
          </div>
          <h1 className="text-[11px] font-bold uppercase tracking-wider text-[#7990ae] mt-1">Cổng Quản Trị</h1>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-5 p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-start gap-2.5">
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[11px] font-bold text-[#51627c] mb-1.5">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email tài khoản quản trị"
              autoComplete="username"
              required
              className="w-full px-3.5 py-2.5 bg-[#f8fafd] border border-[#dde4ef] rounded-xl text-[#17253d] placeholder-[#9aa7bb] focus:outline-none focus:bg-white focus:border-[#476cf3] focus:ring-2 focus:ring-[#476cf3]/20 text-sm transition-all"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold text-[#51627c] mb-1.5">
              Mật khẩu
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              className="w-full px-3.5 py-2.5 bg-[#f8fafd] border border-[#dde4ef] rounded-xl text-[#17253d] placeholder-[#9aa7bb] focus:outline-none focus:bg-white focus:border-[#476cf3] focus:ring-2 focus:ring-[#476cf3]/20 text-sm transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3 px-4 bg-[#476cf3] hover:bg-[#3b61e8] text-white font-bold rounded-xl shadow-md shadow-[#476cf3]/20 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50 text-sm"
          >
            {loading ? (
              <>
                <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <span>Đang đăng nhập...</span>
              </>
            ) : (
              <span>Đăng nhập</span>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
