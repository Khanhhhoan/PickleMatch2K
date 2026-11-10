/**
 * Phần dùng chung của hộp Kết ca và thẻ Lịch sử kết ca: dữ liệu một lần kết ca, cách ghi giờ, nhãn chênh lệch
 * (Khớp / Thừa / Thiếu) và bảng đối chiếu tiền mặt trong két với sổ giao dịch.
 */
import React from "react";
import { formatLocalDate, formatVND, parseUtcDate } from "@/lib/api";
import { Line } from "@/components/ManagementUi";

/** Một lần kết ca do máy chủ trả về. */
export interface Closing {
  id: number;
  venue_id: number;
  business_date: string; // ngày kết ca (giờ Việt Nam)
  period_start?: string | null; // ca kéo dài từ đây (lần kết ca trước) tới closed_at
  closed_at: string;
  closed_by_name: string;
  opening_float: number;
  counted_cash: number;
  cash_collected: number;
  transfer_collected: number;
  refunded: number;
  total_collected: number;
  expected_cash: number;
  difference: number;
  note?: string | null;
}

export const timeOf = (iso: string) => parseUtcDate(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

// Ghép tay ngày/tháng: toLocaleDateString("vi-VN", { day, month }) cho ra "15-10", khác kiểu dd/mm dùng khắp ứng dụng
const dayMonth = (moment: Date) => `${String(moment.getDate()).padStart(2, "0")}/${String(moment.getMonth() + 1).padStart(2, "0")}`;

/** Giờ, kèm ngày nếu khác ngày `day` (YYYY-MM-DD): "20:00 15/10" cho ca bắt đầu từ hôm trước. */
export const momentOn = (iso: string, day: string) => {
  const moment = parseUtcDate(iso);
  return formatLocalDate(moment) === day ? timeOf(iso) : `${timeOf(iso)} ${dayMonth(moment)}`;
};

/** Giờ, kèm ngày nếu không phải hôm nay. */
export const momentOf = (iso: string) => momentOn(iso, formatLocalDate());

export function Difference({ value }: { value: number }) {
  if (value === 0) return <span className="text-emerald-700">Khớp</span>;
  return value > 0 ? <span className="text-amber-700">Thừa {formatVND(value)}</span> : <span className="text-rose-600">Thiếu {formatVND(-value)}</span>;
}

export function Reconciliation({ cash, transfer, refunded, openingFloat, counted }: {
  cash: number;
  transfer: number;
  refunded: number;
  openingFloat: number;
  counted: number;
}) {
  const expected = openingFloat + cash;
  return (
    <div className="space-y-2 p-4 rounded-xl bg-[#f8fafd] border border-[#e8edf3]">
      <Line label="Tổng thu trong ca" value={formatVND(cash + transfer)} />
      <Line label="Tiền mặt" value={formatVND(cash)} />
      <Line label="Chuyển khoản" value={formatVND(transfer)} />
      {refunded > 0 && <Line label="Đã hoàn cho khách" value={formatVND(refunded)} />}
      <div className="border-t border-[#e8edf3]" />
      <Line label="Tiền vốn đầu ca" value={formatVND(openingFloat)} />
      <Line label="Tiền mặt phải có trong két" value={formatVND(expected)} />
      <Line label="Tiền mặt đếm được" value={formatVND(counted)} />
      <Line label="Chênh lệch" value={<Difference value={counted - expected} />} />
    </div>
  );
}
