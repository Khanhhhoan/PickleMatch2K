"use client";

import React, { useEffect, useState } from "react";
import { errorMessage, fetchApi, formatVND } from "@/lib/api";
import { WsMessage } from "@/lib/use-websocket";
import RevenueBars, { RevenueBar } from "@/components/RevenueBars";
import RevenueSummary, { REVENUE_BOX, REVENUE_LIVE_EVENTS, RevenueTotals } from "@/components/RevenueSummary";

interface Amounts {
  collected: number;
  refunded: number;
  net: number;
}

/** GET /bookings/revenue/monthly: cả tháng và từng ngày trong tháng (giờ Việt Nam). */
interface MonthlyRevenueData extends RevenueTotals {
  month: string;
  days: (Amounts & { date: string })[];
}

/** GET /bookings/revenue/yearly: cả năm và từng tháng trong năm. */
interface YearlyRevenueData extends RevenueTotals {
  year: number;
  months: (Amounts & { month: string })[];
}

const WEEKDAY = ["Chủ nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];

/** Số tiền gọn trên đầu cột: 850k, 12,5tr. */
function shortVND(amount: number): string {
  if (Math.abs(amount) >= 1_000_000) return `${(amount / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}tr`;
  return `${Math.round(amount / 1000).toLocaleString("vi-VN")}k`;
}

function monthBars(data: MonthlyRevenueData, today: string): RevenueBar[] {
  const lastDay = data.days.length;
  return data.days.map((day) => {
    const dayNumber = Number(day.date.slice(8));
    const weekday = WEEKDAY[new Date(`${day.date}T00:00:00`).getDay()];
    return {
      key: day.date,
      // Đủ để dò ngày mà không chen chúc trên điện thoại
      label: [1, 5, 10, 15, 20, 25, lastDay].includes(dayNumber) ? String(dayNumber) : "",
      title: `${weekday} ${day.date.slice(8)}/${day.date.slice(5, 7)}: ${formatVND(day.net)}`,
      amount: day.net,
      current: day.date === today,
      disabled: day.date > today,
    };
  });
}

function yearBars(data: YearlyRevenueData, today: string): RevenueBar[] {
  const currentMonth = today.slice(0, 7);
  return data.months.map((month) => ({
    key: month.month,
    label: `T${Number(month.month.slice(5))}`,
    title: `Tháng ${Number(month.month.slice(5))}/${month.month.slice(0, 4)}: ${formatVND(month.net)}`,
    amount: month.net,
    current: month.month === currentMonth,
    disabled: month.month > currentMonth,
  }));
}

/**
 * Doanh thu một tháng (cột là từng ngày) hoặc một năm (cột là từng tháng), cùng các khoản thu, hoàn của cả kỳ.
 * Bấm một cột thì gọi onPick với ngày (YYYY-MM-DD) hoặc tháng (YYYY-MM) đó.
 */
export default function PeriodRevenue({
  unit,
  period,
  today,
  onPick,
  lastMessage,
}: {
  unit: "month" | "year";
  period: string; // "2026-11" khi xem tháng, "2026" khi xem năm
  today: string; // YYYY-MM-DD
  onPick: (key: string) => void;
  lastMessage?: WsMessage | null;
}) {
  const key = `${unit}:${period}`;
  const [result, setResult] = useState<{ key: string; data?: MonthlyRevenueData | YearlyRevenueData; error?: string } | null>(null);

  // Có giao dịch mới (thanh toán, đặt sân, hủy, hoàn tiền...): tải lại kỳ đang xem
  const [seenMessage, setSeenMessage] = useState(lastMessage);
  const [version, setVersion] = useState(0);
  if (lastMessage !== seenMessage) {
    setSeenMessage(lastMessage);
    if (lastMessage && REVENUE_LIVE_EVENTS.includes(lastMessage.type)) setVersion((v) => v + 1);
  }

  useEffect(() => {
    let cancelled = false;
    const url = unit === "month" ? `/bookings/revenue/monthly?month=${period}` : `/bookings/revenue/yearly?year=${period}`;
    fetchApi(url)
      .then((data: MonthlyRevenueData | YearlyRevenueData) => {
        if (!cancelled) setResult({ key, data });
      })
      .catch((err) => {
        const fallback = unit === "month" ? "Không tải được doanh thu của tháng này." : "Không tải được doanh thu của năm này.";
        if (!cancelled) setResult({ key, error: errorMessage(err, fallback) });
      });
    return () => {
      cancelled = true;
    };
  }, [key, unit, period, version]);

  if (!result || result.key !== key) {
    return <div className={`${REVENUE_BOX} animate-pulse h-48`} />;
  }
  if (!result.data) {
    return <p className={`${REVENUE_BOX} text-xs text-rose-600 text-center`}>{result.error}</p>;
  }

  const data = result.data;
  const byDay = "days" in data;
  const bars = byDay ? monthBars(data, today) : yearBars(data, today);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[11px] font-bold text-[#718096]">{byDay ? "Thực thu từng ngày" : "Thực thu từng tháng"}</p>
        <RevenueBars
          bars={bars}
          onPick={onPick}
          empty={byDay ? "Chưa có khoản thu nào trong tháng này." : "Chưa có khoản thu nào trong năm này."}
          valueLabel={byDay ? undefined : shortVND}
          valuesFromSm
        />
        <p className="text-[11px] text-[#8a97ab] mt-2">
          {byDay ? "Bấm vào một cột để xem chi tiết ngày đó." : "Bấm vào một cột để xem tháng đó."}
        </p>
      </div>

      <div className="pt-4 border-t border-[#f1f4f9] space-y-4">
        <RevenueSummary data={data} collectedLabel={byDay ? "Thu trong tháng" : "Thu trong năm"} cashHint="Thu tại quầy" />
      </div>
    </div>
  );
}
