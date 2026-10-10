"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { fetchApi } from "@/lib/api";

const navItems = [
  {
    href: "/staff/dashboard",
    label: "Bảng Ca Trực",
  },
  {
    href: "/staff/bookings",
    label: "Lịch Đặt & Check-in",
  },
];

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isLoading } = useAuth();
  const [mobileDrawer, setMobileDrawer] = useState(false);
  const [assignedVenueName, setAssignedVenueName] = useState<string>("");
  const [pendingRefundCount, setPendingRefundCount] = useState(0);
  const isStaff = user?.role === "STAFF" || user?.role === "ADMIN";

  // Cổng nhân viên chỉ dành cho Nhân viên (và Admin khi cần hỗ trợ)
  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (user.role === "OWNER") router.replace("/owner/dashboard");
    else if (!isStaff) router.replace("/");
  }, [user, isLoading, isStaff, router]);

  useEffect(() => {
    if (user?.role === "STAFF" || user?.role === "ADMIN") {
      fetchApi("/venues/me")
        .then((venues) => setAssignedVenueName(venues?.[0]?.name || "Chưa được gán cụm sân"))
        .catch(() => setAssignedVenueName("Chưa được gán cụm sân"));

      // Fetch pending refund count
      const fetchPending = () => {
        fetchApi("/bookings/owner/list")
          .then((bookings: any[]) => {
            const count = bookings.filter((b: any) => b.refund_status === "PENDING").length;
            setPendingRefundCount(count);
          })
          .catch(() => {});
      };
      fetchPending();
      const interval = setInterval(fetchPending, 30000);
      return () => clearInterval(interval);
    }
  }, [user]);

  const displayName = user?.staff_profile?.full_name || user?.email?.split("@")[0] || "";

  if (isLoading || !isStaff) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-zinc-950 text-white font-sans text-xs">
        <span>Đang xác thực quyền nhân viên...</span>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-40 bg-zinc-50 flex flex-col md:flex-row font-sans overflow-hidden">
      {/* Mobile Top Header */}
      <header className="md:hidden bg-zinc-950 text-white px-4 py-3 flex items-center justify-between shrink-0 z-40 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMobileDrawer(true)}
            className="px-2.5 py-1.5 rounded-md bg-zinc-800 text-xs text-zinc-300 hover:text-white font-medium cursor-pointer"
          >
            Menu
          </button>

          <Link href="/staff/dashboard" className="block">
            <span className="font-semibold text-xs text-white">Cổng Nhân Viên</span>
          </Link>
        </div>
      </header>

      {/* Mobile Slide-over Drawer */}
      {mobileDrawer && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div className="fixed inset-0 bg-zinc-950/60 backdrop-blur-xs" onClick={() => setMobileDrawer(false)} />
          <div className="relative w-64 bg-zinc-950 text-white p-4 flex flex-col justify-between z-10 animate-in slide-in-from-left">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800 mb-3">
                <div>
                  <h3 className="font-bold text-xs text-white uppercase tracking-wider">Cổng Nhân Viên</h3>
                  <p className="text-[11px] text-zinc-400 font-medium truncate max-w-[170px] mt-0.5">{assignedVenueName}</p>
                </div>
                <button onClick={() => setMobileDrawer(false)} className="text-zinc-400 hover:text-white text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 cursor-pointer">
                  Đóng
                </button>
              </div>

              <nav className="space-y-1">
                {navItems.map((item) => {
                  const active = pathname === item.href;
                  const isBookings = item.href === "/staff/bookings";
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileDrawer(false)}
                      className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                        active
                          ? "bg-zinc-800 text-white font-bold"
                          : "text-zinc-400 hover:bg-zinc-900 hover:text-white"
                      }`}
                    >
                      <span>{item.label}</span>
                      {isBookings && pendingRefundCount > 0 && (
                        <span className="ml-1.5 min-w-[18px] h-[18px] px-1 bg-amber-500 text-white text-[10px] font-black rounded-full flex items-center justify-center">
                          {pendingRefundCount}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </nav>
            </div>

            <div className="pt-3 border-t border-zinc-800">
              <div className="mb-2.5">
                <p className="text-xs font-semibold text-white truncate">{displayName}</p>
                <p className="text-[10px] text-zinc-400 truncate">{user?.email}</p>
              </div>

              <div className="flex gap-2">
                <Link
                  href="/"
                  className="flex-1 text-center py-2 text-xs font-semibold bg-zinc-900 text-zinc-300 rounded-lg hover:bg-zinc-800 hover:text-white border border-zinc-800"
                >
                  Trang Chủ
                </Link>
                <button
                  onClick={logout}
                  className="flex-1 text-center py-2 text-xs font-semibold bg-zinc-900 text-zinc-300 rounded-lg hover:bg-zinc-800 hover:text-rose-400 border border-zinc-800 cursor-pointer"
                >
                  Đăng Xuất
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-56 bg-zinc-950 text-white flex-col shrink-0 border-r border-zinc-800 h-full justify-between z-20">
        <div>
          {/* Brand Area */}
          <div className="p-4 border-b border-zinc-800">
            <Link href="/staff/dashboard" className="block">
              <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider block">
                Cổng Nhân Viên
              </span>
              <p className="text-sm font-bold text-white truncate mt-1">
                {assignedVenueName}
              </p>
            </Link>
          </div>

          {/* Shift Info Card */}
          <div className="mx-3 my-3 p-3 rounded-lg bg-zinc-900 border border-zinc-800 space-y-1">
            <div className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
              Ca Trực Hiện Tại
            </div>
            <p className="text-xs font-bold text-white truncate">{displayName}</p>
            <p className="text-[10px] text-zinc-400 truncate">{user?.email}</p>
          </div>

          {/* Navigation Items (Text Only, No Icons) */}
          <nav className="p-3 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const active = pathname === item.href;
              const isBookings = item.href === "/staff/bookings";
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-semibold transition-all ${
                    active
                      ? "bg-zinc-800 text-white font-bold"
                      : "text-zinc-400 hover:bg-zinc-900 hover:text-white"
                  }`}
                >
                  <span>{item.label}</span>
                  {isBookings && pendingRefundCount > 0 && (
                    <span className="ml-1.5 min-w-[18px] h-[18px] px-1 bg-amber-500 text-white text-[10px] font-black rounded-full flex items-center justify-center animate-pulse">
                      {pendingRefundCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User Footer Profile & Logout */}
        <div className="p-3 border-t border-zinc-800 bg-zinc-950">
          <div className="flex items-center justify-between gap-2">
            <Link
              href="/"
              className="flex-1 text-center py-2 text-xs font-semibold bg-zinc-900 text-zinc-300 rounded-lg hover:bg-zinc-800 hover:text-white border border-zinc-800 transition"
            >
              Trang Chủ
            </Link>
            <button
              onClick={logout}
              className="flex-1 text-center py-2 text-xs font-semibold bg-zinc-900 text-zinc-300 hover:text-rose-400 rounded-lg hover:bg-zinc-800 border border-zinc-800 transition cursor-pointer"
            >
              Đăng Xuất
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area (Scrollable) */}
      <main className="flex-1 h-full overflow-y-auto bg-zinc-50 p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
