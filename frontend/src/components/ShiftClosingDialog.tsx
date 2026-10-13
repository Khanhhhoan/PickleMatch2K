"use client";

/**
 * Kết ca trong ngày, dùng chung cho cổng Chủ sân và cổng Nhân viên: nhập tiền vốn đầu ca và tiền mặt đếm được,
 * xem bảng đối chiếu với các khoản hệ thống đã ghi nhận, rồi xác nhận để lưu. Các khoản thu, hoàn do máy chủ
 * tính từ sổ giao dịch; người dùng chỉ nhập hai số tiền mình đếm.
 */
import React, { useEffect, useState } from "react";
import { fetchApi, formatVND, parseUtcDate } from "@/lib/api";
import { formatDisplayDate } from "@/lib/booking";
import { useToast } from "@/components/Toast";
import { INPUT, LABEL, Line, Modal, PRIMARY, SECONDARY } from "@/components/ManagementUi";

interface Closing {
  id: number;
  venue_id: number;
  business_date: string;
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

interface Summary {
  venue_id: number;
  venue_name: string;
  business_date: string;
  last_closed_at?: string | null;
  cash_collected: number;
  transfer_collected: number;
  refunded: number;
  closings: Closing[];
}

type Step = "count" | "review" | "done";

const timeOf = (iso: string) => parseUtcDate(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

/** Số tiền nguyên, không âm; nhập sai (số âm, số lẻ, bỏ trống) trả về null. */
const wholeAmount = (text: string): number | null => (/^\d{1,10}$/.test(text.trim()) ? Number(text.trim()) : null);

function Difference({ value }: { value: number }) {
  if (value === 0) return <span className="text-emerald-700">Khớp</span>;
  return value > 0 ? <span className="text-amber-700">Thừa {formatVND(value)}</span> : <span className="text-rose-600">Thiếu {formatVND(-value)}</span>;
}

function Reconciliation({ cash, transfer, refunded, openingFloat, counted }: {
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

export default function ShiftClosingDialog({ onClose }: { onClose: () => void }) {
  const { success: toastSuccess, error: toastError } = useToast();
  const [venues, setVenues] = useState<{ id: number; name: string }[]>([]);
  const [venueId, setVenueId] = useState<number | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [step, setStep] = useState<Step>("count");
  const [openingFloat, setOpeningFloat] = useState("");
  const [countedCash, setCountedCash] = useState("");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Closing | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchApi("/venues/me")
      .then((data) => setVenues(Array.isArray(data) ? data : []))
      .catch(() => setVenues([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchApi(`/payments/shift-closings${venueId ? `?venue_id=${venueId}` : ""}`)
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Không tải được số liệu kết ca.");
      });
    return () => {
      cancelled = true;
    };
  }, [venueId, reloadKey]);

  const review = (e: React.FormEvent) => {
    e.preventDefault();
    if (!openingFloat.trim() || !countedCash.trim()) {
      setFormError("Vui lòng nhập cả hai số tiền (nhập 0 nếu không có).");
      return;
    }
    if (wholeAmount(openingFloat) === null || wholeAmount(countedCash) === null) {
      setFormError("Số tiền phải là số nguyên, không âm.");
      return;
    }
    setFormError(null);
    setReloadKey((key) => key + 1); // lấy lại số mới nhất trước khi đối chiếu
    setStep("review");
  };

  const confirm = async () => {
    if (!summary) return;
    setBusy(true);
    try {
      const closing = await fetchApi("/payments/shift-closings", {
        method: "POST",
        body: JSON.stringify({
          venue_id: summary.venue_id,
          opening_float: Number(openingFloat),
          counted_cash: Number(countedCash),
          note: note.trim() || null,
        }),
      });
      setSaved(closing);
      setStep("done");
      setReloadKey((key) => key + 1);
      toastSuccess("Đã kết ca.");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Không kết ca được. Vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Kết ca trong ngày" onClose={onClose}>
      {loadError ? (
        <p className="text-xs text-rose-600">{loadError}</p>
      ) : !summary ? (
        <p className="text-xs text-[#51627c]">Đang tải số liệu...</p>
      ) : (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-black text-[#17253d] truncate">{summary.venue_name}</p>
              <p className="text-[11px] text-[#718096]">
                {formatDisplayDate(summary.business_date)}
                {step !== "done" && ` • ${summary.last_closed_at ? `Tính từ lần kết ca lúc ${timeOf(summary.last_closed_at)}` : "Tính từ đầu ngày"}`}
              </p>
            </div>
            {venues.length > 1 && step === "count" && (
              <select
                className={`${INPUT} w-auto`}
                value={summary.venue_id}
                onChange={(e) => setVenueId(Number(e.target.value))}
                aria-label="Chọn cụm sân kết ca"
              >
                {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            )}
          </div>

          {step === "count" && (
            <form onSubmit={review} noValidate className="space-y-3">
              <p className="text-xs text-[#51627c]">Đếm tiền mặt trong két rồi nhập hai số dưới đây. Hệ thống sẽ đối chiếu với các khoản đã ghi nhận.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className={LABEL} htmlFor="shift-opening-float">Tiền vốn đầu ca</label>
                  <input id="shift-opening-float" className={INPUT} type="number" min={0} step={1000} inputMode="numeric" placeholder="0"
                    value={openingFloat} onChange={(e) => setOpeningFloat(e.target.value)} />
                  <p className="text-[11px] text-[#8a97ab] mt-1">Tiền có sẵn trong két khi bắt đầu ca</p>
                </div>
                <div>
                  <label className={LABEL} htmlFor="shift-counted-cash">Tiền mặt đếm được</label>
                  <input id="shift-counted-cash" className={INPUT} type="number" min={0} step={1000} inputMode="numeric" placeholder="0"
                    value={countedCash} onChange={(e) => setCountedCash(e.target.value)} />
                  <p className="text-[11px] text-[#8a97ab] mt-1">Toàn bộ tiền mặt đang có trong két</p>
                </div>
              </div>
              {formError && <p className="text-xs font-bold text-rose-600" role="alert">{formError}</p>}
              <div className="flex justify-end gap-2">
                <button type="button" className={SECONDARY} onClick={onClose}>Đóng</button>
                <button type="submit" className={PRIMARY}>Đối chiếu</button>
              </div>
            </form>
          )}

          {step === "review" && (
            <div className="space-y-3">
              <Reconciliation
                cash={summary.cash_collected}
                transfer={summary.transfer_collected}
                refunded={summary.refunded}
                openingFloat={Number(openingFloat)}
                counted={Number(countedCash)}
              />
              <div>
                <label className={LABEL} htmlFor="shift-note">Ghi chú (không bắt buộc)</label>
                <input id="shift-note" className={INPUT} maxLength={300} placeholder="Ví dụ: lý do chênh lệch"
                  value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" className={SECONDARY} disabled={busy} onClick={() => setStep("count")}>Nhập lại</button>
                <button type="button" className={PRIMARY} disabled={busy} onClick={confirm}>{busy ? "Đang lưu..." : "Xác nhận kết ca"}</button>
              </div>
            </div>
          )}

          {step === "done" && saved && (
            <div className="space-y-3">
              <p className="p-3 rounded-xl bg-emerald-50 border border-emerald-100 text-xs font-bold text-emerald-800">
                Đã kết ca lúc {timeOf(saved.closed_at)}. Số liệu đã được lưu.
              </p>
              <Reconciliation
                cash={saved.cash_collected}
                transfer={saved.transfer_collected}
                refunded={saved.refunded}
                openingFloat={saved.opening_float}
                counted={saved.counted_cash}
              />
              <div className="flex justify-end">
                <button type="button" className={PRIMARY} onClick={onClose}>Đóng</button>
              </div>
            </div>
          )}

          <div>
            <p className={LABEL}>Các lần kết ca gần đây</p>
            {summary.closings.length === 0 ? (
              <p className="text-xs text-[#8a97ab]">Chưa có lần kết ca nào.</p>
            ) : (
              <ul className="divide-y divide-[#f1f4f9] border border-[#e8edf3] rounded-xl px-3">
                {summary.closings.slice(0, 5).map((closing) => (
                  <li key={closing.id} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                    <div className="min-w-0">
                      <p className="font-bold text-[#17253d]">
                        {formatDisplayDate(closing.business_date)} • {timeOf(closing.closed_at)}
                      </p>
                      <p className="text-[#8a97ab] truncate">
                        {closing.closed_by_name} • thu {formatVND(closing.total_collected)}
                        {closing.note ? ` • ${closing.note}` : ""}
                      </p>
                    </div>
                    <span className="font-bold shrink-0"><Difference value={closing.difference} /></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
