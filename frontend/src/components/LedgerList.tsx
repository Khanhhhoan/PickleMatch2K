import React from "react";
import { formatVND, parseUtcDate } from "@/lib/api";

/** Một giao dịch trong sổ do máy chủ trả về. */
export interface LedgerTransaction {
  id: number;
  transaction_code?: string | null;
  kind?: string | null;
  method?: string | null;
  amount_in: number;
  created_at?: string | null;
  booking?: { booking_code?: string | null } | null;
}

const KIND_LABEL: Record<string, string> = { DEPOSIT: "Tiền cọc", BALANCE: "Thu tại sân", REFUND: "Hoàn tiền" };
const METHOD_LABEL: Record<string, string> = { BANK_TRANSFER: "Chuyển khoản", CASH: "Tiền mặt" };

const timeOnly = (iso: string) => parseUtcDate(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

/** Từng giao dịch: loại, hình thức, giờ ghi sổ, mã đơn và số tiền (khoản hoàn mang dấu trừ). */
export default function LedgerList({ transactions, empty, when = timeOnly }: {
  transactions: LedgerTransaction[];
  empty: string;
  when?: (iso: string) => string; // cách ghi giờ của một giao dịch, mặc định chỉ giờ:phút
}) {
  if (transactions.length === 0) {
    return <p className="py-6 text-center text-xs text-[#8a97ab] rounded-xl border border-dashed border-[#dde4ef]">{empty}</p>;
  }
  return (
    <ul className="divide-y divide-[#f1f4f9] max-h-80 overflow-y-auto">
      {transactions.map((t) => (
        <li key={t.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
          <div className="min-w-0">
            <p className="font-bold text-[#17253d]">
              {KIND_LABEL[t.kind || ""] || t.kind}{" "}
              <span className="text-[#718096] font-semibold">• {METHOD_LABEL[t.method || ""] || t.method}</span>
            </p>
            <p className="text-[#8a97ab]">
              {t.created_at ? when(t.created_at) : ""}
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
  );
}
