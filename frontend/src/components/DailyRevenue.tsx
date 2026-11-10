"use client";

import React, { useEffect, useState } from "react";
import { errorMessage, fetchApi } from "@/lib/api";
import { WsMessage } from "@/lib/use-websocket";
import LedgerList, { LedgerTransaction } from "@/components/LedgerList";
import RevenueSummary, { REVENUE_BOX as BOX, REVENUE_LIVE_EVENTS as LIVE_EVENTS, RevenueTotals } from "@/components/RevenueSummary";

/** Doanh thu một ngày (giờ Việt Nam) do máy chủ tổng hợp từ sổ giao dịch (GET /bookings/revenue/daily). */
interface DailyRevenueData extends RevenueTotals {
  date: string;
  transactions: LedgerTransaction[];
}

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
        <LedgerList transactions={data.transactions} empty="Chưa có giao dịch nào trong ngày này." />
      </div>
    </div>
  );
}
