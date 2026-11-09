import React from "react";
import { formatVND } from "@/lib/api";

/** Các khoản của một ngày, tháng hoặc năm (giờ Việt Nam) do máy chủ tổng hợp từ sổ giao dịch. */
export interface RevenueTotals {
  collected: number;
  cash: number;
  transfer: number;
  refunded: number;
  net: number;
  plays_total: number;
  plays_arrived: number;
}

export const REVENUE_BOX = "rounded-xl bg-[#f8fafd] border border-[#e8edf3] p-4";

// Sự kiện trực tiếp làm số liệu doanh thu thay đổi
export const REVENUE_LIVE_EVENTS = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "BOOKING_STATUS_CHANGED", "SLOT_RELEASED", "BOOKING_RESCHEDULED"];

/** Bốn ô: tổng thu, tiền mặt, chuyển khoản, hoàn tiền; bên dưới là thực thu và số lượt chơi. */
export default function RevenueSummary({ data, collectedLabel, cashHint }: { data: RevenueTotals; collectedLabel: string; cashHint: string }) {
  const tiles = [
    { label: collectedLabel, value: formatVND(data.collected), hint: "Tiền cọc và tiền thu tại sân", dot: "bg-[#476cf3]" },
    { label: "Tiền mặt", value: formatVND(data.cash), hint: cashHint, dot: "bg-emerald-500" },
    { label: "Chuyển khoản", value: formatVND(data.transfer), hint: "Cọc qua VietQR và chuyển khoản tại quầy", dot: "bg-sky-500" },
    { label: "Hoàn tiền", value: data.refunded > 0 ? `-${formatVND(data.refunded)}` : formatVND(0), hint: "Đã chuyển trả cho khách", dot: "bg-rose-500" },
  ];

  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((tile) => (
          <div key={tile.label} className={REVENUE_BOX}>
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
    </>
  );
}
