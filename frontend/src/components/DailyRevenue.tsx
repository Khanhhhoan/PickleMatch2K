"use client";

import React, { useEffect, useState } from "react";
import { errorMessage, fetchApi, formatVND, parseUtcDate } from "@/lib/api";
import { WsMessage } from "@/lib/use-websocket";
import RevenueSummary, { REVENUE_BOX as BOX, REVENUE_LIVE_EVENTS as LIVE_EVENTS, RevenueTotals } from "@/components/RevenueSummary";

/** Doanh thu một ngày (giờ Việt Nam) do máy chủ tổng hợp từ sổ giao dịch (GET /bookings/revenue/daily). */
interface DailyRevenueData extends RevenueTotals {
  date: string;
  transactions: {
    id: number;
    transaction_code?: string | null;
    kind?: string | null;
    method?: string | null;
    amount_in: number;
    created_at?: string | null;
    booking?: { booking_code?: string | null } | null;
  }[];
}

const KIND_LABEL: Record<string, string> = { DEPOSIT: "Tiền cọc", BALANCE: "Thu tại sân", REFUND: "Hoàn tiền" };
const METHOD_LABEL: Record<string, string> = { BANK_TRANSFER: "Chuyển khoản", CASH: "Tiền mặt" };

/** Số liệu của một ngày: các khoản thu theo hình thức, tiền hoàn, thực thu, số lượt chơi và từng giao dịch. */
export default function DailyRevenue({ day, lastMessage }: { day: string; lastMessage?: WsMessage | null }) {
  const [result, setResult] = useState<{ day: string; data?: DailyRevenueData; error?: string } | null>(null);

  // Có giao dịch mới (thanh toán, đặt sân, hủy, hoàn tiền...): tải lại ngày đang xem
  const [seenMessage, setSeenMessage] = useState(lastMessage);
  const [version, setVersion] = useState(0);
  if (lastMessage !== seenMessage) {
    setSeenMessage(lastMessage);
    if (lastMessage && LIVE_EVENTS.includes(lastMessage.type)) setVersion((v) => v + 1);
  }

  useEffect(() => {
    let cancelled = false;
    fetchApi(`/bookings/revenue/daily?date=${day}`)
      .then((data: DailyRevenueData) => {
        if (!cancelled) setResult({ day, data });
      })
      .catch((err) => {
        if (!cancelled) setResult({ day, error: errorMessage(err, "Không tải được doanh thu của ngày này.") });
      });
    return () => {
      cancelled = true;
    };
  }, [day, version]);

  if (!result || result.day !== day) {
    return <div className={`${BOX} animate-pulse h-28`} />;
  }
  if (!result.data) {
    return <p className={`${BOX} text-xs text-rose-600 text-center`}>{result.error}</p>;
  }

  const data = result.data;

  return (
    <div className="space-y-4">
      <RevenueSummary data={data} collectedLabel="Thu trong ngày" cashHint="Cần khớp với tiền trong két" />

      <div>
        <h3 className="text-xs font-black text-[#17253d] m-0 mb-2">Giao dịch trong ngày ({data.transactions.length})</h3>
        {data.transactions.length === 0 ? (
          <p className="py-6 text-center text-xs text-[#8a97ab] rounded-xl border border-dashed border-[#dde4ef]">
            Chưa có giao dịch nào trong ngày này.
          </p>
        ) : (
          <ul className="divide-y divide-[#f1f4f9] max-h-80 overflow-y-auto">
            {data.transactions.map((t) => (
              <li key={t.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                <div className="min-w-0">
                  <p className="font-bold text-[#17253d]">
                    {KIND_LABEL[t.kind || ""] || t.kind}{" "}
                    <span className="text-[#718096] font-semibold">• {METHOD_LABEL[t.method || ""] || t.method}</span>
                  </p>
                  <p className="text-[#8a97ab]">
                    {t.created_at ? parseUtcDate(t.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : ""}
                    {t.booking?.booking_code ? <span className="font-mono"> • {t.booking.booking_code}</span> : null}
                  </p>
                </div>
                <span className={`font-black shrink-0 tabular-nums ${t.kind === "REFUND" ? "text-rose-600" : "text-emerald-700"}`}>
                  {t.kind === "REFUND" ? "-" : "+"}
                  {formatVND(t.amount_in)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
