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
const KIND_LABEL: Record<string, string> = { DEPOSIT: "Tiền cọc", BALANCE: "Thu tại sân", REFUND: "Hoàn tiền" };
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

  // Tiền thu từng ngày trong 7 ngày gần nhất (khoản thu trừ khoản hoàn), theo giờ máy người xem
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
  const weekTotal = sevenDays.reduce((sum, d) => sum + d.amount, 0);
  const todayRevenue = sevenDays[6].amount;
  const hasWeekData = sevenDays.some((d) => d.amount !== 0);

  const todayBookings = useMemo(
    () => bookings.filter((b) => !["CANCELLED", "EXPIRED"].includes(b.status) && b.details.some((d) => d.date === today)),
    [bookings, today],
  );

  // Lịch hôm nay theo từng lượt chơi, sắp theo giờ bắt đầu
  const todaySchedule = useMemo(
    () =>
      todayBookings
        .flatMap((b) => mergeSlots(b.details.filter((d) => d.date === today)).map((slot) => ({ booking: b, slot })))
        .sort((a, b) => a.slot.start_time.localeCompare(b.slot.start_time)),
    [todayBookings, today],
  );

  const arrivedToday = todayBookings.filter((b) => ["CHECKED_IN", "COMPLETED"].includes(b.status)).length;

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

  const pendingDeposits = stats?.pending_bookings ?? 0;
  const pendingRefunds = stats?.pending_refunds ?? 0;
  const kpis = [
    { label: "Thu hôm nay", value: formatVND(todayRevenue), hint: `7 ngày qua: ${formatVND(weekTotal)}`, dot: "bg-[#476cf3]", alert: false },
    { label: "Lịch hôm nay", value: `${todayBookings.length} đơn`, hint: `${arrivedToday} khách đã nhận sân`, dot: "bg-emerald-500", alert: false },
    { label: "Chờ khách cọc", value: String(pendingDeposits), hint: "Mỗi đơn được giữ chỗ 15 phút", dot: "bg-amber-500", alert: pendingDeposits > 0 },
    {
      label: "Chờ hoàn tiền",
      value: String(pendingRefunds),
      hint: pendingRefunds > 0 ? "Chuyển khoản rồi xác nhận trong Lịch đặt" : "Không có yêu cầu nào",
      dot: "bg-rose-500",
      alert: pendingRefunds > 0,
    },
  ];
  const todayLabel = new Date().toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });

  return (
    <div className="space-y-6 font-sans">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-[#6b7ba1] first-letter:uppercase">{todayLabel}</p>
          <h1 className="text-2xl sm:text-[26px] font-black text-[#17253d] tracking-tight m-0 mt-0.5">
            {stats?.venue_names?.join(", ") || "Chưa có cụm sân"}
          </h1>
          <p className="text-xs text-[#51627c] mt-1">
            {stats?.total_courts ?? 0} sân • {stats?.total_bookings ?? 0} đơn đã nhận • {stats?.completed_bookings ?? 0} đơn hoàn tất
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            type="button"
            onClick={exportCsv}
            className="px-3.5 py-2.5 bg-white hover:bg-[#f1f4fb] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] whitespace-nowrap cursor-pointer"
          >
            Xuất danh sách đơn
          </button>
          <Link href="/owner/bookings" className="px-4 py-2.5 bg-[#476cf3] text-white rounded-xl text-xs font-bold hover:bg-[#3b61e8] whitespace-nowrap">
            + Tạo đơn tại quầy
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className={`${CARD} p-5 ${kpi.alert ? "ring-1 ring-amber-300/70" : ""}`}>
            <p className="flex items-center gap-2 text-[11px] font-bold text-[#718096]">
              <span className={`w-2 h-2 rounded-full ${kpi.dot}`} />
              {kpi.label}
            </p>
            <p className="text-2xl sm:text-[28px] font-black text-[#17253d] mt-2 leading-none">{kpi.value}</p>
            <p className="text-[11px] text-[#8a97ab] mt-2">{kpi.hint}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className={`${CARD} p-5 lg:col-span-2`}>
          <div className="flex items-center justify-between gap-3 mb-3">
            <h2 className="text-sm font-black text-[#17253d] m-0">Lịch hôm nay</h2>
            <Link href="/owner/bookings" className="text-xs font-bold text-[#476cf3] hover:underline whitespace-nowrap">
              Mở lịch đặt →
            </Link>
          </div>
          {todaySchedule.length === 0 ? (
            <div className="py-10 text-center rounded-xl bg-[#f8fafd] border border-dashed border-[#dde4ef]">
              <p className="text-sm font-bold text-[#3d4e68]">Hôm nay chưa có lượt đặt nào</p>
              <p className="text-xs text-[#8a97ab] mt-1">Khách đặt trên web hoặc bạn tạo đơn tại quầy sẽ hiện ở đây.</p>
            </div>
          ) : (
            <ul className="divide-y divide-[#f1f4f9]">
              {todaySchedule.map(({ booking: b, slot }) => (
                <li key={`${b.id}-${slot.court_name}-${slot.start_time}`} className="py-3 flex items-center gap-4 text-xs">
                  <div className="w-24 shrink-0">
                    <p className="font-black text-[#17253d] text-[13px] tabular-nums">
                      {slot.start_time} - {slot.end_time}
                    </p>
                    <p className="text-[#718096] font-semibold">{slot.court_name}</p>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-[#17253d] truncate">{b.user_name || "Khách"}</p>
                    <p className="text-[#8a97ab]">
                      <span className="font-mono">{bookingCode(b)}</span>
                      {b.remaining_amount > 0 && !["CANCELLED", "EXPIRED"].includes(b.status) ? ` • còn thu ${formatVND(b.remaining_amount)}` : ""}
                    </p>
                  </div>
                  <span className={`px-2 py-0.5 rounded-md border font-bold shrink-0 ${bookingStatusTone(b.status)}`}>{bookingStatusLabel(b.status)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Việc cần làm{todo.length > 0 ? ` (${todo.length})` : ""}</h2>
          {todo.length === 0 ? (
            <div className="py-8 text-center rounded-xl bg-emerald-50/60 border border-emerald-100">
              <p className="text-sm font-bold text-emerald-800">Mọi việc đã xong</p>
              <p className="text-xs text-emerald-700/80 mt-1">Không có khoản nào cần thu hay cần hoàn.</p>
            </div>
          ) : (
            <>
              <ul className="space-y-2">
                {todo.slice(0, 6).map((b) => (
                  <li key={b.id} className="text-xs p-3 rounded-xl bg-amber-50 border border-amber-200">
                    <p className="font-bold text-[#17253d]">
                      {b.user_name} <span className="font-mono font-semibold text-[#718096]">• {bookingCode(b)}</span>
                    </p>
                    <p className="text-amber-800 mt-0.5">
                      {b.refund_status === "PENDING" ? `Hoàn ${formatVND(b.refund_amount || 0)} cho khách` : `Khách đã nhận sân, còn thu ${formatVND(b.remaining_amount)}`}
                    </p>
                  </li>
                ))}
              </ul>
              <Link href="/owner/bookings" className="inline-block mt-3 text-xs font-bold text-[#476cf3] hover:underline">
                Xử lý trong Lịch đặt →
              </Link>
            </>
          )}
        </section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className={`${CARD} p-5 lg:col-span-2`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-black text-[#17253d] m-0">Doanh thu 7 ngày</h2>
              <p className="text-xl font-black text-[#17253d] mt-1">{formatVND(weekTotal)}</p>
            </div>
            <div className="text-right">
              <p className="text-[11px] font-bold text-[#718096]">Tổng thực thu</p>
              <p className="text-sm font-black text-[#17253d]">{formatVND(stats?.total_revenue)}</p>
            </div>
          </div>
          <div className="relative mt-4">
            <div className="flex items-end gap-3 h-40 border-b border-[#e8edf3]">
              {sevenDays.map((day) => (
                <div key={day.key} className="flex-1 flex flex-col items-center justify-end h-full gap-1.5">
                  <span className="text-[10px] font-bold text-[#51627c]">{day.amount !== 0 ? `${Math.round(day.amount / 1000).toLocaleString("vi-VN")}k` : ""}</span>
                  <div
                    className={`w-full max-w-14 rounded-t-lg ${day.amount < 0 ? "bg-rose-300" : day.label === "Hôm nay" ? "bg-[#476cf3]" : "bg-[#c7d3f6]"}`}
                    style={{ height: day.amount === 0 ? "3px" : `${Math.max(6, (Math.abs(day.amount) / maxDay) * 100)}%` }}
                    title={`${day.key}: ${formatVND(day.amount)}`}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-1.5">
              {sevenDays.map((day) => (
                <span key={day.key} className={`flex-1 text-center text-[10px] font-bold ${day.label === "Hôm nay" ? "text-[#476cf3]" : "text-[#718096]"}`}>
                  {day.label}
                </span>
              ))}
            </div>
            {!hasWeekData && (
              <p className="absolute inset-x-0 top-14 text-center text-xs text-[#8a97ab]">Chưa có khoản thu nào trong 7 ngày qua.</p>
            )}
          </div>
        </section>

        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Giao dịch gần đây</h2>
          {transactions.length === 0 ? (
            <p className="text-xs text-[#8a97ab] py-6 text-center">Chưa có giao dịch nào.</p>
          ) : (
            <ul className="divide-y divide-[#f1f4f9]">
              {transactions.slice(0, 6).map((t) => (
                <li key={t.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                  <div className="min-w-0">
                    <p className="font-bold text-[#17253d]">
                      {KIND_LABEL[t.kind || ""] || t.kind} <span className="text-[#718096] font-semibold">• {METHOD_LABEL[t.method || ""] || t.method}</span>
                    </p>
                    <p className="text-[#8a97ab]">
                      <span className="font-mono">{t.booking?.booking_code || ""}</span>
                      {t.created_at ? ` • ${parseUtcDate(t.created_at).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}` : ""}
                    </p>
                  </div>
                  <span className={`font-black shrink-0 ${t.kind === "REFUND" ? "text-rose-600" : "text-emerald-700"}`}>
                    {t.kind === "REFUND" ? "-" : "+"}
                    {formatVND(t.amount_in)}
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
