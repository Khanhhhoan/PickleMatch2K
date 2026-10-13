"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { fetchApi } from "@/lib/api";
import { useWebSocket } from "@/lib/use-websocket";

const navItems = [
  { href: "/staff/dashboard", label: "Bảng Ca Trực" },
  { href: "/staff/bookings", label: "Lịch Đặt & Check-in" },
];

const LIVE_EVENTS = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "BOOKING_STATUS_CHANGED", "SLOT_RELEASED", "BOOKING_RESCHEDULED"];

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isLoading } = useAuth();
  const [mobileDrawer, setMobileDrawer] = useState(false);
  const [venueName, setVenueName] = useState("");
  const [pendingRefundCount, setPendingRefundCount] = useState(0);
  const isStaff = user?.role === "STAFF" || user?.role === "ADMIN";

  // Cổng nhân viên chỉ dành cho Nhân viên (và Admin khi cần hỗ trợ)
  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (user.role === "OWNER") router.replace("/owner/dashboard");
    else if (!isStaff) router.replace("/");
  }, [user, isLoading, isStaff, router]);

  // Việc cần xử lý: yêu cầu hoàn tiền chưa chuyển cho khách
  const loadPendingRefunds = useCallback(() => {
    fetchApi("/bookings/owner/list")
      .then((bookings: { refund_status?: string | null }[]) => setPendingRefundCount(bookings.filter((b) => b.refund_status === "PENDING").length))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!isStaff) return;
    fetchApi("/venues/me")
      .then((venues: { name?: string }[]) => setVenueName(venues?.[0]?.name || "Chưa được gán cụm sân"))
      .catch(() => setVenueName("Chưa được gán cụm sân"));
    loadPendingRefunds();
    const interval = setInterval(loadPendingRefunds, 30000);
    return () => clearInterval(interval);
  }, [isStaff, loadPendingRefunds]);

  // WebSocket Live Sync
  const { lastMessage } = useWebSocket("/api/v1/ws/live");
  useEffect(() => {
    if (isStaff && lastMessage && LIVE_EVENTS.includes(lastMessage.type)) loadPendingRefunds();
  }, [isStaff, lastMessage, loadPendingRefunds]);

  const currentNav = navItems.find((item) => pathname.startsWith(item.href)) || navItems[0];
  const displayName = user?.staff_profile?.full_name || user?.email?.split("@")[0] || "";
  const roleLabel = user?.role === "ADMIN" ? "Quản trị viên" : "Nhân viên";

  if (isLoading || !isStaff) {
    return <div className="fixed inset-0 z-40 bg-[#f5f7fb] flex items-center justify-center text-xs text-[#51627c]">Đang kiểm tra quyền truy cập...</div>;
  }

  return (
    <div className="fixed inset-0 z-40 bg-[#f5f7fb] flex flex-col md:flex-row font-sans overflow-hidden text-[#17253d]">
      {/* Mobile Top Header */}
      <header className="md:hidden bg-[#101c31] text-white px-4 py-3 flex items-center justify-between shrink-0 z-40 border-b border-[#1b2b48]">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMobileDrawer(true)}
            className="px-2.5 py-1.5 rounded-lg bg-[#1a2b47] text-slate-200 hover:text-white text-xs font-semibold cursor-pointer"
          >
            Menu
          </button>
          <Link href="/staff/dashboard" className="flex items-center gap-2">
            <div className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg bg-white p-1 shadow-xs">
              <img
                src="/images/logo_transparent.png"
                alt="PickleMatch2K"
                className="w-full h-full object-contain"
              />
            </div>
            <div className="flex items-center">
              <span className="font-black text-sm text-white tracking-tight">PickleMatch</span>
              <span className="ml-1 px-1.5 py-0.5 rounded bg-[#476cf3] text-white font-black text-[10px]">
                2K
              </span>
            </div>
          </Link>
        </div>
        <div className="text-xs font-medium text-slate-300 truncate max-w-[150px]">
          {venueName}
        </div>
      </header>

      {/* Mobile Drawer */}
      {mobileDrawer && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div className="fixed inset-0 bg-[#081b34]/70 backdrop-blur-xs" onClick={() => setMobileDrawer(false)} />
          <div className="relative w-64 bg-[#101c31] text-white p-5 flex flex-col justify-between z-10">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-[#213555] mb-4">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 shrink-0 flex items-center justify-center rounded-xl bg-white p-1 shadow-xs">
                    <img
                      src="/images/logo_transparent.png"
                      alt="PickleMatch2K"
                      className="w-full h-full object-contain"
                    />
                  </div>
                  <div>
                    <div className="flex items-center">
                      <span className="font-black text-sm text-white tracking-tight">
                        PickleMatch
                      </span>
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-[#476cf3] text-white font-black text-[10px]">
                        2K
                      </span>
                    </div>
                    <p className="text-[10px] text-[#7990ae] font-semibold uppercase tracking-wider">
                      Cổng Nhân Viên
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setMobileDrawer(false)}
                  className="text-slate-400 hover:text-white text-xs font-bold px-2 py-1 bg-[#1a2b47] rounded cursor-pointer"
                >
                  Đóng
                </button>
              </div>

              {/* Mobile Nav items: Pure text, no icon */}
              <nav className="space-y-1">
                {navItems.map((item) => {
                  const active = item.href === currentNav.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileDrawer(false)}
                      className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                        active
                          ? "bg-[#476cf3] text-white shadow-md shadow-[#476cf3]/30"
                          : "text-[#9daec7] hover:bg-white/10 hover:text-white"
                      }`}
                    >
                      <span>{item.label}</span>
                      {item.href === "/staff/bookings" && pendingRefundCount > 0 && (
                        <span className="px-2 py-0.5 bg-[#e9a451]/20 text-[#ffc97f] rounded-md text-[10px] font-black">
                          {pendingRefundCount}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </nav>
            </div>

            <div className="pt-4 border-t border-[#213555]">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-xl bg-[#405c94] text-white flex items-center justify-center font-black text-xs">
                  NV
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold text-white truncate">{displayName}</p>
                  <p className="text-[10px] text-[#91a3bd] truncate">{roleLabel}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <Link
                  href="/"
                  className="flex-1 text-center py-2 text-xs font-bold bg-[#1a2b47] text-slate-200 rounded-lg hover:text-white"
                >
                  Trang chủ
                </Link>
                <button
                  onClick={logout}
                  className="flex-1 text-center py-2 text-xs font-bold bg-[#291e2b] text-rose-400 rounded-lg hover:bg-rose-900/30 cursor-pointer"
                >
                  Thoát
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Desktop Sidebar: cùng kiểu với cổng chủ sân */}
      <aside className="hidden md:flex w-[242px] bg-[#101c31] text-[#9faec4] flex-col shrink-0 h-full justify-between z-20 sticky top-0 px-4 py-6">
        <div>
          {/* Brand Logo & Name */}
          <Link href="/staff/dashboard" className="flex items-center gap-3 px-2 mb-6 group select-none">
            <div className="w-10 h-10 shrink-0 flex items-center justify-center rounded-xl bg-white p-1.5 shadow-sm border border-white/20 group-hover:scale-105 transition">
              <img
                src="/images/logo_transparent.png"
                alt="PickleMatch2K Logo"
                className="w-full h-full object-contain"
              />
            </div>
            <div className="flex flex-col justify-center">
              <div className="flex items-center">
                <span className="text-[16px] font-black tracking-tight text-white leading-tight">
                  PickleMatch
                </span>
                <span className="ml-1.5 px-1.5 py-0.5 rounded-md bg-[#476cf3] text-white font-black text-[10px] tracking-wider uppercase shadow-xs">
                  2K
                </span>
              </div>
              <span className="text-[10px] text-[#7990ae] font-bold uppercase tracking-wider mt-0.5">
                Cổng Nhân Viên
              </span>
            </div>
          </Link>

          <div className="text-[10px] font-bold tracking-[1.5px] uppercase text-[#7990ae] px-3 mb-3">
            DANH MỤC
          </div>

          {/* Nav Items: Pure text typography, no icons */}
          <nav className="space-y-1">
            {navItems.map((item) => {
              const active = item.href === currentNav.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl text-[13.5px] font-bold transition-all ${
                    active
                      ? "bg-[#476cf3] text-white shadow-[0_7px_18px_rgba(24,42,98,0.5)]"
                      : "text-[#9daec7] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <span>{item.label}</span>
                  {item.href === "/staff/bookings" && pendingRefundCount > 0 && (
                    <span className="px-2 py-0.5 rounded-md bg-[#e9a451]/20 text-[#ffc97f] text-[10px] font-black">
                      {pendingRefundCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="mt-auto" />
      </aside>

      {/* Main Body */}
      <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        {/* Topbar: Height 76px, White background, Line #e8edf3 */}
        <header className="h-[76px] bg-white border-b border-[#e8edf3] flex items-center justify-between px-6 sm:px-9 shrink-0 gap-4 z-10">
          <div className="text-[13px] text-[#9ba5b5] flex items-center gap-1.5 min-w-0">
            <span className="hidden sm:inline whitespace-nowrap">Không gian làm việc</span>
            <span className="hidden sm:inline">/</span>
            <b className="text-[#3d4e68] font-bold truncate">{currentNav.label}</b>
          </div>

          {/* Top-Right Account Area */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#405c94] text-white flex items-center justify-center text-xs font-black shrink-0 shadow-xs">
                NV
              </div>
              <div className="hidden sm:block text-left">
                <strong className="block text-xs font-bold text-[#17253d] max-w-[150px] truncate leading-tight">
                  {displayName}
                </strong>
                <span className="block text-[10.5px] text-[#8696ab] font-medium leading-tight mt-0.5">
                  {roleLabel}
                </span>
              </div>
            </div>

            <button
              onClick={logout}
              className="px-3 py-1.5 text-xs font-bold text-rose-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
              title="Đăng xuất"
            >
              Thoát
            </button>
          </div>
        </header>

        {/* Scrollable Page Content */}
        <main className="flex-1 overflow-y-auto bg-[#f5f7fb] p-6 sm:p-9 pb-16">
          <div className="max-w-[1650px] mx-auto w-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
