"use client";

/**
 * Bàn làm việc tại quầy, dùng chung cho cổng Chủ sân và cổng Nhân viên:
 * lịch theo sân của một ngày, danh sách đơn, tạo đơn cho khách tại quầy, check-in (nhập mã hoặc quét QR),
 * thu tiền, dời lịch, hủy và xác nhận hoàn tiền. Mọi thay đổi trạng thái đều do máy chủ thực hiện và kiểm tra.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchApi, formatLocalDate, formatVND, parseUtcDate } from "@/lib/api";
import {
  Booking,
  bookingCode,
  bookingStatusLabel,
  bookingStatusTone,
  formatDisplayDate,
  mergeSlots,
  paymentStatusLabel,
  paymentStatusTone,
  secondsUntil,
} from "@/lib/booking";
import { useWebSocket } from "@/lib/use-websocket";
import { useToast } from "@/components/Toast";

interface Venue {
  id: number;
  name: string;
  status: string;
  courts: { id: number; name: string; status: string }[];
}

interface Slot {
  start_time: string;
  end_time: string;
  price: number;
  is_available: boolean;
  is_past?: boolean;
  is_held?: boolean;
}

interface Availability {
  courts: { court_id: number; court_name: string; slots: Slot[] }[];
}

interface CreateForm {
  court_id: number;
  start_time: string;
  hours: number;
  customer_name: string;
  customer_phone: string;
  price: string;
  payment: "CASH" | "BANK_TRANSFER" | "DEPOSIT_PAID" | "UNPAID";
  walkin: boolean;
}

type ListFilter = "date" | "todo" | "all";

const CARD = "bg-white rounded-2xl border border-[#e8edf3] shadow-[0_12px_35px_rgba(29,51,87,0.035)]";
const INPUT = "w-full h-10 px-3 bg-white border border-[#dde4ef] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3]";
const LABEL = "block text-[11px] font-bold text-[#51627c] mb-1";
const PRIMARY = "px-4 py-2.5 bg-[#476cf3] text-white rounded-xl text-xs font-bold hover:bg-[#3b61e8] disabled:opacity-50 transition cursor-pointer";
const SECONDARY = "px-3 py-2 bg-[#f1f4fb] hover:bg-[#e4ebf7] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] cursor-pointer disabled:opacity-50";
const DANGER = "px-3 py-2 rounded-xl text-xs font-bold text-rose-600 border border-rose-200 hover:bg-rose-50 cursor-pointer disabled:opacity-50";

const PAYMENT_OPTIONS: { value: CreateForm["payment"]; label: string }[] = [
  { value: "CASH", label: "Đã thu đủ - tiền mặt" },
  { value: "BANK_TRANSFER", label: "Đã thu đủ - chuyển khoản" },
  { value: "DEPOSIT_PAID", label: "Đã thu cọc 50% - tiền mặt" },
  { value: "UNPAID", label: "Chưa thu (trả khi đến sân)" },
];

const addHours = (time: string, hours: number) => {
  const [h, m] = time.split(":").map(Number);
  return `${String(h + hours).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};

const slotKey = (courtId: number, date: string, start: string) => `${courtId}|${date}|${start.slice(0, 5)}`;

/** Đơn còn chiếm khung giờ trên lịch (đơn chờ cọc đã quá hạn không còn giữ chỗ). */
const occupiesSlot = (b: Booking) =>
  !["CANCELLED", "EXPIRED"].includes(b.status) && (b.status !== "PENDING" || secondsUntil(b.expires_at) > 0);

export default function BookingDesk({ heading }: { heading: string }) {
  const { success: toastSuccess, error: toastError } = useToast();
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venueId, setVenueId] = useState<number | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [grid, setGrid] = useState<Availability | null>(null);
  const [date, setDate] = useState(() => formatLocalDate());
  const [loading, setLoading] = useState(true);
  const [simulatorEnabled, setSimulatorEnabled] = useState(false);
  const [listFilter, setListFilter] = useState<ListFilter>("date");
  const [search, setSearch] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [scanning, setScanning] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [createForm, setCreateForm] = useState<CreateForm | null>(null);
  const [busy, setBusy] = useState(false);

  const today = formatLocalDate();
  const venue = useMemo(() => venues.find((v) => v.id === venueId) || venues[0] || null, [venues, venueId]);
  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  const loadBookings = useCallback(async () => {
    const data = await fetchApi("/bookings/owner/list").catch(() => []);
    setBookings(Array.isArray(data) ? data : []);
  }, []);

  const loadGrid = useCallback(async () => {
    if (!venue) return;
    const data = await fetchApi(`/search/venues/${venue.id}/availability?target_date=${date}`).catch(() => null);
    setGrid(data);
  }, [venue, date]);

  useEffect(() => {
    Promise.all([fetchApi("/venues/me").catch(() => []), fetchApi("/payments/config").catch(() => null), loadBookings()])
      .then(([venueData, config]) => {
        setVenues(Array.isArray(venueData) ? venueData : []);
        setSimulatorEnabled(Boolean(config?.simulator_enabled));
      })
      .finally(() => setLoading(false));
  }, [loadBookings]);

  useEffect(() => {
    loadGrid();
  }, [loadGrid]);

  useEffect(() => {
    if (!lastMessage) return;
    const relevant = ["PAYMENT_CONFIRMED", "SLOT_BOOKED", "SLOT_RELEASED", "SLOT_HELD", "BOOKING_STATUS_CHANGED", "BOOKING_RESCHEDULED", "PRICE_UPDATED"];
    if (relevant.includes(lastMessage.type)) {
      loadBookings();
      loadGrid();
    }
  }, [lastMessage, loadBookings, loadGrid]);

  const venueBookings = useMemo(
    () => bookings.filter((b) => venue && b.details.some((d) => d.venue_id === venue.id)),
    [bookings, venue],
  );

  const occupied = useMemo(() => {
    const map = new Map<string, Booking>();
    venueBookings.filter(occupiesSlot).forEach((b) =>
      b.details.filter((d) => d.is_active).forEach((d) => map.set(slotKey(d.court_id, d.date, d.start_time), b)),
    );
    return map;
  }, [venueBookings]);

  const detail = detailId ? bookings.find((b) => b.id === detailId) || null : null;

  /** Chạy một thao tác ghi rồi tải lại dữ liệu; thông báo lỗi của máy chủ được hiển thị nguyên văn. */
  const act = async (action: () => Promise<unknown>, successMessage: string): Promise<boolean> => {
    setBusy(true);
    try {
      await action();
      toastSuccess(successMessage);
      await Promise.all([loadBookings(), loadGrid()]);
      return true;
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Thao tác không thực hiện được.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const openByCode = useCallback(
    (raw: string) => {
      const match = raw.toUpperCase().match(/PK2K\s*0*(\d+)/);
      const wanted = match ? `PK2K${match[1].padStart(6, "0")}` : raw.trim().toUpperCase();
      const found = bookings.find((b) => (b.booking_code || "").toUpperCase() === wanted);
      if (found) {
        setDetailId(found.id);
        setCodeInput("");
        setScanning(false);
      } else {
        toastError(`Không tìm thấy đơn ${wanted} trong các cụm sân bạn quản lý.`);
      }
    },
    [bookings, toastError],
  );

  const shiftDate = (days: number) => {
    const [y, m, d] = date.split("-").map(Number);
    setDate(formatLocalDate(new Date(y, m - 1, d + days)));
  };

  const openCreate = (courtId: number, start: string) =>
    setCreateForm({ court_id: courtId, start_time: start.slice(0, 5), hours: 1, customer_name: "", customer_phone: "", price: "", payment: "CASH", walkin: date === today });

  /** Số giờ liên tiếp còn trống tính từ khung bắt đầu, và tổng tiền theo bảng giá. */
  const createInfo = useMemo(() => {
    if (!createForm || !grid) return { maxHours: 1, listPrice: 0 };
    const slots = grid.courts.find((c) => c.court_id === createForm.court_id)?.slots || [];
    const startIndex = slots.findIndex((s) => s.start_time.slice(0, 5) === createForm.start_time);
    let maxHours = 0;
    while (startIndex >= 0 && slots[startIndex + maxHours]?.is_available && !slots[startIndex + maxHours]?.is_held && maxHours < 12) maxHours += 1;
    const listPrice = slots.slice(startIndex, startIndex + createForm.hours).reduce((sum, s) => sum + s.price, 0);
    return { maxHours: Math.max(1, maxHours), listPrice };
  }, [createForm, grid]);

  const submitCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm) return;
    const ok = await act(
      () =>
        fetchApi(createForm.walkin && date === today ? "/bookings/staff/walkin" : "/bookings/desk", {
          method: "POST",
          body: JSON.stringify({
            court_id: createForm.court_id,
            date,
            start_time: createForm.start_time,
            end_time: addHours(createForm.start_time, createForm.hours),
            customer_name: createForm.customer_name.trim() || null,
            customer_phone: createForm.customer_phone.trim() || null,
            price: createForm.price ? Number(createForm.price) : null,
            payment_method: createForm.payment,
          }),
        }),
      "Đã tạo đơn tại quầy.",
    );
    if (ok) setCreateForm(null);
  };

  const listed = useMemo(() => {
    const term = search.trim().toLowerCase();
    return venueBookings
      .filter((b) => {
        if (listFilter === "date" && !b.details.some((d) => d.date === date)) return false;
        if (listFilter === "todo" && !(b.status === "PENDING" || b.refund_status === "PENDING" || (b.status === "CHECKED_IN" && b.remaining_amount > 0))) return false;
        if (!term) return true;
        return [b.user_name, b.user_phone, b.booking_code].some((value) => (value || "").toLowerCase().includes(term));
      })
      .sort((a, b) => (a.details[0]?.date || "").localeCompare(b.details[0]?.date || "") || (a.details[0]?.start_time || "").localeCompare(b.details[0]?.start_time || ""));
  }, [venueBookings, listFilter, date, search]);

  const todoCount = venueBookings.filter((b) => b.status === "PENDING" || b.refund_status === "PENDING" || (b.status === "CHECKED_IN" && b.remaining_amount > 0)).length;

  if (loading) return <div className="p-10 text-center text-xs text-[#51627c]">Đang tải lịch đặt...</div>;
  if (!venue) {
    return <div className={`${CARD} p-8 text-center text-sm text-[#51627c]`}>Tài khoản của bạn chưa được gắn với cụm sân nào.</div>;
  }

  const slotTimes = grid?.courts[0]?.slots || [];

  return (
    <div className="space-y-6 font-sans">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-black text-[#6b7ba1] tracking-[1.6px] uppercase mb-1">{heading}</div>
          <h1 className="text-2xl sm:text-[26px] font-black text-[#17253d] tracking-tight m-0">{venue.name}</h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {venues.length > 1 && (
            <select value={venue.id} onChange={(e) => setVenueId(Number(e.target.value))} aria-label="Chọn cụm sân" className={`${INPUT} w-auto`}>
              {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          )}
          <form onSubmit={(e) => { e.preventDefault(); if (codeInput.trim()) openByCode(codeInput); }} className="flex gap-2">
            <input className={`${INPUT} w-44 font-mono uppercase`} placeholder="Mã đơn PK2K..." value={codeInput} onChange={(e) => setCodeInput(e.target.value)} aria-label="Mã đơn để check-in" />
            <button type="submit" className={PRIMARY}>Tìm đơn</button>
            <button type="button" className={SECONDARY} onClick={() => setScanning(true)}>Quét QR</button>
          </form>
        </div>
      </div>

      {/* Lịch theo sân */}
      <section className={`${CARD} p-5 space-y-4`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button type="button" className={SECONDARY} onClick={() => shiftDate(-1)} aria-label="Ngày trước">←</button>
            <input type="date" className={`${INPUT} w-40`} value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
            <button type="button" className={SECONDARY} onClick={() => shiftDate(1)} aria-label="Ngày sau">→</button>
            <button type="button" className={date === today ? PRIMARY : SECONDARY} onClick={() => setDate(today)}>Hôm nay</button>
          </div>
          <p className="text-xs font-bold text-[#17253d]">{formatDisplayDate(date)}</p>
          <div className="flex flex-wrap gap-3 text-[11px] text-[#51627c]">
            <Legend className="bg-white border-[#dde4ef]" label="Trống (bấm để tạo đơn)" />
            <Legend className="bg-amber-50 border-amber-200" label="Chờ cọc" />
            <Legend className="bg-emerald-50 border-emerald-200" label="Đã xác nhận" />
            <Legend className="bg-sky-50 border-sky-200" label="Đã nhận sân" />
            <Legend className="bg-[#eef1f6] border-[#dde4ef]" label="Đã qua / không đặt được" />
          </div>
        </div>

        {!grid || grid.courts.length === 0 ? (
          <p className="text-xs text-[#718096] py-6 text-center">
            {venue.status !== "ACTIVE" ? "Cụm sân đang không hoạt động nên không có lịch." : "Cụm sân không mở cửa vào ngày này."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-1 text-[11px]">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-white text-left pr-3 font-bold text-[#51627c]">Sân</th>
                  {slotTimes.map((slot) => (
                    <th key={slot.start_time} className="font-bold text-[#51627c] min-w-[74px]">{slot.start_time.slice(0, 5)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grid.courts.map((court) => (
                  <tr key={court.court_id}>
                    <td className="sticky left-0 bg-white pr-3 font-black text-[#17253d] whitespace-nowrap">{court.court_name}</td>
                    {court.slots.map((slot) => {
                      const booking = occupied.get(slotKey(court.court_id, date, slot.start_time));
                      if (booking) {
                        return (
                          <td key={slot.start_time}>
                            <button
                              type="button"
                              onClick={() => setDetailId(booking.id)}
                              title={`${bookingCode(booking)} - ${bookingStatusLabel(booking.status)}`}
                              className={`w-full h-10 px-1 rounded-lg border font-bold truncate cursor-pointer ${bookingStatusTone(booking.status)}`}
                            >
                              {(booking.user_name || "Khách").split(" ").slice(-1)[0]}
                            </button>
                          </td>
                        );
                      }
                      const free = slot.is_available && !slot.is_held;
                      return (
                        <td key={slot.start_time}>
                          <button
                            type="button"
                            disabled={!free}
                            onClick={() => openCreate(court.court_id, slot.start_time)}
                            title={slot.is_past ? "Khung giờ đã qua" : slot.is_held ? "Đang có khách giữ tạm trên web" : free ? "Tạo đơn tại quầy" : "Không đặt được"}
                            className={`w-full h-10 rounded-lg border font-bold ${
                              free ? "bg-white border-[#dde4ef] text-[#476cf3] hover:border-[#476cf3] cursor-pointer" : "bg-[#eef1f6] border-[#e3e8f0] text-[#b1bccd] cursor-not-allowed"
                            }`}
                          >
                            {free ? "+" : slot.is_held ? "giữ" : ""}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Danh sách đơn */}
      <section className={`${CARD} p-5 space-y-4`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1.5">
            {([["date", `Ngày ${date.slice(8)}/${date.slice(5, 7)}`], ["todo", `Cần xử lý (${todoCount})`], ["all", "Tất cả"]] as [ListFilter, string][]).map(([key, label]) => (
              <button key={key} type="button" onClick={() => setListFilter(key)} className={listFilter === key ? PRIMARY : SECONDARY}>{label}</button>
            ))}
          </div>
          <input className={`${INPUT} w-64`} placeholder="Tìm theo tên, số điện thoại, mã đơn" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>

        {listed.length === 0 ? (
          <p className="text-xs text-[#718096] py-6 text-center">Không có đơn nào.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[11px] text-[#718096] border-b border-[#eef1f6]">
                  <th className="py-2 pr-3">Mã đơn</th>
                  <th className="py-2 pr-3">Khách</th>
                  <th className="py-2 pr-3">Lịch</th>
                  <th className="py-2 pr-3 text-right">Tổng / đã trả</th>
                  <th className="py-2 pr-3">Trạng thái</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {listed.map((b) => (
                  <tr key={b.id} className="border-b border-[#f3f5f9] align-top">
                    <td className="py-2.5 pr-3 font-mono font-bold text-[#17253d]">{bookingCode(b)}{b.source === "DESK" && <span className="ml-1 text-[10px] text-[#718096]">quầy</span>}</td>
                    <td className="py-2.5 pr-3">
                      <p className="font-bold text-[#17253d]">{b.user_name}</p>
                      <p className="text-[#718096]">{b.user_phone || "—"}</p>
                    </td>
                    <td className="py-2.5 pr-3 text-[#3d4e68]">
                      {mergeSlots(b.details).map((s, i) => (
                        <p key={i}>{s.court_name} • {s.date.slice(8)}/{s.date.slice(5, 7)} • {s.start_time}-{s.end_time}</p>
                      ))}
                    </td>
                    <td className="py-2.5 pr-3 text-right">
                      <p className="font-bold text-[#17253d]">{formatVND(b.total_price)}</p>
                      <p className="text-[#718096]">{formatVND(b.paid_amount)}</p>
                    </td>
                    <td className="py-2.5 pr-3 space-y-1">
                      <span className={`inline-block px-2 py-0.5 rounded-md border font-bold ${bookingStatusTone(b.status)}`}>{bookingStatusLabel(b.status)}</span>
                      <br />
                      <span className={`inline-block px-2 py-0.5 rounded-md border font-bold ${paymentStatusTone(b.payment_status)}`}>{paymentStatusLabel(b.payment_status)}</span>
                      {b.refund_status === "PENDING" && <p className="font-bold text-amber-700">Chờ hoàn {formatVND(b.refund_amount || 0)}</p>}
                    </td>
                    <td className="py-2.5 text-right">
                      <button type="button" className={SECONDARY} onClick={() => setDetailId(b.id)}>Xử lý</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {createForm && (
        <Modal title={`Tạo đơn tại quầy - ${formatDisplayDate(date)}`} onClose={() => setCreateForm(null)}>
          <form onSubmit={submitCreate} className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className={LABEL}>Sân</label>
                <select className={INPUT} value={createForm.court_id} onChange={(e) => setCreateForm({ ...createForm, court_id: Number(e.target.value), hours: 1 })}>
                  {grid?.courts.map((c) => <option key={c.court_id} value={c.court_id}>{c.court_name}</option>)}
                </select>
              </div>
              <div>
                <label className={LABEL}>Bắt đầu</label>
                <select className={INPUT} value={createForm.start_time} onChange={(e) => setCreateForm({ ...createForm, start_time: e.target.value, hours: 1 })}>
                  {(grid?.courts.find((c) => c.court_id === createForm.court_id)?.slots || [])
                    .filter((s) => s.is_available && !s.is_held)
                    .map((s) => <option key={s.start_time} value={s.start_time.slice(0, 5)}>{s.start_time.slice(0, 5)}</option>)}
                </select>
              </div>
              <div>
                <label className={LABEL}>Số giờ</label>
                <select className={INPUT} value={createForm.hours} onChange={(e) => setCreateForm({ ...createForm, hours: Number(e.target.value) })}>
                  {Array.from({ length: createInfo.maxHours }, (_, i) => i + 1).map((h) => <option key={h} value={h}>{h} giờ (đến {addHours(createForm.start_time, h)})</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL}>Tên khách</label>
                <input className={INPUT} maxLength={120} value={createForm.customer_name} onChange={(e) => setCreateForm({ ...createForm, customer_name: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Số điện thoại</label>
                <input className={INPUT} type="tel" maxLength={20} value={createForm.customer_phone} onChange={(e) => setCreateForm({ ...createForm, customer_phone: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL}>Tổng tiền thỏa thuận (để trống = theo bảng giá {formatVND(createInfo.listPrice)})</label>
                <input className={INPUT} type="number" min={0} step={1000} value={createForm.price} onChange={(e) => setCreateForm({ ...createForm, price: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Thanh toán</label>
                <select className={INPUT} value={createForm.payment} onChange={(e) => setCreateForm({ ...createForm, payment: e.target.value as CreateForm["payment"] })}>
                  {PAYMENT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
            {date === today && (
              <label className="flex items-center gap-2 text-xs font-bold text-[#17253d] cursor-pointer">
                <input type="checkbox" checked={createForm.walkin} onChange={(e) => setCreateForm({ ...createForm, walkin: e.target.checked })} />
                Khách vào sân ngay (ghi nhận đã nhận sân)
              </label>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className={SECONDARY} onClick={() => setCreateForm(null)}>Đóng</button>
              <button type="submit" disabled={busy} className={PRIMARY}>{busy ? "Đang tạo..." : "Tạo đơn"}</button>
            </div>
          </form>
        </Modal>
      )}

      {detail && (
        <BookingDetailModal
          key={detail.id}
          booking={detail}
          venue={venue}
          busy={busy}
          simulatorEnabled={simulatorEnabled}
          act={act}
          onClose={() => setDetailId(null)}
        />
      )}

      {scanning && <QrScanner onDetected={openByCode} onClose={() => setScanning(false)} />}
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-3 h-3 rounded border inline-block ${className}`} />
      {label}
    </span>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 bg-[#081b34]/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-xl border border-[#e8edf3] my-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-black text-[#17253d] m-0">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Đóng" className="w-8 h-8 rounded-lg hover:bg-[#f1f4fb] text-[#718096] cursor-pointer">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Line({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-xs">
      <span className="text-[#718096]">{label}</span>
      <span className="font-bold text-[#17253d] text-right">{value}</span>
    </div>
  );
}

function BookingDetailModal({
  booking,
  venue,
  busy,
  simulatorEnabled,
  act,
  onClose,
}: {
  booking: Booking;
  venue: Venue;
  busy: boolean;
  simulatorEnabled: boolean;
  act: (action: () => Promise<unknown>, successMessage: string) => Promise<boolean>;
  onClose: () => void;
}) {
  const depositDue = Math.max(0, booking.deposit_amount - booking.paid_amount);
  const [amount, setAmount] = useState(String(booking.status === "PENDING" ? depositDue : booking.remaining_amount));
  const [method, setMethod] = useState<"CASH" | "BANK_TRANSFER">("CASH");
  const [reason, setReason] = useState("");
  const first = booking.details[0];
  const [move, setMove] = useState({ court_id: first?.court_id || 0, date: first?.date || "", start_time: first?.start_time.slice(0, 5) || "" });
  const [showMove, setShowMove] = useState(false);

  const path = `/bookings/${booking.id}`;
  const post = (url: string, body?: unknown) => fetchApi(url, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const put = (url: string, body: unknown) => fetchApi(url, { method: "PUT", body: JSON.stringify(body) });
  const numericAmount = Number(amount) || 0;
  const isOpen = ["PENDING", "CONFIRMED", "CHECKED_IN"].includes(booking.status);

  const cancel = () => {
    const refundNote = booking.paid_amount > 0 ? ` Khách sẽ được hoàn toàn bộ ${formatVND(booking.paid_amount)} đã trả.` : "";
    if (!window.confirm(`Cụm sân hủy đơn ${bookingCode(booking)}?${refundNote}`)) return;
    act(() => put(`${path}/status`, { status: "CANCELLED", reason: reason.trim() || null }), "Đã hủy đơn.");
  };

  return (
    <Modal title={`Đơn ${bookingCode(booking)}`} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          <span className={`px-2 py-0.5 rounded-md border text-[11px] font-bold ${bookingStatusTone(booking.status)}`}>{bookingStatusLabel(booking.status)}</span>
          <span className={`px-2 py-0.5 rounded-md border text-[11px] font-bold ${paymentStatusTone(booking.payment_status)}`}>{paymentStatusLabel(booking.payment_status)}</span>
          <span className="px-2 py-0.5 rounded-md border border-[#dde4ef] text-[11px] font-bold text-[#51627c]">{booking.source === "DESK" ? "Tạo tại quầy" : "Đặt trên web"}</span>
        </div>

        <div className="p-3 rounded-xl bg-[#fafbfe] border border-[#e8edf3] space-y-1.5">
          <Line label="Khách" value={`${booking.user_name || "—"}${booking.user_phone ? ` • ${booking.user_phone}` : ""}`} />
          {mergeSlots(booking.details).map((s, i) => (
            <Line key={i} label={i === 0 ? "Lịch" : ""} value={`${s.court_name} • ${formatDisplayDate(s.date)} • ${s.start_time} - ${s.end_time}`} />
          ))}
          <Line label="Tạo lúc" value={parseUtcDate(booking.created_at).toLocaleString("vi-VN")} />
          {booking.status === "PENDING" && booking.expires_at && (
            <Line label="Hạn thanh toán cọc" value={parseUtcDate(booking.expires_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} />
          )}
          {booking.checked_in_at && <Line label="Nhận sân lúc" value={parseUtcDate(booking.checked_in_at).toLocaleString("vi-VN")} />}
          {booking.cancel_reason && <Line label="Lý do hủy" value={booking.cancel_reason} />}
        </div>

        <div className="p-3 rounded-xl bg-[#fafbfe] border border-[#e8edf3] space-y-1.5">
          <Line label="Tổng tiền" value={formatVND(booking.total_price)} />
          <Line label="Tiền cọc (50%)" value={formatVND(booking.deposit_amount)} />
          <Line label="Đã thanh toán" value={formatVND(booking.paid_amount)} />
          <Line label="Còn lại" value={<span className={booking.remaining_amount > 0 ? "text-amber-700" : "text-emerald-700"}>{formatVND(booking.remaining_amount)}</span>} />
        </div>

        {booking.refund_status && (
          <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 space-y-1.5">
            <Line label="Hoàn tiền" value={`${formatVND(booking.refund_amount || 0)} - ${booking.refund_status === "PENDING" ? "chờ chuyển" : booking.refund_status === "COMPLETED" ? "đã chuyển" : "từ chối"}`} />
            {booking.refund_bank_account && (
              <Line label="Tài khoản khách" value={`${booking.refund_bank_account} • ${booking.refund_bank_name || ""} • ${booking.refund_account_holder || ""}`} />
            )}
            {booking.refund_reason && <p className="text-[11px] text-amber-900">{booking.refund_reason}</p>}
            {booking.refund_status === "PENDING" && (
              <button
                type="button"
                disabled={busy}
                className={PRIMARY}
                onClick={() => window.confirm(`Xác nhận ĐÃ chuyển ${formatVND(booking.refund_amount || 0)} cho khách?`) && act(() => post(`${path}/confirm-refund`, { note: null }), "Đã ghi nhận hoàn tiền.")}
              >
                Xác nhận đã chuyển hoàn
              </button>
            )}
          </div>
        )}

        {(booking.status === "PENDING" || booking.status === "CONFIRMED" || (booking.status === "CHECKED_IN" && booking.remaining_amount > 0)) && (
          <div className="p-3 rounded-xl border border-[#e8edf3] space-y-3">
            <p className="text-xs font-black text-[#17253d]">
              {booking.status === "PENDING" ? "Thu tiền cọc tại quầy" : booking.status === "CONFIRMED" ? "Khách đến nhận sân" : "Thu phần còn lại"}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL}>Số tiền thu (VNĐ)</label>
                <input className={INPUT} type="number" min={0} max={booking.remaining_amount} step={1000} value={amount} onChange={(e) => setAmount(e.target.value)} />
              </div>
              <div>
                <label className={LABEL}>Hình thức</label>
                <select className={INPUT} value={method} onChange={(e) => setMethod(e.target.value as "CASH" | "BANK_TRANSFER")}>
                  <option value="CASH">Tiền mặt</option>
                  <option value="BANK_TRANSFER">Chuyển khoản</option>
                </select>
              </div>
            </div>
            {booking.status === "CONFIRMED" ? (
              <div className="flex flex-wrap gap-2">
                <button type="button" disabled={busy} className={PRIMARY}
                  onClick={() => act(() => post(`${path}/checkin`, { collected_amount: numericAmount, payment_method: method }), "Đã check-in.")}>
                  Check-in{numericAmount > 0 ? ` & thu ${formatVND(numericAmount)}` : " (thu sau)"}
                </button>
                <p className="text-[11px] text-[#718096] self-center">Chỉ check-in được trong đúng ngày đặt sân và trước khi hết giờ.</p>
              </div>
            ) : (
              <button type="button" disabled={busy || numericAmount <= 0} className={PRIMARY}
                onClick={() => act(() => post(`${path}/collect`, { amount: numericAmount, payment_method: method }), "Đã ghi nhận khoản thu.")}>
                Ghi nhận đã thu {formatVND(numericAmount)}
              </button>
            )}
            {booking.status === "PENDING" && simulatorEnabled && booking.source === "ONLINE" && (
              <button type="button" disabled={busy} className={SECONDARY}
                onClick={() => act(() => post(`/payments/simulate-sepay/${booking.id}`), "Đã giả lập khách chuyển khoản cọc.")}>
                Giả lập khách đã chuyển khoản cọc (chỉ có ở môi trường demo)
              </button>
            )}
          </div>
        )}

        {booking.status === "CHECKED_IN" && (
          <button type="button" disabled={busy} className={SECONDARY}
            onClick={() => act(() => put(`${path}/status`, { status: "COMPLETED" }), "Đã hoàn tất đơn.")}>
            Kết thúc lượt chơi (hoàn tất đơn)
          </button>
        )}

        {(booking.status === "PENDING" || booking.status === "CONFIRMED") && (
          <div className="p-3 rounded-xl border border-[#e8edf3] space-y-3">
            <button type="button" className={SECONDARY} onClick={() => setShowMove(!showMove)}>{showMove ? "Ẩn dời lịch" : "Dời lịch"}</button>
            {showMove && (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className={LABEL}>Sân</label>
                    <select className={INPUT} value={move.court_id} onChange={(e) => setMove({ ...move, court_id: Number(e.target.value) })}>
                      {venue.courts.filter((c) => c.status === "ACTIVE").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Ngày</label>
                    <input className={INPUT} type="date" value={move.date} onChange={(e) => setMove({ ...move, date: e.target.value })} />
                  </div>
                  <div>
                    <label className={LABEL}>Giờ bắt đầu</label>
                    <input className={INPUT} type="time" value={move.start_time} onChange={(e) => setMove({ ...move, start_time: e.target.value })} />
                  </div>
                </div>
                <button type="button" disabled={busy || !move.date || !move.start_time} className={PRIMARY}
                  onClick={async () => (await act(() => put(`/bookings/staff/${booking.id}/reschedule`, { court_id: move.court_id, booking_date: move.date, start_time: move.start_time }), "Đã dời lịch. Số giờ và số tiền giữ nguyên.")) && setShowMove(false)}>
                  Xác nhận dời lịch
                </button>
              </div>
            )}
          </div>
        )}

        {isOpen && (
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <div className="flex-1 min-w-40">
              <label className={LABEL}>Lý do hủy (không bắt buộc)</label>
              <input className={INPUT} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
            <button type="button" disabled={busy} className={DANGER} onClick={cancel}>Cụm sân hủy đơn</button>
          </div>
        )}
      </div>
    </Modal>
  );
}

/** Quét mã QR trên vé của khách bằng camera (trình duyệt hỗ trợ BarcodeDetector); nếu không, nhập mã bằng tay. */
function QrScanner({ onDetected, onClose }: { onDetected: (value: string) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [cameraError, setCameraError] = useState(false);
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => {
    if (!supported) return;
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    let stopped = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const detector = new (window as any).BarcodeDetector({ formats: ["qr_code"] });

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((media) => {
        if (stopped) {
          media.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = media;
        if (videoRef.current) {
          videoRef.current.srcObject = media;
          videoRef.current.play().catch(() => undefined);
        }
        timer = setInterval(async () => {
          const video = videoRef.current;
          if (!video || video.readyState < 2) return;
          try {
            const codes = await detector.detect(video);
            if (codes[0]?.rawValue) onDetected(String(codes[0].rawValue));
          } catch {
            // khung hình chưa sẵn sàng: thử lại ở lần sau
          }
        }, 400);
      })
      .catch(() => setCameraError(true));

    return () => {
      stopped = true;
      if (timer) clearInterval(timer);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [supported, onDetected]);

  return (
    <Modal title="Quét mã QR trên vé của khách" onClose={onClose}>
      {!supported ? (
        <p className="text-xs text-[#51627c] leading-relaxed">
          Trình duyệt này chưa hỗ trợ quét QR trực tiếp (cần Chrome trên Android hoặc máy có hỗ trợ). Hãy nhập mã đơn PK2K... vào ô tìm đơn.
        </p>
      ) : cameraError ? (
        <p className="text-xs text-[#51627c]">Không mở được camera. Hãy cấp quyền camera cho trang, hoặc nhập mã đơn bằng tay.</p>
      ) : (
        <video ref={videoRef} muted playsInline className="w-full rounded-xl bg-black aspect-video object-cover" />
      )}
    </Modal>
  );
}
