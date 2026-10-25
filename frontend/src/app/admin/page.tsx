"use client";

import React, { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";

// Địa chỉ cổng quản trị: theo biến môi trường, không có thì cùng máy với trang đang mở (cổng 3001).
// Lúc dựng trang ở máy chủ chưa biết máy đó nên tạm dùng localhost.
const subscribeNothing = () => () => {};
const adminUrlInBrowser = () =>
  process.env.NEXT_PUBLIC_ADMIN_URL || `${window.location.protocol}//${window.location.hostname}:3001`;
const adminUrlOnServer = () => process.env.NEXT_PUBLIC_ADMIN_URL || "http://localhost:3001";

export default function AdminRedirectPage() {
  const [countdown, setCountdown] = useState(3);
  const adminUrl = useSyncExternalStore(subscribeNothing, adminUrlInBrowser, adminUrlOnServer);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          window.location.href = adminUrl;
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [adminUrl]);

  return (
    <div className="min-h-[80vh] flex items-center justify-center p-4">
      <div className="max-w-lg w-full bg-white border border-zinc-200 rounded-3xl p-8 shadow-xl text-center">
        <div className="w-16 h-16 rounded-2xl bg-zinc-900 text-white flex items-center justify-center mx-auto mb-6 shadow-lg">
          <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </div>

        <h1 className="text-2xl font-black text-zinc-950 tracking-tight mb-2">
          Cổng Quản Trị Hệ Thống (Admin Portal)
        </h1>
        <p className="text-sm text-zinc-600 mb-6 leading-relaxed">
          Cổng Admin đã được nâng cấp thành ứng dụng quản trị riêng biệt hoạt động độc lập trên <strong className="text-zinc-950">Port 3001</strong> nhằm tối ưu hóa bảo mật và hiệu năng.
        </p>

        <div className="p-4 rounded-2xl bg-zinc-50 border border-zinc-100 mb-6">
          <p className="text-xs text-zinc-500 mb-1">Đường dẫn cổng quản trị:</p>
          <a
            href={adminUrl}
            className="text-base font-mono font-bold text-blue-600 hover:text-blue-700 underline break-all"
          >
            {adminUrl}
          </a>
          <p className="text-xs text-zinc-400 mt-2">
            Đang tự động chuyển hướng sau <strong className="text-zinc-700">{countdown}s</strong>...
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <a
            href={adminUrl}
            className="flex-1 py-3 px-4 bg-zinc-900 hover:bg-zinc-800 text-white font-bold rounded-xl text-sm transition text-center"
          >
            Truy Cập Ngay Cổng 3001 →
          </a>
          <Link
            href="/"
            className="py-3 px-4 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 font-semibold rounded-xl text-sm transition text-center"
          >
            Quay Lại Trang Chủ (Port 3000)
          </Link>
        </div>
      </div>
    </div>
  );
}
