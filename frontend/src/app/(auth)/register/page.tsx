"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { register } = useAuth();
  const { success: toastSuccess } = useToast();

  const handlePlayerRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Mật khẩu xác nhận không trùng khớp! Vui lòng kiểm tra lại.");
      return;
    }

    setLoading(true);

    try {
      await register(email, password, fullName.trim(), phone.trim() || undefined);
      toastSuccess("Đăng ký thành công! Đăng nhập để thiết lập hồ sơ ghép trận.");
      router.push("/login?next=/onboarding");
    } catch (err: any) {
      setError(err.message || "Đăng ký thất bại");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans selection:bg-zinc-950 selection:text-white">
      <Navbar />

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-10 sm:py-16">
        <div className="max-w-lg w-full">
          {/* Large Clean Register Card */}
          <div className="bg-white rounded-3xl p-8 sm:p-12 border border-zinc-200/90 shadow-lg">
            <div className="text-center mb-8">
              <h1 className="text-3xl sm:text-4xl font-black text-zinc-950 tracking-tight">
                Đăng Ký Tài Khoản
              </h1>
            </div>

            {error && (
              <div className="bg-red-50 text-red-700 p-4 rounded-2xl mb-6 text-sm font-semibold border border-red-200 flex items-center gap-2">
                <span>{error}</span>
              </div>
            )}

            {/* Player Register Form */}
            <form onSubmit={handlePlayerRegister} className="space-y-5">
              <div>
                <label className="block text-sm font-bold text-zinc-900 mb-2">
                  Họ và Tên
                </label>
                <input
                  type="text"
                  required
                  className="w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium"
                  placeholder="VD: Nguyễn Văn A"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-zinc-900 mb-2">
                  Địa Chỉ Email
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
                  Số Điện Thoại <span className="font-medium text-zinc-400">(không bắt buộc)</span>
                </label>
                <input
                  type="tel"
                  inputMode="numeric"
                  pattern="[0-9+ .\-]{9,15}"
                  title="Số điện thoại gồm 9-12 chữ số"
                  className="w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium"
                  placeholder="Để cụm sân và bạn chơi liên hệ khi cần"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-zinc-900 mb-2">
                  Mật Khẩu
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  className="w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium"
                  placeholder="Tối thiểu 6 ký tự"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-zinc-900 mb-2">
                  Xác Nhận Mật Khẩu
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  className="w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium"
                  placeholder="Nhập lại mật khẩu"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 bg-zinc-950 hover:bg-zinc-800 active:bg-zinc-900 text-white font-black py-4 rounded-2xl text-base transition-all btn-press disabled:opacity-60 cursor-pointer shadow-md"
              >
                {loading ? "Đang tạo tài khoản..." : "Đăng Ký Tài Khoản"}
              </button>
            </form>

            <div className="mt-8 text-center pt-6 border-t border-zinc-100">
              <p className="text-sm text-zinc-600 font-medium">
                Đã có tài khoản?{" "}
                <Link href="/login" className="text-zinc-950 font-black hover:underline">
                  Đăng nhập ngay
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

