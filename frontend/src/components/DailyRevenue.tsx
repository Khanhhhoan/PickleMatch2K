"use client";

import React, { useEffect, useState } from "react";
import { errorMessage, fetchApi, formatVND, parseUtcDate } from "@/lib/api";
import { WsMessage } from "@/lib/use-websocket";

/** Doanh thu một ngày (giờ Việt Nam) do máy chủ tổng hợp từ sổ giao dịch (GET /bookings/revenue/daily). */
interface DailyRevenueData {
  date: string;
  collected: number;
  cash: number;
  transfer: number;
  refunded: number;
  net: number;
  plays_total: number;
  plays_arrived: number;
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
// Sự kiện trực tiếp làm số liệu trong ngày thay đổi
const LIVE_EVENTS = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "BOOKING_STATUS_CHANGED", "SLOT_RELEASED", "BOOKING_RESCHEDULED"];
const BOX = "rounded-xl bg-[#f8fafd] border border-[#e8edf3] p-4";

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
  const tiles = [
    { label: "Thu trong ngày", value: formatVND(data.collected), hint: "Tiền cọc và tiền thu tại sân", dot: "bg-[#476cf3]" },
    { label: "Tiền mặt", value: formatVND(data.cash), hint: "Cần khớp với tiền trong két", dot: "bg-emerald-500" },
    { label: "Chuyển khoản", value: formatVND(data.transfer), hint: "Cọc qua VietQR và chuyển khoản tại quầy", dot: "bg-sky-500" },
    { label: "Hoàn tiền", value: data.refunded > 0 ? `-${formatVND(data.refunded)}` : formatVND(0), hint: "Đã chuyển trả cho khách", dot: "bg-rose-500" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((tile) => (
          <div key={tile.label} className={BOX}>
            <p className="flex items-center gap-2 text-[11px] font-bold text-[#718096]">
              <span className={`w-2 h-2 rounded-full ${tile.dot}`} />
              {tile.label}
            </p>
            <p className="text-lg sm:text-xl font-black text-[#17253d] mt-1.5 leading-none tabular-nums">{tile.value}</p>
            <p className="text-[11px] text-[#8a97ab] mt-1.5">{tile.hint}</p>
          </div>
        ))}
      </div>

      <p className="text-xs text-[#51627c]">
        Thực thu <strong className="text-[#17253d] font-black">{formatVND(data.net)}</strong> • {data.plays_total} lượt chơi,{" "}
        {data.plays_arrived} lượt khách đã nhận sân
      </p>

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
