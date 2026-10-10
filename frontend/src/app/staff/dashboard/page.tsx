"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchApi, formatLocalDate, formatVND } from "@/lib/api";
import { Booking, bookingCode, bookingStatusLabel, bookingStatusTone, formatDisplayDate, mergeSlots } from "@/lib/booking";
import { useWebSocket } from "@/lib/use-websocket";

interface ShiftStats {
  venue_id: number;
  venue_name: string;
  venue_address: string;
  staff_name: string;
  today_date: string;
  today_revenue: number;
  today_deposit_online: number;
  today_cash_collected: number;
  today_total_bookings: number;
  today_completed_bookings: number;
  today_pending_bookings: number;
  today_courts_count: number;
}

const CARD = "bg-white rounded-2xl border border-zinc-200 shadow-xs";

/** Bảng ca trực: số liệu trong ngày của cụm sân được phân công, lấy từ sổ giao dịch trên máy chủ. */
export default function StaffDashboardPage() {
  const [stats, setStats] = useState<ShiftStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const { lastMessage } = useWebSocket("/api/v1/ws/live");
  const today = formatLocalDate();

  const loadData = useCallback(() => {
    Promise.all([
      fetchApi("/bookings/staff/stats").then(
        (data) => {
          setStats(data);
          setStatsError(null);
        },
        (err) => setStatsError(err instanceof Error ? err.message : "Không tải được số liệu ca trực."),
      ),
      fetchApi("/bookings/owner/list").then((data) => setBookings(Array.isArray(data) ? data : []), () => setBookings([])),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (lastMessage && ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "BOOKING_STATUS_CHANGED", "SLOT_RELEASED", "BOOKING_RESCHEDULED"].includes(lastMessage.type)) {
      loadData();
    }
  }, [lastMessage, loadData]);

  const todayBookings = useMemo(
    () =>
      bookings
        .filter((b) => !["CANCELLED", "EXPIRED"].includes(b.status) && b.details.some((d) => d.date === today))
        .sort((a, b) => (a.details[0]?.start_time || "").localeCompare(b.details[0]?.start_time || "")),
    [bookings, today],
  );
  const waiting = todayBookings.filter((b) => b.status === "CONFIRMED");
  const refunds = bookings.filter((b) => b.refund_status === "PENDING");

  if (loading) return <div className="p-10 text-center text-xs text-zinc-500">Đang tải bảng ca trực...</div>;

  if (statsError || !stats) {
    return (
      <div className={`${CARD} p-8 text-center max-w-lg mx-auto`}>
        <p className="text-sm font-bold text-zinc-900">Chưa xem được bảng ca trực</p>
        <p className="text-xs text-zinc-600 mt-1">{statsError || "Tài khoản chưa được gán cụm sân."}</p>
      </div>
    );
  }

  const kpis = [
    { label: "Thu trong ngày", value: formatVND(stats.today_revenue), hint: "Mọi khoản thu ghi nhận hôm nay" },
    { label: "Tiền mặt tại quầy", value: formatVND(stats.today_cash_collected), hint: "Cần đối chiếu cuối ca" },
    { label: "Cọc chuyển khoản", value: formatVND(stats.today_deposit_online), hint: "Khách chuyển qua VietQR" },
    { label: "Lượt hôm nay", value: `${stats.today_completed_bookings}/${stats.today_total_bookings}`, hint: `${stats.today_pending_bookings} lượt chưa đến` },
  ];

  return (
    <div className="space-y-6 font-sans">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">Ca trực • {formatDisplayDate(stats.today_date)}</p>
          <h1 className="text-2xl font-black text-zinc-950 tracking-tight">{stats.venue_name}</h1>
          <p className="text-xs text-zinc-500 mt-0.5">{stats.venue_address} • {stats.today_courts_count} sân • Nhân viên: {stats.staff_name}</p>
        </div>
        <Link href="/staff/bookings" className="px-4 py-2.5 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs font-bold self-start sm:self-auto">
          Mở quầy: lịch đặt & check-in →
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className={`${CARD} p-5`}>
            <p className="text-[11px] font-bold text-zinc-500">{kpi.label}</p>
            <p className="text-xl sm:text-2xl font-black text-zinc-950 mt-1">{kpi.value}</p>
            <p className="text-[11px] text-zinc-400 mt-1">{kpi.hint}</p>
          </div>
        ))}
      </div>

      {refunds.length > 0 && (
        <div className="p-4 rounded-2xl bg-amber-50 border border-amber-300 text-xs text-amber-950 flex flex-wrap items-center justify-between gap-3">
          <span>
            Có <strong>{refunds.length} yêu cầu hoàn tiền</strong> đang chờ chuyển khoản cho khách.
          </span>
          <Link href="/staff/bookings" className="px-3.5 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold">Xử lý →</Link>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-zinc-950 mb-3">Khách sắp đến ({waiting.length})</h2>
          {waiting.length === 0 ? (
            <p className="text-xs text-zinc-500">Không còn lượt nào đang chờ nhận sân hôm nay.</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {waiting.map((b) => (
                <li key={b.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                  <div className="min-w-0">
                    <p className="font-bold text-zinc-950 truncate">{b.user_name} <span className="font-mono text-zinc-500 font-semibold">• {bookingCode(b)}</span></p>
                    <p className="text-zinc-600">
                      {mergeSlots(b.details.filter((d) => d.date === today)).map((s) => `${s.court_name} ${s.start_time}-${s.end_time}`).join(", ")}
                    </p>
                  </div>
                  <span className="font-bold text-amber-700 shrink-0">Còn thu {formatVND(b.remaining_amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-zinc-950 mb-3">Tất cả lượt hôm nay ({todayBookings.length})</h2>
          {todayBookings.length === 0 ? (
            <p className="text-xs text-zinc-500">Hôm nay chưa có đơn nào.</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {todayBookings.map((b) => (
                <li key={b.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                  <div className="min-w-0">
                    <p className="font-bold text-zinc-950 truncate">{b.user_name}</p>
                    <p className="text-zinc-600">
                      {mergeSlots(b.details.filter((d) => d.date === today)).map((s) => `${s.court_name} ${s.start_time}-${s.end_time}`).join(", ")}
                    </p>
                  </div>
                  <span className={`px-2 py-0.5 rounded-md border font-bold shrink-0 ${bookingStatusTone(b.status)}`}>{bookingStatusLabel(b.status)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
