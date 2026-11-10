"use client";

/**
 * Lịch sử kết ca của chủ sân (thẻ "Lịch sử" trong hộp Kết ca): mọi lần kết ca của một cụm sân trong một tháng, lọc
 * được theo ngày, kèm số lần khớp, thừa, thiếu và các khoản cộng theo ca. Bấm một lần kết ca để xem bảng đối chiếu
 * và đúng những giao dịch thuộc ca đó, để lần ra khoản gây chênh lệch.
 * Một lần kết ca được xếp vào ngày kết ca (giờ Việt Nam): ca 20:00 tới 00:15 hôm sau nằm ở ngày hôm sau.
 */
import React, { useEffect, useState } from "react";
import { errorMessage, fetchApi, formatLocalDate, formatVND } from "@/lib/api";
import { formatDisplayDate } from "@/lib/booking";
import { LABEL } from "@/components/ManagementUi";
import LedgerList, { LedgerTransaction } from "@/components/LedgerList";
import MonthPicker, { PICKER_SELECT } from "@/components/MonthPicker";
import { Closing, Difference, Reconciliation, momentOn, timeOf } from "@/components/ShiftClosingParts";

interface History {
  venue_id: number;
  venue_name: string;
  month: string; // YYYY-MM
  first_date?: string | null; // ngày của lần kết ca đầu tiên tại cụm sân
  closings: Closing[]; // mới nhất trước
}

interface ClosingDetail extends Closing {
  transactions: LedgerTransaction[]; // các giao dịch thuộc ca, cũ nhất trước
}

const TILE = "rounded-xl bg-[#f8fafd] border border-[#e8edf3] p-3 min-w-0";
const TILE_VALUE = "text-sm sm:text-base font-black mt-1 leading-tight tabular-nums break-words";

const total = (closings: Closing[], pick: (closing: Closing) => number) => closings.reduce((sum, closing) => sum + pick(closing), 0);

export default function ShiftHistory({ venues, initialVenueId, initialVenueName }: {
  venues: { id: number; name: string }[];
  initialVenueId: number;
  initialVenueName: string;
}) {
  const thisMonth = formatLocalDate().slice(0, 7);
  const [venueId, setVenueId] = useState(initialVenueId);
  const [month, setMonth] = useState(thisMonth);
  const [day, setDay] = useState(""); // một ngày trong tháng, "" là cả tháng
  const [result, setResult] = useState<{ key: string; data?: History; error?: string } | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  // Các khoản của từng lần kết ca đã mở: chuỗi là thông báo lỗi khi tải
  const [details, setDetails] = useState<Record<number, ClosingDetail | string | undefined>>({});

  useEffect(() => {
    let cancelled = false;
    const key = `${venueId}|${month}`;
    fetchApi(`/payments/shift-closings/history?venue_id=${venueId}&month=${month}`)
      .then((data: History) => {
        if (!cancelled) setResult({ key, data });
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, error: errorMessage(err, "Không tải được lịch sử kết ca.") });
      });
    return () => {
      cancelled = true;
    };
  }, [venueId, month]);

  const pickVenue = (id: number) => {
    setVenueId(id);
    setDay("");
    setOpenId(null);
  };
  const pickMonth = (value: string) => {
    setMonth(value);
    setDay("");
    setOpenId(null);
  };
  const pickDay = (value: string) => {
    setDay(value);
    setOpenId(null);
  };

  // Mở một lần kết ca: tải các giao dịch của ca đó một lần (lần trước lỗi thì tải lại)
  const toggle = (id: number) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    if (typeof details[id] === "object") return;
    setDetails((all) => ({ ...all, [id]: undefined }));
    fetchApi(`/payments/shift-closings/${id}`)
      .then((data: ClosingDetail) => setDetails((all) => ({ ...all, [id]: data })))
      .catch((err) => setDetails((all) => ({ ...all, [id]: errorMessage(err, "Không tải được các khoản của ca này.") })));
  };

  const current = result?.key === `${venueId}|${month}` ? result : null;
  const closings = current?.data?.closings ?? [];
  const days = Array.from(new Set(closings.map((closing) => closing.business_date))); // mới nhất trước
  const selectedDay = days.includes(day) ? day : "";
  const shown = selectedDay ? closings.filter((closing) => closing.business_date === selectedDay) : closings;
  const over = shown.filter((closing) => closing.difference > 0);
  const short = shown.filter((closing) => closing.difference < 0);
  const refunded = total(shown, (closing) => closing.refunded);
  // Bộ chọn tháng không lùi quá năm của lần kết ca đầu tiên (lúc đang tải vẫn dùng số của lần tải trước)
  const firstYear = Math.min(
    Number(thisMonth.slice(0, 4)),
    Number(result?.data?.first_date?.slice(0, 4)) || Infinity,
    Number(month.slice(0, 4)),
  );
  const monthLabel = `tháng ${Number(month.slice(5))}/${month.slice(0, 4)}`;
  const venueName = current?.data?.venue_name ?? venues.find((venue) => venue.id === venueId)?.name ?? initialVenueName;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-black text-[#17253d] truncate">{venueName}</p>
          <p className="text-[11px] text-[#718096] first-letter:uppercase">{selectedDay ? formatDisplayDate(selectedDay) : monthLabel}</p>
        </div>
        {venues.length > 1 && (
          <select
            className={`${PICKER_SELECT} max-w-[50%]`}
            value={venueId}
            onChange={(e) => pickVenue(Number(e.target.value))}
            aria-label="Chọn cụm sân xem lịch sử"
          >
            {venues.map((venue) => (
              <option key={venue.id} value={venue.id}>
                {venue.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <MonthPicker
            month={month}
            onChange={pickMonth}
            thisMonth={thisMonth}
            firstYear={firstYear}
            monthLabel="Chọn tháng xem kết ca"
            yearLabel="Chọn năm xem kết ca"
          />
          <select
            className={PICKER_SELECT}
            value={selectedDay}
            onChange={(e) => pickDay(e.target.value)}
            disabled={days.length === 0}
            aria-label="Chọn ngày xem kết ca"
          >
            <option value="">Cả tháng</option>
            {days.map((value) => (
              <option key={value} value={value}>
                {formatDisplayDate(value)} ({closings.filter((closing) => closing.business_date === value).length} lần)
              </option>
            ))}
          </select>
        </div>
        <p className="text-[11px] text-[#8a97ab]">Mỗi lần kết ca nằm ở ngày kết ca: ca qua nửa đêm tính vào ngày hôm sau.</p>
      </div>

      {!current ? (
        <div className="h-40 rounded-xl bg-[#f8fafd] border border-[#e8edf3] animate-pulse" />
      ) : !current.data ? (
        <p className="text-xs text-rose-600">{current.error}</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <div className={TILE}>
              <p className="text-[11px] font-bold text-[#718096]">Lần kết ca</p>
              <p className={`${TILE_VALUE} text-[#17253d]`}>{shown.length}</p>
              <p className="text-[11px] text-[#8a97ab] mt-0.5">{shown.length - over.length - short.length} lần khớp</p>
            </div>
            <div className={TILE}>
              <p className="text-[11px] font-bold text-[#718096]">Thừa</p>
              <p className={`${TILE_VALUE} ${over.length ? "text-amber-700" : "text-[#17253d]"}`}>
                {formatVND(total(over, (closing) => closing.difference))}
              </p>
              <p className="text-[11px] text-[#8a97ab] mt-0.5">{over.length} lần</p>
            </div>
            <div className={TILE}>
              <p className="text-[11px] font-bold text-[#718096]">Thiếu</p>
              <p className={`${TILE_VALUE} ${short.length ? "text-rose-600" : "text-[#17253d]"}`}>
                {formatVND(-total(short, (closing) => closing.difference))}
              </p>
              <p className="text-[11px] text-[#8a97ab] mt-0.5">{short.length} lần</p>
            </div>
          </div>
          <p className="text-xs text-[#51627c]">
            Cộng theo các ca: tiền mặt <strong className="text-[#17253d] font-black">{formatVND(total(shown, (closing) => closing.cash_collected))}</strong>
            {" • "}chuyển khoản <strong className="text-[#17253d] font-black">{formatVND(total(shown, (closing) => closing.transfer_collected))}</strong>
            {refunded > 0 && (
              <>
                {" • "}đã hoàn <strong className="text-[#17253d] font-black">{formatVND(refunded)}</strong>
              </>
            )}
          </p>

          {shown.length === 0 ? (
            <p className="py-6 text-center text-xs text-[#8a97ab] rounded-xl border border-dashed border-[#dde4ef]">
              Chưa có lần kết ca nào trong {monthLabel}.
            </p>
          ) : (
            <ul className="divide-y divide-[#f1f4f9] border border-[#e8edf3] rounded-xl overflow-hidden">
              {shown.map((closing) => {
                const open = openId === closing.id;
                const detail = details[closing.id];
                return (
                  <li key={closing.id}>
                    <button
                      type="button"
                      onClick={() => toggle(closing.id)}
                      aria-expanded={open}
                      className="w-full px-3 py-2.5 flex items-center justify-between gap-3 text-xs text-left cursor-pointer hover:bg-[#f8fafd]"
                    >
                      <span className="min-w-0">
                        <span className="block font-bold text-[#17253d]">
                          {formatDisplayDate(closing.business_date)} •{" "}
                          {closing.period_start ? `${momentOn(closing.period_start, closing.business_date)} - ` : ""}
                          {timeOf(closing.closed_at)}
                        </span>
                        <span className="block text-[#8a97ab] truncate">
                          {closing.closed_by_name} • thu {formatVND(closing.total_collected)}
                          {closing.note ? ` • ${closing.note}` : ""}
                        </span>
                      </span>
                      <span className="flex items-center gap-2 font-bold shrink-0">
                        <Difference value={closing.difference} />
                        <span aria-hidden="true" className="text-[#8a97ab]">
                          {open ? "▾" : "▸"}
                        </span>
                      </span>
                    </button>
                    {open && (
                      <div className="px-3 pb-3 space-y-3">
                        {closing.note && (
                          <p className="text-xs text-[#51627c] break-words">
                            <span className="font-bold text-[#17253d]">Ghi chú:</span> {closing.note}
                          </p>
                        )}
                        <Reconciliation
                          cash={closing.cash_collected}
                          transfer={closing.transfer_collected}
                          refunded={closing.refunded}
                          openingFloat={closing.opening_float}
                          counted={closing.counted_cash}
                        />
                        <div>
                          <p className={LABEL}>Các khoản trong ca{typeof detail === "object" ? ` (${detail.transactions.length})` : ""}</p>
                          {detail === undefined ? (
                            <p className="text-xs text-[#51627c]">Đang tải các khoản...</p>
                          ) : typeof detail === "string" ? (
                            <p className="text-xs text-rose-600">{detail}</p>
                          ) : (
                            <LedgerList
                              transactions={detail.transactions}
                              empty="Ca này không có khoản thu hay hoàn nào."
                              when={(iso) => momentOn(iso, closing.business_date)}
                            />
                          )}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
