"use client";

import React, { useMemo, useState } from "react";
import { apiDelete, apiPut, formatDateTime, formatVND } from "@/lib/api";
import { BOOKING_STATUS_LABEL, PAYMENT_STATUS_LABEL, statusTone } from "@/lib/labels";
import { Booking, TabProps } from "@/lib/types";
import { BTN_DANGER, Badge, Chips, DataTable, INPUT, TD, Toolbar } from "@/components/ui";

const STATUSES = ["PENDING", "CONFIRMED", "CHECKED_IN", "COMPLETED", "NO_SHOW", "CANCELLED", "EXPIRED"];

/** Gộp các khung 60 phút liền nhau trên cùng một sân: "Sân 1 • 12/10 • 18:00-20:00". */
function describeSlots(booking: Booking): string[] {
  const sorted = [...booking.details].sort(
    (a, b) => a.date.localeCompare(b.date) || a.court_id - b.court_id || a.start_time.localeCompare(b.start_time),
  );
  const merged: { court: string; date: string; start: string; end: string; courtId: number }[] = [];
  for (const d of sorted) {
    const last = merged[merged.length - 1];
    const start = d.start_time.slice(0, 5);
    const end = d.end_time.slice(0, 5);
    if (last && last.courtId === d.court_id && last.date === d.date && last.end === start) last.end = end;
    else merged.push({ court: d.court_name || `Sân #${d.court_id}`, date: d.date, start, end, courtId: d.court_id });
  }
  return merged.map((m) => `${m.court} • ${m.date.slice(8)}/${m.date.slice(5, 7)} • ${m.start}-${m.end}`);
}

export default function BookingsTab({ data, run }: TabProps) {
  const [status, setStatus] = useState("ALL");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return data.bookings.filter((b) => {
      if (status === "REFUND" ? b.refund_status !== "PENDING" : status !== "ALL" && b.status !== status) return false;
      if (!term) return true;
      return [b.booking_code, b.user_name, b.user_phone, b.user_email, b.details[0]?.venue_name].some((value) => (value || "").toLowerCase().includes(term));
    });
  }, [data.bookings, status, search]);

  const cancel = (booking: Booking) => {
    const reason = window.prompt(
      `Hủy đơn ${booking.booking_code} thay mặt cụm sân?` +
        (booking.paid_amount > 0 ? ` Khách sẽ được hoàn toàn bộ ${formatVND(booking.paid_amount)} đã trả.` : "") +
        "\nNhập lý do hủy:",
      "",
    );
    if (reason === null) return;
    run(() => apiPut(`/bookings/${booking.id}/status`, { status: "CANCELLED", reason: reason.trim() || "Quản trị viên hủy đơn" }), "Đã hủy đơn.");
  };

  const remove = (booking: Booking) => {
    if (!window.confirm(`Xóa hẳn đơn ${booking.booking_code}? Chỉ xóa được đơn đã hủy/hết hạn và chưa có giao dịch nào.`)) return;
    run(() => apiDelete(`/bookings/admin/${booking.id}`), "Đã xóa đơn.");
  };

  const pendingRefunds = data.bookings.filter((b) => b.refund_status === "PENDING").length;

  return (
    <div className="space-y-4">
      <Toolbar>
        <Chips
          value={status}
          onChange={setStatus}
          options={[
            { value: "ALL", label: `Tất cả (${data.bookings.length})` },
            ...STATUSES.map((s) => ({ value: s, label: `${BOOKING_STATUS_LABEL[s]} (${data.bookings.filter((b) => b.status === s).length})` })),
            { value: "REFUND", label: `Chờ hoàn tiền (${pendingRefunds})` },
          ]}
        />
        <input className={`${INPUT} w-72`} placeholder="Tìm theo mã đơn, khách, cụm sân" value={search} onChange={(e) => setSearch(e.target.value)} />
      </Toolbar>

      <DataTable headers={["Mã đơn", "Khách", "Cụm sân / lịch", "Tổng / đã trả", "Trạng thái", ""]} empty={filtered.length === 0}>
        {filtered.map((b) => (
          <tr key={b.id}>
            <td className={TD}>
              <p className="font-mono font-bold text-slate-900">{b.booking_code || `#${b.id}`}</p>
              <p className="text-xs text-slate-500">{b.source === "DESK" ? "Tạo tại quầy" : "Đặt trên web"}</p>
              <p className="text-xs text-slate-400">{formatDateTime(b.created_at)}</p>
            </td>
            <td className={TD}>
              <p className="text-slate-900">{b.user_name || "—"}</p>
              <p className="text-xs text-slate-500">{[b.user_phone, b.user_email].filter(Boolean).join(" • ")}</p>
            </td>
            <td className={`${TD} text-xs`}>
              <p className="font-semibold text-slate-900">{b.details[0]?.venue_name || "—"}</p>
              {describeSlots(b).map((line) => <p key={line} className="text-slate-600">{line}</p>)}
            </td>
            <td className={`${TD} whitespace-nowrap`}>
              <p className="font-bold text-slate-900">{formatVND(b.total_price)}</p>
              <p className="text-xs text-slate-500">Đã trả {formatVND(b.paid_amount)}</p>
            </td>
            <td className={`${TD} space-y-1`}>
              <Badge tone={statusTone(b.status)}>{BOOKING_STATUS_LABEL[b.status] || b.status}</Badge>
              <br />
              <Badge tone={statusTone(b.payment_status)}>{PAYMENT_STATUS_LABEL[b.payment_status] || b.payment_status}</Badge>
              {b.refund_status && (
                <p className="text-xs font-semibold text-amber-700">
                  Hoàn {formatVND(b.refund_amount)}: {b.refund_status === "PENDING" ? "chờ chuyển" : b.refund_status === "COMPLETED" ? "đã chuyển" : "từ chối"}
                </p>
              )}
            </td>
            <td className={`${TD} text-right whitespace-nowrap space-x-1.5`}>
              {["PENDING", "CONFIRMED", "CHECKED_IN"].includes(b.status) && (
                <button type="button" className={BTN_DANGER} onClick={() => cancel(b)}>Hủy đơn</button>
              )}
              {["CANCELLED", "EXPIRED"].includes(b.status) && b.paid_amount === 0 && (
                <button type="button" className={BTN_DANGER} onClick={() => remove(b)}>Xóa</button>
              )}
            </td>
          </tr>
        ))}
      </DataTable>
      <p className="text-xs text-slate-500">
        Check-in, thu tiền và xác nhận hoàn tiền do chủ sân/nhân viên thực hiện tại quầy. Đơn đã phát sinh giao dịch không xóa được để giữ sổ sách.
      </p>
    </div>
  );
}
