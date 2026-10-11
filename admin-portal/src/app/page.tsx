"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet } from "@/lib/api";
import { useAdminAuth } from "@/lib/auth-context";
import { useWebSocket } from "@/lib/use-websocket";
import { AdminData } from "@/lib/types";
import OverviewTab from "@/components/tabs/OverviewTab";
import VenuesTab from "@/components/tabs/VenuesTab";
import UsersTab from "@/components/tabs/UsersTab";
import BookingsTab from "@/components/tabs/BookingsTab";
import TransactionsTab from "@/components/tabs/TransactionsTab";
import MatchesTab from "@/components/tabs/MatchesTab";

type Tab = "overview" | "venues" | "users" | "bookings" | "transactions" | "matches";

const TAB_TITLE: Record<Tab, string> = {
  overview: "Tổng quan hệ thống",
  venues: "Cụm sân",
  users: "Tài khoản",
  bookings: "Đơn đặt sân",
  transactions: "Sổ giao dịch",
  matches: "Phòng đấu",
};

const EMPTY: AdminData = { users: [], venues: [], bookings: [], matches: [], transactions: [], stats: null };
const LIVE_EVENTS = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "SLOT_RELEASED", "BOOKING_STATUS_CHANGED", "BOOKING_RESCHEDULED", "MATCH_CREATED", "MATCH_UPDATED"];

export default function AdminDashboard() {
  const router = useRouter();
  const { user, logout, isLoading: authLoading } = useAdminAuth();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [data, setData] = useState<AdminData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);

  const isAdmin = user?.role === "ADMIN";

  useEffect(() => {
    if (!authLoading && !isAdmin) router.replace("/login");
  }, [authLoading, isAdmin, router]);

  const notify = useCallback((message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  /** Tải mọi dữ liệu quản trị; phần nào lỗi thì báo rõ thay vì âm thầm hiển thị danh sách rỗng. */
  const loadData = useCallback(async () => {
    const failed: string[] = [];
    const load = async <T,>(label: string, path: string, fallback: T): Promise<T> => {
      try {
        return await apiGet(path);
      } catch {
        failed.push(label);
        return fallback;
      }
    };
    const [users, venues, bookings, matches, transactions, stats] = await Promise.all([
      load("tài khoản", "/users/admin/users", EMPTY.users),
      load("cụm sân", "/venues/admin/all", EMPTY.venues),
      load("đơn đặt", "/bookings/admin/all", EMPTY.bookings),
      load("phòng đấu", "/matches/admin/all", EMPTY.matches),
      load("giao dịch", "/payments/transactions", EMPTY.transactions),
      load("thống kê", "/bookings/owner/stats", EMPTY.stats),
    ]);
    setData({ users, venues, bookings, matches, transactions, stats });
    setLoading(false);
    if (failed.length > 0) notify(`Không tải được: ${failed.join(", ")}.`, "error");
  }, [notify]);

  useEffect(() => {
    if (isAdmin) loadData();
  }, [isAdmin, loadData]);

  const { lastMessage } = useWebSocket("/api/v1/ws/live");
  useEffect(() => {
    if (lastMessage && LIVE_EVENTS.includes(lastMessage.type)) loadData();
  }, [lastMessage, loadData]);

  const run = useCallback(
    async (action: () => Promise<unknown>, successMessage = "Đã lưu.") => {
      try {
        const result = await action();
        const serverMessage = (result as { message?: unknown } | null)?.message;
        notify(typeof serverMessage === "string" ? serverMessage : successMessage);
        await loadData();
        return true;
      } catch (err) {
        notify(err instanceof Error ? err.message : "Thao tác không thực hiện được.", "error");
        return false;
      }
    },
    [loadData, notify],
  );

  if (authLoading || !isAdmin || !user) {
    return <div className="fixed inset-0 bg-[#f5f7fb] flex items-center justify-center text-xs text-[#51627c]">Đang kiểm tra quyền quản trị...</div>;
  }

  const pendingVenues = data.venues.filter((v) => v.status === "PENDING").length;
  const pendingRefunds = data.bookings.filter((b) => b.refund_status === "PENDING").length;
  const nav: { key: Tab; label: string; alert?: number }[] = [
    { key: "overview", label: "Tổng quan" },
    { key: "venues", label: "Cụm sân", alert: pendingVenues },
    { key: "users", label: "Tài khoản" },
    { key: "bookings", label: "Đơn đặt sân", alert: pendingRefunds },
    { key: "transactions", label: "Sổ giao dịch" },
    { key: "matches", label: "Phòng đấu" },
  ];
  const currentLabel = nav.find((item) => item.key === activeTab)?.label || "";
  const todayLabel = new Date().toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
  const tabProps = { data, run };

  // Cùng khung với khu vực chủ sân: thanh bên tối, thanh trên trắng, nội dung trên nền xám nhạt
  const brand = (
    <div className="flex items-center gap-3 select-none">
      <div className="w-10 h-10 shrink-0 flex items-center justify-center rounded-xl bg-white p-1.5 shadow-sm border border-white/20">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/logo_transparent.png" alt="PickleMatch2K" className="w-full h-full object-contain" />
      </div>
      <div className="flex flex-col justify-center">
        <div className="flex items-center">
          <span className="text-[16px] font-black tracking-tight text-white leading-tight">PickleMatch</span>
          <span className="ml-1.5 px-1.5 py-0.5 rounded-md bg-[#476cf3] text-white font-black text-[10px] tracking-wider uppercase shadow-xs">2K</span>
        </div>
        <span className="text-[10px] text-[#7990ae] font-bold uppercase tracking-wider mt-0.5">Cổng Quản Trị</span>
      </div>
    </div>
  );

  const navButtons = (afterPick?: () => void) =>
    nav.map((item) => {
      const active = activeTab === item.key;
      return (
        <button
          key={item.key}
          type="button"
          onClick={() => {
            setActiveTab(item.key);
            afterPick?.();
          }}
          className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-[13.5px] font-bold transition-all cursor-pointer ${
            active ? "bg-[#476cf3] text-white shadow-[0_7px_18px_rgba(24,42,98,0.5)]" : "text-[#9daec7] hover:text-white hover:bg-white/10"
          }`}
        >
          <span>{item.label}</span>
          {!!item.alert && (
            <span className="px-2 py-0.5 rounded-md bg-[#e9a451]/20 text-[#ffc97f] text-[10px] font-black" title="Cần xử lý">
              {item.alert}
            </span>
          )}
        </button>
      );
    });

  return (
    <div className="fixed inset-0 bg-[#f5f7fb] flex flex-col md:flex-row font-sans overflow-hidden text-[#17253d]">
      {toast && (
        <div
          role="status"
          className={`fixed bottom-6 right-6 z-[60] px-5 py-3 rounded-xl shadow-lg border text-xs font-bold max-w-md ${
            toast.type === "error" ? "bg-red-50 border-red-200 text-red-700" : "bg-emerald-50 border-emerald-200 text-emerald-700"
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* Điện thoại: thanh trên tối và menu xổ xuống */}
      <header className="md:hidden bg-[#101c31] px-4 py-3 flex items-center justify-between shrink-0 border-b border-[#1b2b48]">
        {brand}
        <button
          type="button"
          onClick={() => setMobileMenu((open) => !open)}
          className="px-2.5 py-1.5 rounded-lg bg-[#1a2b47] text-slate-200 hover:text-white text-xs font-semibold cursor-pointer"
        >
          Menu
        </button>
      </header>
      {mobileMenu && (
        <div className="md:hidden bg-[#101c31] px-4 pb-4 space-y-1 shrink-0">
          {navButtons(() => setMobileMenu(false))}
          <button type="button" onClick={logout} className="w-full text-left px-3.5 py-2.5 rounded-xl text-[13.5px] font-bold text-rose-400 hover:bg-white/10 cursor-pointer">
            Thoát
          </button>
        </div>
      )}

      <aside className="hidden md:flex w-[242px] bg-[#101c31] text-[#9faec4] flex-col shrink-0 h-full px-4 py-6">
        <div className="px-2 mb-6">{brand}</div>
        <div className="text-[10px] font-bold tracking-[1.5px] uppercase text-[#7990ae] px-3 mb-3">Danh mục</div>
        <nav className="space-y-1">{navButtons()}</nav>
      </aside>

      <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        <header className="hidden md:flex h-[76px] bg-white border-b border-[#e8edf3] items-center justify-between px-6 sm:px-9 shrink-0 gap-4">
          <div className="text-[13px] text-[#9ba5b5] flex items-center gap-1.5">
            <span>Không gian quản trị</span>
            <span>/</span>
            <b className="text-[#3d4e68] font-bold">{currentLabel}</b>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#405c94] text-white flex items-center justify-center text-xs font-black shrink-0 shadow-xs">QT</div>
              <div className="text-left">
                <strong className="block text-xs font-bold text-[#17253d] max-w-[200px] truncate leading-tight">{user.email}</strong>
                <span className="block text-[10.5px] text-[#8696ab] font-medium leading-tight mt-0.5">Quản trị viên</span>
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              className="px-3 py-1.5 text-xs font-bold text-rose-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
              title="Đăng xuất"
            >
              Thoát
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto bg-[#f5f7fb] p-6 sm:p-9 pb-16">
          <div className="max-w-[1650px] mx-auto w-full space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-[#6b7ba1] first-letter:uppercase">{todayLabel}</p>
                <h1 className="text-2xl sm:text-[26px] font-black text-[#17253d] tracking-tight m-0 mt-0.5">{TAB_TITLE[activeTab]}</h1>
              </div>
              <button
                type="button"
                onClick={loadData}
                className="self-start sm:self-auto px-3.5 py-2.5 bg-white hover:bg-[#f1f4fb] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] whitespace-nowrap cursor-pointer"
              >
                Làm mới dữ liệu
              </button>
            </div>

            {loading ? (
              <p className="text-xs text-[#51627c]">Đang tải dữ liệu quản trị...</p>
            ) : (
              <>
                {activeTab === "overview" && <OverviewTab {...tabProps} />}
                {activeTab === "venues" && <VenuesTab {...tabProps} />}
                {activeTab === "users" && <UsersTab {...tabProps} currentUserId={user.id} />}
                {activeTab === "bookings" && <BookingsTab {...tabProps} />}
                {activeTab === "transactions" && <TransactionsTab {...tabProps} />}
                {activeTab === "matches" && <MatchesTab {...tabProps} />}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
