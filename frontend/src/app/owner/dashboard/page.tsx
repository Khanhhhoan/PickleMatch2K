"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchApi, formatLocalDate, formatVND } from "@/lib/api";
import { Booking, bookingCode, bookingStatusLabel, bookingStatusTone, mergeSlots, paymentStatusLabel } from "@/lib/booking";
import { useWebSocket } from "@/lib/use-websocket";
import DailyRevenue from "@/components/DailyRevenue";
import PeriodRevenue from "@/components/PeriodRevenue";
import RevenueBars from "@/components/RevenueBars";
import ShiftClosingDialog from "@/components/ShiftClosingDialog";

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
  daily: { date: string; revenue: number; bookings: number }[]; // thực thu theo ngày (giờ Việt Nam), chỉ ngày có phát sinh
}

const CARD = "bg-white rounded-2xl border border-[#e8edf3] shadow-[0_12px_35px_rgba(29,51,87,0.035)]";
const WEEKDAY_SHORT = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const DAY_BUTTON =
  "h-9 min-w-9 px-2.5 bg-white hover:bg-[#f1f4fb] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] whitespace-nowrap cursor-pointer disabled:opacity-40 disabled:cursor-default";
const SELECT =
  "h-9 pl-2.5 pr-1.5 bg-white border border-[#d5dfed] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3] cursor-pointer";

type RevenueView = "day" | "month" | "year";
const REVENUE_VIEWS: { key: RevenueView; label: string; word: string }[] = [
  { key: "day", label: "Theo ngày", word: "ngày" },
  { key: "month", label: "Theo tháng", word: "tháng" },
  { key: "year", label: "Theo năm", word: "năm" },
];

/** Ngày cách `day` (YYYY-MM-DD) một số ngày. */
function shiftDay(day: string, offset: number): string {
  const [year, month, date] = day.split("-").map(Number);
  return formatLocalDate(new Date(year, month - 1, date + offset));
}

/** Tháng (YYYY-MM) cách `month` một số tháng. */
function shiftMonth(month: string, offset: number): string {
  const [year, value] = month.split("-").map(Number);
  const moved = new Date(year, value - 1 + offset, 1);
  return `${moved.getFullYear()}-${String(moved.getMonth() + 1).padStart(2, "0")}`;
}

export default function OwnerOverviewDashboard() {
  const today = formatLocalDate();
  const [stats, setStats] = useState<Stats | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [closingShift, setClosingShift] = useState(false);
  // Lấy từ một lần gọi riêng: gọi phương thức trên `today` giữa các hook khiến React Compiler coi `today` có thể bị
  // sửa và không còn xem các hàm setState phía trên là cố định
  const thisMonth = formatLocalDate().slice(0, 7);
  const thisYear = Number(thisMonth.slice(0, 4));
  const [view, setView] = useState<RevenueView>("day"); // xem doanh thu theo ngày, tháng hay năm
  const [day, setDay] = useState(today); // ngày đang xem doanh thu
  const [month, setMonth] = useState(thisMonth); // tháng đang xem (YYYY-MM)
  const [year, setYear] = useState(thisYear); // năm đang xem
  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  const loadData = useCallback(() => {
    Promise.all([
      fetchApi("/bookings/owner/stats").catch(() => null),
      fetchApi("/bookings/owner/list").catch(() => []),
    ])
      .then(([statsData, bookingData]) => {
        setStats(statsData);
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

  // Thực thu (khoản thu trừ khoản hoàn) từng ngày trong 7 ngày gần nhất, do máy chủ tính theo giờ Việt Nam
  const sevenDays = useMemo(() => {
    const revenue = new Map((stats?.daily || []).map((d) => [d.date, d.revenue]));
    return Array.from({ length: 7 }, (_, index) => {
      const d = new Date();
      d.setDate(d.getDate() - (6 - index));
      const key = formatLocalDate(d);
      return { key, label: index === 6 ? "Hôm nay" : WEEKDAY_SHORT[d.getDay()], amount: revenue.get(key) ?? 0 };
    });
  }, [stats]);

  const weekTotal = sevenDays.reduce((sum, d) => sum + d.amount, 0);
  const todayRevenue = sevenDays[6].amount;

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
  const dayLabel =
    day === today
      ? `Hôm nay, ${todayLabel}`
      : new Date(`${day}T00:00:00`).toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
  const periodLabel =
    view === "day" ? dayLabel : view === "month" ? `Tháng ${Number(month.slice(5))}/${month.slice(0, 4)}` : `Năm ${year}`;

  // Năm đầu tiên có phát sinh (đơn hoặc khoản thu): bộ chọn tháng/năm không lùi quá năm này
  // (trừ khi đang xem một kỳ cũ hơn, chẳng hạn chuyển từ một ngày cũ sang xem tháng của ngày đó)
  const firstYear = Math.min(thisYear, Number(stats?.daily?.[0]?.date.slice(0, 4)) || thisYear, Number(month.slice(0, 4)), year);
  const years = Array.from({ length: thisYear - firstYear + 1 }, (_, index) => thisYear - index);
  const chooseMonth = (value: string) => setMonth(value > thisMonth ? thisMonth : value);

  // Đổi kiểu xem: từ ngày sang tháng/năm, hay từ tháng sang năm, thì xem đúng tháng/năm chứa kỳ đang xem
  const openView = (next: RevenueView) => {
    if (next === "month" && view === "day") setMonth(day.slice(0, 7));
    if (next === "year" && view !== "year") setYear(Number((view === "day" ? day : month).slice(0, 4)));
    setView(next);
  };
  // Bấm một cột: ngày trong biểu đồ tháng mở chi tiết ngày đó, tháng trong biểu đồ năm mở tháng đó
  const openDay = (key: string) => {
    setDay(key);
    setView("day");
  };
  const openMonth = (key: string) => {
    setMonth(key);
    setView("month");
  };

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
          <button
            type="button"
            onClick={() => setClosingShift(true)}
            className="px-3.5 py-2.5 bg-white hover:bg-[#f1f4fb] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] whitespace-nowrap cursor-pointer"
          >
            Kết ca
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

      <section className={`${CARD} p-5 space-y-5`}>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-black text-[#17253d] m-0">
              Doanh thu theo {REVENUE_VIEWS.find((option) => option.key === view)?.word}
            </h2>
            <p className="text-xs text-[#51627c] mt-1 first-letter:uppercase">{periodLabel}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 lg:justify-end">
            <div className="inline-flex p-1 rounded-xl bg-[#f1f4fb] border border-[#e3e9f3]">
              {REVENUE_VIEWS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => openView(option.key)}
                  aria-pressed={view === option.key}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap cursor-pointer transition ${
                    view === option.key ? "bg-white text-[#17253d] shadow-sm" : "text-[#51627c] hover:text-[#17253d]"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>

            {view === "day" && (
              <div className="flex flex-wrap items-center gap-1.5">
                <button type="button" className={DAY_BUTTON} onClick={() => setDay(shiftDay(day, -1))} aria-label="Ngày trước" title="Ngày trước">
                  ‹
                </button>
                <input
                  type="date"
                  value={day}
                  max={today}
                  onChange={(e) => e.target.value && setDay(e.target.value > today ? today : e.target.value)}
                  aria-label="Chọn ngày xem doanh thu"
                  className="h-9 px-2.5 bg-white border border-[#d5dfed] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3]"
                />
                <button type="button" className={DAY_BUTTON} onClick={() => setDay(shiftDay(day, 1))} disabled={day >= today} aria-label="Ngày sau" title="Ngày sau">
                  ›
                </button>
                <button type="button" className={DAY_BUTTON} onClick={() => setDay(today)} disabled={day === today}>
                  Hôm nay
                </button>
              </div>
            )}

            {view === "month" && (
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  className={DAY_BUTTON}
                  onClick={() => setMonth(shiftMonth(month, -1))}
                  disabled={month <= `${firstYear}-01`}
                  aria-label="Tháng trước"
                  title="Tháng trước"
                >
                  ‹
                </button>
                <select
                  className={SELECT}
                  value={Number(month.slice(5))}
                  onChange={(e) => chooseMonth(`${month.slice(0, 4)}-${e.target.value.padStart(2, "0")}`)}
                  aria-label="Chọn tháng xem doanh thu"
                >
                  {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => (
                    <option key={value} value={value} disabled={`${month.slice(0, 4)}-${String(value).padStart(2, "0")}` > thisMonth}>
                      Tháng {value}
                    </option>
                  ))}
                </select>
                <select
                  className={SELECT}
                  value={month.slice(0, 4)}
                  onChange={(e) => chooseMonth(`${e.target.value}-${month.slice(5)}`)}
                  aria-label="Chọn năm của tháng"
                >
                  {years.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className={DAY_BUTTON}
                  onClick={() => setMonth(shiftMonth(month, 1))}
                  disabled={month >= thisMonth}
                  aria-label="Tháng sau"
                  title="Tháng sau"
                >
                  ›
                </button>
                <button type="button" className={DAY_BUTTON} onClick={() => setMonth(thisMonth)} disabled={month === thisMonth}>
                  Tháng này
                </button>
              </div>
            )}

            {view === "year" && (
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  className={DAY_BUTTON}
                  onClick={() => setYear(year - 1)}
                  disabled={year <= firstYear}
                  aria-label="Năm trước"
                  title="Năm trước"
                >
                  ‹
                </button>
                <select className={SELECT} value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Chọn năm xem doanh thu">
                  {years.map((value) => (
                    <option key={value} value={value}>
                      Năm {value}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className={DAY_BUTTON}
                  onClick={() => setYear(year + 1)}
                  disabled={year >= thisYear}
                  aria-label="Năm sau"
                  title="Năm sau"
                >
                  ›
                </button>
                <button type="button" className={DAY_BUTTON} onClick={() => setYear(thisYear)} disabled={year === thisYear}>
                  Năm nay
                </button>
              </div>
            )}
          </div>
        </div>

        {view === "day" && (
          <>
            <div>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-bold text-[#718096]">7 ngày gần nhất</p>
                  <p className="text-sm font-black text-[#17253d]">{formatVND(weekTotal)}</p>
                </div>
                <div className="text-right">
                  <p className="text-[11px] font-bold text-[#718096]">Tổng thực thu</p>
                  <p className="text-sm font-black text-[#17253d]">{formatVND(stats?.total_revenue)}</p>
                </div>
              </div>
              <RevenueBars
                bars={sevenDays.map((d) => ({
                  key: d.key,
                  label: d.label,
                  title: `${d.key}: ${formatVND(d.amount)}`,
                  amount: d.amount,
                  selected: d.key === day,
                }))}
                onPick={setDay}
                empty="Chưa có khoản thu nào trong 7 ngày qua."
                valueLabel={(amount) => `${Math.round(amount / 1000).toLocaleString("vi-VN")}k`}
              />
              <p className="text-[11px] text-[#8a97ab] mt-2">Bấm vào một cột để xem chi tiết ngày đó.</p>
            </div>

            <div className="pt-4 border-t border-[#f1f4f9]">
              <DailyRevenue day={day} lastMessage={lastMessage} />
            </div>
          </>
        )}

        {view === "month" && <PeriodRevenue unit="month" period={month} today={today} onPick={openDay} lastMessage={lastMessage} />}
        {view === "year" && <PeriodRevenue unit="year" period={String(year)} today={today} onPick={openMonth} lastMessage={lastMessage} />}
      </section>

      {closingShift && <ShiftClosingDialog onClose={() => setClosingShift(false)} />}
    </div>
  );
}
