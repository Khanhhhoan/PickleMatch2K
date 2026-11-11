"use client";

/**
 * Đặt lại mật khẩu từ liên kết trong thư: /reset-password?token=...
 * Mã được đọc một lần rồi xóa khỏi thanh địa chỉ. Chỉ khi bấm xác nhận (POST) mật khẩu mới đổi, nên trình quét liên
 * kết của hộp thư có mở trang trước cũng không làm mất liên kết.
 */
import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { useToast } from "@/components/Toast";
import { ApiError, errorMessage, fetchApi } from "@/lib/api";

const INPUT =
  "w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium";
const CARD = "bg-white rounded-3xl p-8 sm:p-12 border border-zinc-200/90 shadow-lg";
const PRIMARY =
  "block w-full text-center bg-zinc-950 hover:bg-zinc-800 active:bg-zinc-900 text-white font-black py-4 rounded-2xl text-base transition-all btn-press disabled:opacity-60 cursor-pointer shadow-md";

function ResetPasswordContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { success: toastSuccess } = useToast();
  // Đọc mã một lần lúc mở trang; sau đó mã không còn trên thanh địa chỉ
  const [token] = useState(() => searchParams?.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [linkDead, setLinkDead] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("token")) {
      window.history.replaceState(null, "", "/reset-password");
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Mật khẩu mới phải có ít nhất 6 ký tự.");
      return;
    }
    if (password !== confirm) {
      setError("Xác nhận mật khẩu không khớp.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetchApi("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      toastSuccess(res?.message || "Đã đặt lại mật khẩu. Hãy đăng nhập bằng mật khẩu mới.");
      router.push("/login");
    } catch (err) {
      setLinkDead(err instanceof ApiError && err.status === 400);
      setError(errorMessage(err, "Không đặt lại được mật khẩu. Vui lòng thử lại."));
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className={CARD}>
        <h1 className="text-3xl sm:text-4xl font-black text-zinc-950 text-center tracking-tight mb-4">Đặt Lại Mật Khẩu</h1>
        <p className="text-sm text-zinc-600 text-center mb-8">
          Liên kết không đầy đủ. Hãy mở lại đúng liên kết trong thư, hoặc yêu cầu một liên kết mới.
        </p>
        <Link href="/forgot-password" className={PRIMARY}>
          Gửi Lại Link Mới
        </Link>
      </div>
    );
  }

  return (
    <div className={CARD}>
      <h1 className="text-3xl sm:text-4xl font-black text-zinc-950 text-center tracking-tight mb-3">Đặt Lại Mật Khẩu</h1>
      <p className="text-sm text-zinc-600 text-center mb-8">Nhập mật khẩu mới cho tài khoản của bạn.</p>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-2xl mb-6 text-sm font-semibold border border-red-200" role="alert">
          <p>{error}</p>
          {linkDead && (
            <Link href="/forgot-password" className="inline-block mt-2 font-black text-red-800 underline">
              Gửi lại link mới
            </Link>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="new-password" className="block text-sm font-bold text-zinc-900 mb-2">
            Mật khẩu mới
          </label>
          <input
            id="new-password"
            type="password"
            required
            autoComplete="new-password"
            className={INPUT}
            placeholder="Ít nhất 6 ký tự"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="confirm-password" className="block text-sm font-bold text-zinc-900 mb-2">
            Nhập lại mật khẩu mới
          </label>
          <input
            id="confirm-password"
            type="password"
            required
            autoComplete="new-password"
            className={INPUT}
            placeholder="••••••••"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>

        <button type="submit" disabled={loading} className={PRIMARY}>
          {loading ? "Đang lưu..." : "Đặt Mật Khẩu Mới"}
        </button>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans selection:bg-zinc-950 selection:text-white">
      <Navbar />

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-10 sm:py-16">
        <div className="max-w-lg w-full">
          <Suspense fallback={<div className="h-80 rounded-3xl bg-white border border-zinc-200 animate-pulse" />}>
            <ResetPasswordContent />
          </Suspense>

          <div className="mt-6 text-center">
            <Link href="/login" className="text-sm font-semibold text-zinc-500 hover:text-zinc-950 transition">
              ← Quay lại đăng nhập
            </Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
