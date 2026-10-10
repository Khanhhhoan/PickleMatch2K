"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login, user } = useAuth();

  // Redirect if already logged in
  useEffect(() => {
    if (user) {
      if (user.role === "STAFF") router.push("/staff/dashboard");
      else if (user.role === "OWNER") router.push("/owner/dashboard");
      else if (user.role === "ADMIN") router.push("/admin");
      else router.push("/");
    }
  }, [user, router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || "Email hoặc mật khẩu không chính xác.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans selection:bg-zinc-950 selection:text-white">
      <Navbar />

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-10 sm:py-16">
        <div className="max-w-lg w-full">
          {/* Large Clean Login Card */}
          <div className="bg-white rounded-3xl p-8 sm:p-12 border border-zinc-200/90 shadow-lg">
            <h1 className="text-3xl sm:text-4xl font-black text-zinc-950 text-center tracking-tight mb-8">
              Đăng Nhập
            </h1>

            {error && (
              <div className="bg-red-50 text-red-700 p-4 rounded-2xl mb-6 text-sm font-semibold border border-red-200 flex items-center gap-2">
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-bold text-zinc-900 mb-2">
                  Địa chỉ Email
                </label>
                <input
                  type="email"
                  required
                  className="w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium"
                  placeholder="VD: player@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-zinc-900 mb-2">
                  Mật khẩu
                </label>
                <input
                  type="password"
                  required
                  className="w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 bg-zinc-950 hover:bg-zinc-800 active:bg-zinc-900 text-white font-black py-4 rounded-2xl text-base transition-all btn-press disabled:opacity-60 cursor-pointer shadow-md"
              >
                {loading ? "Đang đăng nhập..." : "Đăng Nhập"}
              </button>
            </form>

            <div className="mt-8 text-center pt-6 border-t border-zinc-100">
              <p className="text-sm text-zinc-600 font-medium">
                Chưa có tài khoản?{" "}
                <Link href="/register" className="text-zinc-950 font-black hover:underline">
                  Đăng ký ngay
                </Link>
              </p>
            </div>
          </div>

          {/* Back to Home Link */}
          <div className="mt-6 text-center">
            <Link href="/" className="text-sm font-semibold text-zinc-500 hover:text-zinc-950 transition">
              ← Quay lại trang chủ
            </Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
