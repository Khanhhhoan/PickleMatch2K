"use client";

import React, { useCallback, useState, useEffect, Suspense } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { fetchApi } from "@/lib/api";
import { useWebSocket } from "@/lib/use-websocket";

const navItems = [
  { href: "/owner/dashboard", label: "Tổng quan", key: "overview" },
  { href: "/owner/bookings", label: "Lịch đặt", key: "bookings" },
  { href: "/owner/venues?tab=info_sepay", label: "Thông tin & nhận tiền", key: "payment" },
  { href: "/owner/venues?tab=courts_pricing", label: "Sân & bảng giá", key: "courts" },
  { href: "/owner/venues?tab=hours", label: "Giờ hoạt động", key: "hours" },
  { href: "/owner/venues?tab=staff", label: "Nhân sự", key: "staff" },
];

const LIVE_EVENTS = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "BOOKING_STATUS_CHANGED", "SLOT_RELEASED", "BOOKING_RESCHEDULED"];

function OwnerLayoutInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, logout, isLoading } = useAuth();
  const [mobileDrawer, setMobileDrawer] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [venueName, setVenueName] = useState("");

  const currentTab = searchParams.get("tab");
  const isManager = user?.role === "OWNER" || user?.role === "ADMIN";

  // Cổng chủ sân chỉ dành cho Chủ sân và Admin
  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (user.role === "STAFF") router.replace("/staff/dashboard");
    else if (!isManager) router.replace("/");
  }, [user, isLoading, isManager, router]);

  const loadMetadata = useCallback(() => {
    fetchApi("/bookings/owner/list")
      .then((bookings: { status: string; refund_status?: string | null }[]) => {
        // Việc cần xử lý: đơn chờ thu cọc tại quầy và yêu cầu hoàn tiền chưa chuyển
        const pending = bookings.filter((b) => b.status === "PENDING" || b.refund_status === "PENDING").length;
        setPendingCount(pending);
      })
      .catch(() => {});

    fetchApi("/venues/me")
      .then((venues: { name?: string }[]) => {
        setVenueName(venues?.[0]?.name || "");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!isManager) return;
    loadMetadata();
    const interval = setInterval(loadMetadata, 30000);
    return () => clearInterval(interval);
  }, [isManager, loadMetadata]);

  // WebSocket Live Sync
  const { lastMessage } = useWebSocket("/api/v1/ws/live");
  useEffect(() => {
    if (isManager && lastMessage && LIVE_EVENTS.includes(lastMessage.type)) loadMetadata();
  }, [isManager, lastMessage, loadMetadata]);

  const isItemActive = (item: typeof navItems[0]) => {
    if (item.key === "overview") {
      return pathname === "/owner/dashboard";
    }
    if (item.key === "bookings") {
      return pathname.startsWith("/owner/bookings");
    }
    if (pathname.startsWith("/owner/venues")) {
      if (item.key === "courts") return currentTab === "courts_pricing";
      if (item.key === "hours") return currentTab === "hours";
      if (item.key === "staff") return currentTab === "staff";
      if (item.key === "payment") return currentTab === "info_sepay" || !currentTab;
    }
    return false;
  };

  const currentNav = navItems.find((n) => isItemActive(n)) || navItems[0];
  const displayName = user?.owner_profile?.full_name || user?.email?.split("@")[0] || "";
  const roleLabel = user?.role === "ADMIN" ? "Quản trị viên" : "Chủ sân";

  if (isLoading || !isManager) {
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
          <Link href="/owner/dashboard" className="flex items-center gap-2">
            <div className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg bg-white p-1 shadow-xs">
              <Image
                src="/images/logo_transparent.png"
                alt="PickleMatch2K"
                width={256}
                height={256}
                unoptimized
                loading="eager"
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
                    <Image
                      src="/images/logo_transparent.png"
                      alt="PickleMatch2K"
                      width={256}
                      height={256}
                      unoptimized
                      loading="eager"
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
                      Cổng Chủ Sân
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
                  const active = isItemActive(item);
                  return (
                    <Link
                      key={item.key}
                      href={item.href}
                      onClick={() => setMobileDrawer(false)}
                      className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                        active
                          ? "bg-[#476cf3] text-white shadow-md shadow-[#476cf3]/30"
                          : "text-[#9daec7] hover:bg-white/10 hover:text-white"
                      }`}
                    >
                      <span>{item.label}</span>
                      {item.key === "bookings" && pendingCount > 0 && (
                        <span className="px-2 py-0.5 bg-[#e9a451]/20 text-[#ffc97f] rounded-md text-[10px] font-black">
                          {pendingCount}
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
                  CS
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

      {/* Desktop Sidebar (SânHub Style - Width 242px, Background #101c31) */}
      <aside className="hidden md:flex w-[242px] bg-[#101c31] text-[#9faec4] flex-col shrink-0 h-full justify-between z-20 sticky top-0 px-4 py-6">
        <div>
          {/* Brand Logo & Name */}
          <Link href="/owner/dashboard" className="flex items-center gap-3 px-2 mb-6 group select-none">
            <div className="w-10 h-10 shrink-0 flex items-center justify-center rounded-xl bg-white p-1.5 shadow-sm border border-white/20 group-hover:scale-105 transition">
              <Image
                src="/images/logo_transparent.png"
                alt="PickleMatch2K Logo"
                width={256}
                height={256}
                unoptimized
                loading="eager"
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
                Cổng Chủ Sân
              </span>
            </div>
          </Link>

          <div className="text-[10px] font-bold tracking-[1.5px] uppercase text-[#7990ae] px-3 mb-3">
            DANH MỤC
          </div>

          {/* Nav Items: Pure text typography, no icons */}
          <nav className="space-y-1">
            {navItems.map((item) => {
              const active = isItemActive(item);
              return (
                <Link
                  key={item.key}
                  href={item.href}
                  className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl text-[13.5px] font-bold transition-all ${
                    active
                      ? "bg-[#476cf3] text-white shadow-[0_7px_18px_rgba(24,42,98,0.5)]"
                      : "text-[#9daec7] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <span>{item.label}</span>
                  {item.key === "bookings" && pendingCount > 0 && (
                    <span className="px-2 py-0.5 rounded-md bg-[#e9a451]/20 text-[#ffc97f] text-[10px] font-black">
                      {pendingCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Clean bottom - No helper card, no account widget */}
        <div className="mt-auto" />
      </aside>

      {/* Main Body */}
      <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        {/* Topbar: Height 76px, White background, Line #e8edf3 */}
        <header className="h-[76px] bg-white border-b border-[#e8edf3] flex items-center justify-between px-6 sm:px-9 shrink-0 gap-4 z-10">
          <div className="text-[13px] text-[#9ba5b5] flex items-center gap-1.5">
            <span>Không gian quản lý</span>
            <span>/</span>
            <b className="text-[#3d4e68] font-bold">{currentNav.label}</b>
          </div>

          {/* Top-Right Account Area */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#405c94] text-white flex items-center justify-center text-xs font-black shrink-0 shadow-xs">
                CS
              </div>
              <div className="text-left">
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

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#f5f7fb]" />}>
      <OwnerLayoutInner>{children}</OwnerLayoutInner>
    </Suspense>
  );
}
