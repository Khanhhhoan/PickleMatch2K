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

const EMPTY: AdminData = { users: [], venues: [], bookings: [], matches: [], transactions: [], stats: null, model: null };
const LIVE_EVENTS = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "SLOT_RELEASED", "BOOKING_STATUS_CHANGED", "BOOKING_RESCHEDULED", "MATCH_CREATED", "MATCH_UPDATED"];

export default function AdminDashboard() {
  const router = useRouter();
  const { user, logout, isLoading: authLoading } = useAdminAuth();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [data, setData] = useState<AdminData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

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
    const [users, venues, bookings, matches, transactions, stats, model] = await Promise.all([
      load("tài khoản", "/users/admin/users", EMPTY.users),
      load("cụm sân", "/venues/admin/all", EMPTY.venues),
      load("đơn đặt", "/bookings/admin/all", EMPTY.bookings),
      load("phòng đấu", "/matches/admin/all", EMPTY.matches),
      load("giao dịch", "/payments/transactions", EMPTY.transactions),
      load("thống kê", "/bookings/owner/stats", EMPTY.stats),
      load("mô hình", "/ml/model-info", EMPTY.model),
    ]);
    setData({ users, venues, bookings, matches, transactions, stats, model });
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
    return <div className="min-h-screen flex items-center justify-center bg-slate-50 text-sm font-semibold text-slate-600">Đang kiểm tra quyền quản trị...</div>;
  }

  const pendingVenues = data.venues.filter((v) => v.status === "PENDING").length;
  const pendingRefunds = data.bookings.filter((b) => b.refund_status === "PENDING").length;
  const nav: { key: Tab; label: string; count?: number; alert?: number }[] = [
    { key: "overview", label: "Tổng quan" },
    { key: "venues", label: "Cụm sân", count: data.venues.length, alert: pendingVenues },
    { key: "users", label: "Tài khoản", count: data.users.length },
    { key: "bookings", label: "Đơn đặt sân", count: data.bookings.length, alert: pendingRefunds },
    { key: "transactions", label: "Sổ giao dịch", count: data.transactions.length },
    { key: "matches", label: "Phòng đấu", count: data.matches.length },
  ];

  const tabProps = { data, run };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col md:flex-row font-sans text-sm">
      {toast && (
        <div
          role="status"
          className={`fixed bottom-6 right-6 z-50 px-5 py-3 rounded-xl shadow-lg border text-sm font-semibold max-w-md ${
            toast.type === "error" ? "bg-red-50 border-red-200 text-red-700" : "bg-emerald-50 border-emerald-200 text-emerald-700"
          }`}
        >
          {toast.message}
        </div>
      )}

      <aside className="w-full md:w-60 bg-white border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-5 border-b border-slate-200">
          <div className="text-base font-bold text-slate-900 tracking-tight">PickleMatch2K</div>
          <div className="text-xs text-slate-500 mt-0.5">Cổng quản trị</div>
        </div>

        <nav className="p-3 space-y-1 flex-1 text-sm font-medium">
          {nav.map((item) => (
            <button
              key={item.key}
              onClick={() => setActiveTab(item.key)}
              className={`w-full px-4 py-2.5 rounded-lg flex items-center justify-between transition cursor-pointer ${
                activeTab === item.key ? "bg-blue-600 text-white font-bold shadow-xs" : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              <span>{item.label}</span>
              <span className="flex items-center gap-1.5">
                {!!item.alert && (
                  <span className="text-[11px] px-1.5 py-0.5 rounded-full font-bold bg-amber-400 text-amber-950" title="Cần xử lý">
                    {item.alert}
                  </span>
                )}
                {item.count !== undefined && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-mono ${activeTab === item.key ? "bg-blue-700 text-white" : "bg-slate-100 text-slate-600"}`}>
                    {item.count}
                  </span>
                )}
              </span>
            </button>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-200 flex items-center justify-between text-sm bg-slate-50/50">
          <div className="truncate pr-2">
            <div className="font-bold truncate text-slate-900">{user.email}</div>
            <div className="text-xs text-slate-500 font-medium">Quản trị viên</div>
          </div>
          <button onClick={logout} className="px-2.5 py-1 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg text-xs font-semibold cursor-pointer transition">
            Thoát
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <header className="h-16 bg-white border-b border-slate-200 px-7 flex items-center justify-between shrink-0">
          <div className="font-bold text-base text-slate-900">{TAB_TITLE[activeTab]}</div>
          <button onClick={loadData} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-sm font-semibold cursor-pointer transition">
            Làm mới dữ liệu
          </button>
        </header>

        <div className="p-7 flex-1">
          {loading ? (
            <p className="text-sm text-slate-500">Đang tải dữ liệu quản trị...</p>
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
  );
}
