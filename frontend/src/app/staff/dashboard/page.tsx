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

const CARD = "bg-white rounded-2xl border border-[#e8edf3] shadow-[0_12px_35px_rgba(29,51,87,0.035)]";
const EMPTY = "py-8 px-4 text-center rounded-xl bg-[#f8fafd] border border-dashed border-[#dde4ef] text-xs text-[#718096]";

/** Một dòng trong danh sách lượt hôm nay: giờ và sân ở bên trái, khách ở giữa, phần bên phải do nơi gọi quyết định. */
function TodayRow({ booking, today, children }: { booking: Booking; today: string; children: React.ReactNode }) {
  return (
    <li className="py-3 flex items-center gap-4 text-xs">
      <div className="w-24 shrink-0 space-y-1.5">
        {mergeSlots(booking.details.filter((d) => d.date === today)).map((slot) => (
          <div key={`${slot.court_id}-${slot.start_time}`}>
            <p className="font-black text-[#17253d] text-[13px] tabular-nums">
              {slot.start_time} - {slot.end_time}
            </p>
            <p className="text-[#718096] font-semibold">{slot.court_name}</p>
          </div>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-bold text-[#17253d] truncate">{booking.user_name || "Khách"}</p>
        <p className="text-[#8a97ab] font-mono">{bookingCode(booking)}</p>
      </div>
      {children}
    </li>
  );
}

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

  if (loading) return <div className="p-10 text-center text-xs text-[#51627c]">Đang tải bảng ca trực...</div>;

  if (statsError || !stats) {
    return (
      <div className={`${CARD} p-8 text-center max-w-lg mx-auto`}>
        <p className="text-sm font-bold text-[#17253d]">Chưa xem được bảng ca trực</p>
        <p className="text-xs text-[#51627c] mt-1">{statsError || "Tài khoản chưa được gán cụm sân."}</p>
      </div>
    );
  }

  const kpis = [
    { label: "Thu trong ngày", value: formatVND(stats.today_revenue), hint: "Mọi khoản thu ghi nhận hôm nay", dot: "bg-[#476cf3]" },
    { label: "Tiền mặt tại quầy", value: formatVND(stats.today_cash_collected), hint: "Cần đối chiếu cuối ca", dot: "bg-emerald-500" },
    { label: "Cọc chuyển khoản", value: formatVND(stats.today_deposit_online), hint: "Khách chuyển qua VietQR", dot: "bg-sky-500" },
    {
      label: "Lượt hôm nay",
      value: `${stats.today_completed_bookings}/${stats.today_total_bookings}`,
      hint: `${stats.today_pending_bookings} lượt chưa đến`,
      dot: "bg-amber-500",
    },
  ];

  return (
    <div className="space-y-6 font-sans">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-[#6b7ba1]">Ca trực • {formatDisplayDate(stats.today_date)}</p>
          <h1 className="text-2xl sm:text-[26px] font-black text-[#17253d] tracking-tight m-0 mt-0.5">{stats.venue_name}</h1>
          <p className="text-xs text-[#51627c] mt-1">
            {stats.venue_address} • {stats.today_courts_count} sân • Nhân viên: {stats.staff_name}
          </p>
        </div>
        <Link
          href="/staff/bookings"
          className="px-4 py-2.5 bg-[#476cf3] text-white rounded-xl text-xs font-bold hover:bg-[#3b61e8] whitespace-nowrap self-start sm:self-auto"
        >
          Mở quầy: lịch đặt & check-in →
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className={`${CARD} p-5`}>
            <p className="flex items-center gap-2 text-[11px] font-bold text-[#718096]">
              <span className={`w-2 h-2 rounded-full ${kpi.dot}`} />
              {kpi.label}
            </p>
            <p className="text-2xl sm:text-[28px] font-black text-[#17253d] mt-2 leading-none">{kpi.value}</p>
            <p className="text-[11px] text-[#8a97ab] mt-2">{kpi.hint}</p>
          </div>
        ))}
      </div>

      {refunds.length > 0 && (
        <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-xs text-amber-900 flex flex-wrap items-center justify-between gap-3">
          <span>
            Có <strong>{refunds.length} yêu cầu hoàn tiền</strong> đang chờ chuyển khoản cho khách.
          </span>
          <Link href="/staff/bookings" className="px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-bold whitespace-nowrap">
            Xử lý →
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Khách sắp đến ({waiting.length})</h2>
          {waiting.length === 0 ? (
            <p className={EMPTY}>Không còn lượt nào đang chờ nhận sân hôm nay.</p>
          ) : (
            <ul className="divide-y divide-[#f1f4f9]">
              {waiting.map((b) => (
                <TodayRow key={b.id} booking={b} today={today}>
                  {b.remaining_amount > 0 ? (
                    <span className="font-bold text-amber-700 shrink-0 whitespace-nowrap">Còn thu {formatVND(b.remaining_amount)}</span>
                  ) : (
                    <span className="font-bold text-emerald-700 shrink-0 whitespace-nowrap">Đã trả đủ</span>
                  )}
                </TodayRow>
              ))}
            </ul>
          )}
        </section>

        <section className={`${CARD} p-5`}>
          <h2 className="text-sm font-black text-[#17253d] m-0 mb-3">Tất cả lượt hôm nay ({todayBookings.length})</h2>
          {todayBookings.length === 0 ? (
            <p className={EMPTY}>Hôm nay chưa có đơn nào.</p>
          ) : (
            <ul className="divide-y divide-[#f1f4f9]">
              {todayBookings.map((b) => (
                <TodayRow key={b.id} booking={b} today={today}>
                  <span className={`px-2 py-0.5 rounded-md border font-bold shrink-0 ${bookingStatusTone(b.status)}`}>{bookingStatusLabel(b.status)}</span>
                </TodayRow>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
