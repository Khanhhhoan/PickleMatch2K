"use client";

/**
 * Quên mật khẩu: người chơi nhập email để nhận liên kết đặt lại. Máy chủ trả cùng một câu cho mọi email (không lộ
 * email nào có tài khoản), nên trang chỉ hiện đúng câu đó sau khi gửi.
 */
import React, { useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { errorMessage, fetchApi } from "@/lib/api";

const INPUT =
  "w-full px-5 py-3.5 border-2 border-zinc-200 rounded-2xl text-base text-zinc-900 bg-white focus:outline-none focus:border-zinc-950 transition-colors placeholder:text-zinc-400 font-medium";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sentMessage, setSentMessage] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetchApi("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
      setSentMessage(res?.message || "Nếu email này thuộc một tài khoản người chơi, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu.");
    } catch (err) {
      setError(errorMessage(err, "Không gửi được yêu cầu. Vui lòng thử lại."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans selection:bg-zinc-950 selection:text-white">
      <Navbar />

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-10 sm:py-16">
        <div className="max-w-lg w-full">
          <div className="bg-white rounded-3xl p-8 sm:p-12 border border-zinc-200/90 shadow-lg">
            <h1 className="text-3xl sm:text-4xl font-black text-zinc-950 text-center tracking-tight mb-3">Quên Mật Khẩu</h1>

            {sentMessage ? (
              <div className="space-y-6 mt-6">
                <div className="bg-emerald-50 text-emerald-800 p-4 rounded-2xl text-sm font-semibold border border-emerald-200" role="status">
                  {sentMessage}
                </div>
                <p className="text-sm text-zinc-600">
                  Liên kết có hiệu lực trong 30 phút. Không thấy thư thì đợi vài phút hoặc gửi lại sau.
                </p>
                <Link
                  href="/login"
                  className="block w-full text-center bg-zinc-950 hover:bg-zinc-800 text-white font-black py-4 rounded-2xl text-base transition-all btn-press shadow-md"
                >
                  Quay Lại Đăng Nhập
                </Link>
              </div>
            ) : (
              <>
                <p className="text-sm text-zinc-600 text-center mb-8">
                  Nhập email bạn đã dùng để đăng ký. Chúng tôi sẽ gửi liên kết để bạn đặt mật khẩu mới.
                </p>

                {error && (
                  <div className="bg-red-50 text-red-700 p-4 rounded-2xl mb-6 text-sm font-semibold border border-red-200" role="alert">
                    {error}
                  </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                  <div>
                    <label htmlFor="forgot-email" className="block text-sm font-bold text-zinc-900 mb-2">
                      Địa chỉ Email
                    </label>
                    <input
                      id="forgot-email"
                      type="email"
                      required
                      autoComplete="email"
                      className={INPUT}
                      placeholder="VD: player@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full bg-zinc-950 hover:bg-zinc-800 active:bg-zinc-900 text-white font-black py-4 rounded-2xl text-base transition-all btn-press disabled:opacity-60 cursor-pointer shadow-md"
                  >
                    {loading ? "Đang gửi..." : "Gửi Link Đặt Lại"}
                  </button>
                </form>
              </>
            )}
          </div>

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
