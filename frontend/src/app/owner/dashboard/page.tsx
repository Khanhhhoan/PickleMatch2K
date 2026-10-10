"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchApi, formatLocalDate, formatVND, parseUtcDate } from "@/lib/api";
import { Booking, bookingCode, bookingStatusLabel, bookingStatusTone, mergeSlots, paymentStatusLabel } from "@/lib/booking";
import { useWebSocket } from "@/lib/use-websocket";

interface Stats {
  total_revenue: number;
  collected_amount: number;
  refunded_amount: number;
  deposit_collected: number;
  completed_bookings: number;
  pending_bookings: number;
  pending_refunds: number;
  total_bookings: number;
  total_courts: number;
  venue_names: string[];
}

interface Transaction {
  id: number;
  transaction_code?: string | null;
  kind?: string | null;
  method?: string | null;
  amount_in: number;
  status: string;
  created_at?: string | null;
  booking?: { booking_code?: string | null } | null;
}

const CARD = "bg-white rounded-2xl border border-[#e8edf3] shadow-[0_12px_35px_rgba(29,51,87,0.035)]";
const KIND_LABEL: Record<string, string> = { DEPOSIT: "Tiền cọc / trả trước", BALANCE: "Thu tại sân", REFUND: "Hoàn tiền" };
const METHOD_LABEL: Record<string, string> = { BANK_TRANSFER: "Chuyển khoản", CASH: "Tiền mặt" };
const WEEKDAY_SHORT = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export default function OwnerOverviewDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  const today = formatLocalDate();

  const loadData = useCallback(() => {
    Promise.all([
      fetchApi("/bookings/owner/stats").catch(() => null),
      fetchApi("/payments/transactions").catch(() => []),
      fetchApi("/bookings/owner/list").catch(() => []),
    ])
      .then(([statsData, txnData, bookingData]) => {
        setStats(statsData);
        setTransactions(Array.isArray(txnData) ? txnData : []);
        setBookings(Array.isArray(bookingData) ? bookingData : []);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (lastMessage && ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "BOOKING_STATUS_CHANGED", "SLOT_RELEASED", "BOOKING_RESCHEDULED"].includes(lastMessage.type)) {
      loadData();
    }
  }, [lastMessage, loadData]);

  // Thực thu 7 ngày gần nhất, tính từ sổ giao dịch (khoản thu trừ khoản hoàn), theo giờ máy người xem
  const sevenDays = useMemo(() => {
    const days = Array.from({ length: 7 }, (_, index) => {
      const d = new Date();
      d.setDate(d.getDate() - (6 - index));
      return { key: formatLocalDate(d), label: index === 6 ? "Hôm nay" : WEEKDAY_SHORT[d.getDay()], amount: 0 };
    });
    const byKey = new Map(days.map((day) => [day.key, day]));
    transactions
      .filter((t) => t.status === "SUCCESS" && t.created_at)
      .forEach((t) => {
        const day = byKey.get(formatLocalDate(parseUtcDate(t.created_at)));
        if (day) day.amount += t.kind === "REFUND" ? -t.amount_in : t.amount_in;
      });
    return days;
  }, [transactions]);

  const maxDay = Math.max(1, ...sevenDays.map((d) => Math.abs(d.amount)));

  const todayBookings = useMemo(
    () =>
      bookings
        .filter((b) => !["CANCELLED", "EXPIRED"].includes(b.status) && b.details.some((d) => d.date === today))
        .sort((a, b) => (a.details[0]?.start_time || "").localeCompare(b.details[0]?.start_time || "")),
    [bookings, today],
  );

  const todo = useMemo(
    () => bookings.filter((b) => b.refund_status === "PENDING" || (b.status === "CHECKED_IN" && b.remaining_amount > 0)),
    [bookings],
  );

  const exportCsv = () => {
    const header = ["Mã đơn", "Nguồn", "Ngày", "Sân", "Khung giờ", "Khách", "Số điện thoại", "Trạng thái", "Thanh toán", "Tổng tiền", "Đã trả", "Còn lại"];
    const rows = bookings.flatMap((b) =>
      mergeSlots(b.details).map((slot) => [
        bookingCode(b), b.source === "DESK" ? "Tại quầy" : "Trên web", slot.date, slot.court_name, `${slot.start_time}-${slot.end_time}`,
        b.user_name || "", b.user_phone || "", bookingStatusLabel(b.status), paymentStatusLabel(b.payment_status),
        b.total_price, b.paid_amount, b.remaining_amount,
      ]),
    );
    const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `don-dat-san-${today}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div className="p-10 text-center text-xs text-[#51627c]">Đang tải số liệu...</div>;

  const kpis = [
    { label: "Thực thu (đã trừ hoàn tiền)", value: formatVND(stats?.total_revenue), hint: `Đã thu ${formatVND(stats?.collected_amount)} • đã hoàn ${formatVND(stats?.refunded_amount)}` },
    { label: "Tổng số đơn", value: String(stats?.total_bookings ?? 0), hint: `${stats?.completed_bookings ?? 0} đơn đã hoàn tất` },
    { label: "Đang chờ khách cọc", value: String(stats?.pending_bookings ?? 0), hint: "Tự hết hạn sau 15 phút nếu chưa cọc" },
    { label: "Chờ hoàn tiền", value: String(stats?.pending_refunds ?? 0), hint: "Cần chuyển khoản hoàn cho khách" },
  ];

  return (
    <div className="space-y-6 font-sans">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <div className="text-[10px] font-black text-[#6b7ba1] tracking-[1.6px] uppercase mb-1">Tổng quan</div>
          <h1 className="text-2xl sm:text-[26px] font-black text-[#17253d] tracking-tight m-0">
            {stats?.venue_names?.join(", ") || "Chưa có cụm sân"}
          </h1>
          <p className="text-xs text-[#51627c] mt-1">{stats?.total_courts ?? 0} sân • số tiền lấy từ sổ giao dịch (khoản thực thu, thực hoàn)</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={exportCsv} className="px-3 py-2 bg-[#f1f4fb] hover:bg-[#e4ebf7] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] cursor-pointer">
            Xuất CSV đơn đặt
          </button>
          <Link href="/owner/bookings" className="px-4 py-2 bg-[#476cf3] text-white rounded-xl text-xs font-bold hover:bg-[#3b61e8]">
            Mở lịch đặt →
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className={`${CARD} p-5`}>
            <p className="text-[11px] font-bold text-[#718096]">{kpi.label}</p>
            <p className="text-xl sm:text-2xl font-black text-[#17253d] mt-1">{kpi.value}</p>
            <p className="text-[11px] text-[#9aa7bb] mt-1">{kpi.hint}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className={`${CARD} p-5 lg:col-span-2`}>
          <h2 className="text-sm font-black text-[#17253d] m-0">Thực thu 7 ngày gần nhất</h2>
          <p className="text-[11px] text-[#718096] mt-0.5 mb-4">
            Tổng: {formatVND(sevenDays.reduce((sum, d) => sum + d.amount, 0))}
          </p>
          <div className="flex items-end gap-3 h-44">
            {sevenDays.map((day) => (
              <div key={day.key} className="flex-1 flex flex-col items-center justify-end h-full gap-1.5">
                <span className="text-[10px] font-bold text-[#51627c]">{day.amount !== 0 ? `${Math.round(day.amount / 1000)}k` : ""}</span>
                <div
                  className={`w-full rounded-t-lg ${day.amount < 0 ? "bg-rose-300" : day.label === "Hôm nay" ? "bg-[#476cf3]" : "bg-[#c7d3f6]"}`}
                  style={{ height: `${Math.max(2, (Math.abs(day.amount) / maxDay) * 100)}%` }}
                  title={`${day.key}: ${formatVND(day.amount)}`}
                />
                <span className="text-[10px] font-bold text-[#718096]">{day.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Cần xử lý ({todo.length})</h2>
          {todo.length === 0 ? (
            <p className="text-xs text-[#718096]">Không có việc nào đang chờ.</p>
          ) : (
            <ul className="space-y-2">
              {todo.slice(0, 6).map((b) => (
                <li key={b.id} className="text-xs p-2.5 rounded-xl bg-amber-50 border border-amber-200">
                  <p className="font-bold text-[#17253d]">
                    {bookingCode(b)} • {b.user_name}
                  </p>
                  <p className="text-amber-800">
                    {b.refund_status === "PENDING" ? `Chờ hoàn ${formatVND(b.refund_amount || 0)}` : `Đã nhận sân, còn thu ${formatVND(b.remaining_amount)}`}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <Link href="/owner/bookings" className="inline-block mt-3 text-xs font-bold text-[#476cf3] hover:underline">
            Xử lý trong Lịch đặt →
          </Link>
        </section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Lịch hôm nay ({todayBookings.length})</h2>
          {todayBookings.length === 0 ? (
            <p className="text-xs text-[#718096]">Hôm nay chưa có đơn nào.</p>
          ) : (
            <ul className="divide-y divide-[#f3f5f9]">
              {todayBookings.map((b) => (
                <li key={b.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                  <div className="min-w-0">
                    <p className="font-bold text-[#17253d] truncate">{b.user_name} <span className="font-mono text-[#718096] font-semibold">• {bookingCode(b)}</span></p>
                    <p className="text-[#51627c]">
                      {mergeSlots(b.details.filter((d) => d.date === today)).map((s) => `${s.court_name} ${s.start_time}-${s.end_time}`).join(", ")}
                    </p>
                  </div>
                  <span className={`px-2 py-0.5 rounded-md border font-bold shrink-0 ${bookingStatusTone(b.status)}`}>{bookingStatusLabel(b.status)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Giao dịch gần đây</h2>
          {transactions.length === 0 ? (
            <p className="text-xs text-[#718096]">Chưa có giao dịch nào.</p>
          ) : (
            <ul className="divide-y divide-[#f3f5f9]">
              {transactions.slice(0, 8).map((t) => (
                <li key={t.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                  <div className="min-w-0">
                    <p className="font-bold text-[#17253d]">
                      {KIND_LABEL[t.kind || ""] || t.kind} <span className="text-[#718096] font-semibold">• {METHOD_LABEL[t.method || ""] || t.method}</span>
                    </p>
                    <p className="text-[#718096]">
                      {t.booking?.booking_code || ""} {t.created_at ? `• ${parseUtcDate(t.created_at).toLocaleString("vi-VN")}` : ""}
                    </p>
                  </div>
                  <span className={`font-black shrink-0 ${t.kind === "REFUND" ? "text-rose-600" : "text-emerald-700"}`}>
                    {t.kind === "REFUND" ? "-" : "+"}{formatVND(t.amount_in)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
