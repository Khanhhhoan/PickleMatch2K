"use client";

import React, { useCallback, useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { fetchApi, formatVND, parseUtcDate } from "@/lib/api";
import {
  Booking,
  BookingGroup,
  CancelPreview,
  VIETNAMESE_BANKS,
  bookingCode,
  bookingGroup,
  bookingStatusLabel,
  bookingStatusTone,
  formatCountdown,
  formatDisplayDate,
  mergeSlots,
  paymentStatusLabel,
  secondsUntil,
} from "@/lib/booking";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";
import { useWebSocket } from "@/lib/use-websocket";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import SepayCheckoutModal from "@/components/SepayCheckoutModal";
import { QRCodeSVG } from "qrcode.react";

type Filter = BookingGroup | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "pending", label: "Chờ Cọc" },
  { key: "upcoming", label: "Sắp Diễn Ra" },
  { key: "completed", label: "Đã Kết Thúc" },
  { key: "cancelled", label: "Hủy / Hết Hạn" },
  { key: "all", label: "Tất Cả" },
];

const FILTER_DESCRIPTION: Record<Filter, string> = {
  pending: "Đơn đang giữ chỗ, chờ bạn chuyển khoản tiền cọc trước khi hết thời gian",
  upcoming: "Lịch đã thanh toán cọc và sẵn sàng thi đấu",
  completed: "Các lượt đặt sân đã qua giờ chơi",
  cancelled: "Đơn đã hủy hoặc hết hạn giữ chỗ, kèm tiến độ hoàn tiền",
  all: "Toàn bộ lịch đặt sân của bạn",
};

const EMPTY_MESSAGE: Record<Filter, string> = {
  pending: "Không có đơn nào đang chờ thanh toán cọc",
  upcoming: "Không có lịch đặt sân nào sắp diễn ra",
  completed: "Chưa có lượt đặt sân nào đã kết thúc",
  cancelled: "Không có đơn nào bị hủy hoặc hết hạn",
  all: "Chưa có lịch đặt sân nào trong tài khoản",
};

/** Đếm ngược tới hạn thanh toán cọc do máy chủ trả về (expires_at). */
function PendingCountdownBadge({ expiresAt, onExpired }: { expiresAt?: string | null; onExpired: () => void }) {
  const [timeLeft, setTimeLeft] = useState(() => secondsUntil(expiresAt));

  useEffect(() => {
    setTimeLeft(secondsUntil(expiresAt));
    const timer = setInterval(() => {
      const remaining = secondsUntil(expiresAt);
      setTimeLeft(remaining);
      if (remaining <= 0) {
        clearInterval(timer);
        onExpired();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [expiresAt, onExpired]);

  if (timeLeft <= 0) {
    return (
      <span className="px-3 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200">
        Hết Hạn Giữ Chỗ
      </span>
    );
  }
  return (
    <span
      className={`px-3 py-1 rounded-full text-xs font-bold inline-flex items-center gap-1.5 border ${
        timeLeft < 180 ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-amber-50 text-amber-800 border-amber-200/80"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${timeLeft < 180 ? "bg-rose-500" : "bg-amber-500"}`} />
      Chờ Cọc (Còn {formatCountdown(timeLeft)})
    </span>
  );
}

function refundLabel(booking: Booking): string | null {
  const amount = formatVND(booking.refund_amount || 0);
  if (booking.refund_status === "COMPLETED") return `Đã hoàn ${amount}`;
  if (booking.refund_status === "PENDING") return `Chờ hoàn ${amount}`;
  if (booking.refund_status === "REJECTED") return "Yêu cầu hoàn tiền bị từ chối";
  return null;
}

function PlayerBookingsContent() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { success: toastSuccess, error: toastError } = useToast();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [matches, setMatches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedIds, setExpandedIds] = useState<number[]>([]);
  const [filter, setFilter] = useState<Filter>("upcoming");
  const [checkoutBookingId, setCheckoutBookingId] = useState<number | null>(null);

  // Hộp thoại hủy đơn: số tiền hoàn do máy chủ tính theo chính sách hủy
  const [cancelTarget, setCancelTarget] = useState<Booking | null>(null);
  const [cancelPreview, setCancelPreview] = useState<CancelPreview | null>(null);
  const [refundForm, setRefundForm] = useState({ bank_account: "", bank_name: VIETNAMESE_BANKS[0], account_holder: "", reason: "" });
  const [cancelling, setCancelling] = useState(false);

  const loadMyBookings = useCallback(() => {
    Promise.all([fetchApi("/bookings/me").catch(() => []), fetchApi("/matches").catch(() => [])])
      .then(([bookingsData, matchesData]) => {
        setBookings(Array.isArray(bookingsData) ? bookingsData : []);
        setMatches(Array.isArray(matchesData) ? matchesData : []);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const tab = searchParams?.get("tab");
    if (tab && FILTERS.some((f) => f.key === tab)) setFilter(tab as Filter);
  }, [searchParams]);

  const { lastMessage } = useWebSocket("/api/v1/ws/live");
  useEffect(() => {
    if (!lastMessage) return;
    if (["BOOKING_STATUS_CHANGED", "PAYMENT_CONFIRMED", "BOOKING_RESCHEDULED", "MATCH_UPDATED", "MATCH_CREATED"].includes(lastMessage.type)) {
      loadMyBookings();
    }
  }, [lastMessage, loadMyBookings]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
      return;
    }
    if (user) loadMyBookings();
  }, [user, isLoading, router, loadMyBookings]);

  const toggleExpand = (id: number) =>
    setExpandedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));

  const openCancelModal = async (booking: Booking) => {
    try {
      const preview: CancelPreview = await fetchApi(`/bookings/${booking.id}/cancel-preview`);
      if (!preview.can_cancel) {
        toastError(preview.message);
        return;
      }
      setCancelPreview(preview);
      setRefundForm({ bank_account: "", bank_name: VIETNAMESE_BANKS[0], account_holder: "", reason: "" });
      setCancelTarget(booking);
    } catch (err: any) {
      toastError(err.message || "Không kiểm tra được điều kiện hủy đơn.");
    }
  };

  const submitCancel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cancelTarget || !cancelPreview) return;
    const needsBank = cancelPreview.refund_amount > 0;
    if (needsBank && (!refundForm.bank_account.trim() || !refundForm.account_holder.trim())) {
      toastError("Vui lòng nhập số tài khoản và tên chủ tài khoản để nhận tiền hoàn.");
      return;
    }
    setCancelling(true);
    try {
      const body = needsBank ? refundForm : { reason: refundForm.reason };
      const updated: Booking = await fetchApi(`/bookings/${cancelTarget.id}/cancel`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setBookings((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
      setCancelTarget(null);
      toastSuccess(
        updated.refund_status === "PENDING"
          ? `Đã hủy đơn. Cụm sân sẽ chuyển hoàn ${formatVND(updated.refund_amount || 0)} cho bạn.`
          : "Đã hủy đơn và trả lại khung giờ.",
      );
    } catch (err: any) {
      toastError(err.message || "Hủy đơn thất bại. Vui lòng thử lại.");
    } finally {
      setCancelling(false);
    }
  };

  const counts: Record<Filter, number> = { pending: 0, upcoming: 0, completed: 0, cancelled: 0, all: bookings.length };
  bookings.forEach((b) => (counts[bookingGroup(b)] += 1));
  const displayed = filter === "all" ? bookings : bookings.filter((b) => bookingGroup(b) === filter);

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900 selection:bg-zinc-900 selection:text-white">
      <Navbar />

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-7 sm:py-9 flex-1 w-full">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 tracking-tight">Lịch Đặt Sân Của Bạn</h1>
            <p className="text-xs sm:text-sm text-zinc-500 mt-1">
              {FILTER_DESCRIPTION[filter]} ({counts[filter]})
            </p>
          </div>
          <Link
            href="/"
            className="px-4 py-2 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white font-bold text-xs shadow-xs transition-all btn-press cursor-pointer self-start sm:self-auto"
          >
            + Đặt Thêm Sân
          </Link>
        </div>

        {counts.pending > 0 && filter !== "pending" && (
          <div className="mb-5 p-3.5 sm:p-4 rounded-2xl bg-amber-50 border border-amber-300 text-amber-950 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
            <span className="text-xs sm:text-sm font-semibold">
              Bạn có <strong>{counts.pending} đơn</strong> đang chờ thanh toán cọc. Quá hạn, khung giờ sẽ được trả lại.
            </span>
            <button
              type="button"
              onClick={() => setFilter("pending")}
              className="px-3.5 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs shadow-xs transition btn-press cursor-pointer shrink-0 self-start sm:self-auto"
            >
              Xem & Thanh Toán Cọc →
            </button>
          </div>
        )}

        <div className="flex items-center gap-2 mb-6 border-b border-zinc-200 pb-2 overflow-x-auto scrollbar-none">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`px-3 py-2 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer shrink-0 ${
                filter === key
                  ? key === "pending"
                    ? "bg-amber-600 text-white shadow-xs"
                    : "bg-zinc-900 text-white shadow-xs"
                  : key === "pending" && counts.pending > 0
                  ? "bg-amber-100 text-amber-900 border border-amber-300 hover:bg-amber-200"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 hover:text-zinc-900"
              }`}
            >
              {label} ({counts[key]})
            </button>
          ))}
        </div>

        {loading ? (
          <div className="space-y-3.5">
            {[1, 2].map((i) => (
              <div key={i} className="bg-white rounded-2xl p-5 border border-zinc-200 animate-pulse">
                <div className="h-4 bg-zinc-100 rounded w-1/3 mb-2.5" />
                <div className="h-3 bg-zinc-100 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : displayed.length === 0 ? (
          <div className="text-center py-14 bg-white rounded-2xl border border-zinc-200 p-6">
            <h3 className="font-semibold text-zinc-900 text-sm">{EMPTY_MESSAGE[filter]}</h3>
            <Link
              href="/"
              className="mt-4 inline-block px-4 py-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl text-xs font-bold btn-press shadow-xs transition"
            >
              Tìm Sân Và Đặt Lịch →
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {displayed.map((b) => {
              const slots = mergeSlots(b.details);
              const first = b.details?.[0];
              const venueName = first?.venue_name || "Cụm sân";
              const venueId = first?.venue_id;
              const group = bookingGroup(b);
              const isExpanded = expandedIds.includes(b.id);
              const match = matches.find((m: any) => m.booking_id === b.id && m.status !== "CANCELLED");
              const refund = refundLabel(b);

              return (
                <div
                  key={b.id}
                  className={`bg-white rounded-2xl sm:rounded-3xl border shadow-xs hover:shadow-md transition-all overflow-hidden ${
                    group === "pending" ? "border-amber-300 ring-1 ring-amber-200/50" : "border-zinc-200/90"
                  }`}
                >
                  <div
                    className={`px-5 py-3 sm:px-6 flex items-center justify-between gap-2 border-b ${
                      group === "pending" ? "bg-amber-50/70 border-amber-200/70" : "bg-zinc-50/90 border-zinc-200/70"
                    }`}
                  >
                    <span className="font-mono text-base sm:text-lg font-black text-zinc-950 tracking-wider select-all">
                      {bookingCode(b)}
                    </span>
                    <div className="flex items-center gap-1.5 flex-wrap justify-end">
                      {refund && (
                        <span
                          className={`px-3 py-1 rounded-full text-xs font-bold border ${
                            b.refund_status === "COMPLETED"
                              ? "bg-emerald-50 text-emerald-800 border-emerald-200/80"
                              : "bg-amber-50 text-amber-800 border-amber-200/80"
                          }`}
                        >
                          {refund}
                        </span>
                      )}
                      {b.status === "PENDING" ? (
                        <PendingCountdownBadge expiresAt={b.expires_at} onExpired={loadMyBookings} />
                      ) : (
                        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${bookingStatusTone(b.status)}`}>
                          {bookingStatusLabel(b.status)}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
                    <div className="space-y-2 min-w-0 flex-1">
                      <h3 className="font-black text-zinc-950 text-lg sm:text-xl tracking-tight leading-snug">{venueName}</h3>
                      <div className="space-y-1.5">
                        {slots.map((slot, index) => (
                          <div key={index} className="flex items-center gap-2 flex-wrap text-xs sm:text-sm">
                            <span className="px-3 py-1 rounded-xl bg-zinc-900 text-white font-bold text-xs shrink-0">
                              {slot.court_name}
                            </span>
                            <span
                              className={`font-bold px-3 py-1 rounded-xl text-xs sm:text-sm border ${
                                group === "cancelled"
                                  ? "text-zinc-500 bg-zinc-100 border-zinc-200 line-through"
                                  : group === "pending"
                                  ? "text-amber-900 bg-amber-50 border-amber-200"
                                  : group === "completed"
                                  ? "text-zinc-700 bg-zinc-100 border-zinc-200"
                                  : "text-emerald-800 bg-emerald-50 border-emerald-200/60"
                              }`}
                            >
                              {slot.start_time} - {slot.end_time}
                            </span>
                            <span className="font-bold text-zinc-800 text-xs sm:text-sm">{formatDisplayDate(slot.date)}</span>
                          </div>
                        ))}
                      </div>
                      {first?.venue_address && (
                        <p className="text-xs sm:text-sm text-zinc-500 pt-0.5 leading-relaxed">{first.venue_address}</p>
                      )}
                    </div>

                    <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center pt-3 sm:pt-0 border-t sm:border-t-0 border-zinc-100 w-full sm:w-auto justify-end flex-wrap">
                      <button
                        type="button"
                        onClick={() => toggleExpand(b.id)}
                        className={`px-3.5 py-2.5 rounded-xl border text-xs sm:text-sm font-semibold transition cursor-pointer ${
                          isExpanded ? "bg-zinc-900 border-zinc-900 text-white" : "border-zinc-200 hover:bg-zinc-100 text-zinc-700 bg-white"
                        }`}
                      >
                        {isExpanded ? "Đóng" : "Chi tiết"}
                      </button>

                      {b.status === "PENDING" && (
                        <button
                          type="button"
                          onClick={() => setCheckoutBookingId(b.id)}
                          className="px-4.5 py-2.5 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs sm:text-sm font-bold btn-press cursor-pointer shadow-xs transition"
                        >
                          Thanh Toán Cọc →
                        </button>
                      )}

                      {b.status === "CONFIRMED" &&
                        (match ? (
                          <Link
                            href="/matches?tab=my_matches"
                            className="px-4.5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs sm:text-sm font-bold btn-press cursor-pointer shadow-xs transition"
                          >
                            Xem Phòng Đấu
                          </Link>
                        ) : (
                          <Link
                            href={`/matches/create?booking_id=${b.id}`}
                            className="px-4.5 py-2.5 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs sm:text-sm font-bold btn-press cursor-pointer shadow-xs transition"
                          >
                            Mở Phòng Đấu
                          </Link>
                        ))}

                      {(b.status === "PENDING" || b.status === "CONFIRMED") && (
                        <button
                          type="button"
                          onClick={() => openCancelModal(b)}
                          className="px-3.5 py-2.5 rounded-xl border border-zinc-200 hover:border-rose-200 hover:bg-rose-50 text-zinc-500 hover:text-rose-600 text-xs sm:text-sm font-semibold transition cursor-pointer"
                        >
                          Hủy Đơn
                        </button>
                      )}

                      {venueId && group === "completed" && b.status === "COMPLETED" && (
                        <Link
                          href={`/venues/${venueId}`}
                          className="px-3.5 py-2.5 rounded-xl border border-zinc-200 hover:bg-zinc-100 text-zinc-700 text-xs sm:text-sm font-semibold transition"
                        >
                          Đánh Giá Sân
                        </Link>
                      )}

                      {venueId && (group === "completed" || group === "cancelled") && (
                        <Link
                          href={`/venues/${venueId}`}
                          className="px-4.5 py-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-white text-xs sm:text-sm font-bold btn-press cursor-pointer shadow-xs transition"
                        >
                          Đặt Lại
                        </Link>
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t border-zinc-100 bg-zinc-50/70 p-4 sm:p-5 text-xs text-zinc-600 animate-in fade-in duration-150 space-y-3.5">
                      {b.status === "CONFIRMED" && (
                        <div className="bg-white p-3 rounded-xl border border-zinc-200/70 shadow-2xs flex items-center gap-4">
                          <QRCodeSVG value={bookingCode(b)} size={92} marginSize={1} title={`Mã đơn ${bookingCode(b)}`} />
                          <div>
                            <p className="font-bold text-zinc-900 text-sm">Vé nhận sân</p>
                            <p className="mt-0.5 leading-relaxed">
                              Đưa mã QR này (hoặc đọc mã <strong className="font-mono text-zinc-900">{bookingCode(b)}</strong>) cho nhân viên
                              khi đến sân để check-in và thanh toán phần còn lại.
                            </p>
                          </div>
                        </div>
                      )}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                        <div className="bg-white p-3 rounded-xl border border-zinc-200/70 space-y-1.5 shadow-2xs">
                          <Row label="Mã đơn (đọc cho nhân viên khi nhận sân)" value={bookingCode(b)} mono />
                          <Row label="Thời gian tạo" value={parseUtcDate(b.created_at).toLocaleString("vi-VN")} />
                          {b.checked_in_at && <Row label="Nhận sân lúc" value={parseUtcDate(b.checked_in_at).toLocaleString("vi-VN")} />}
                          {b.cancelled_at && <Row label="Hủy lúc" value={parseUtcDate(b.cancelled_at).toLocaleString("vi-VN")} />}
                          {b.cancel_reason && <Row label="Lý do hủy" value={b.cancel_reason} />}
                        </div>

                        <div className="bg-white p-3 rounded-xl border border-zinc-200/70 space-y-1.5 shadow-2xs">
                          <Row label="Tổng tiền" value={formatVND(b.total_price)} />
                          <Row label="Tiền cọc (50%)" value={formatVND(b.deposit_amount)} />
                          <Row label={`Đã thanh toán (${paymentStatusLabel(b.payment_status)})`} value={formatVND(b.paid_amount)} />
                          {group !== "cancelled" && <Row label="Còn lại trả tại sân" value={formatVND(b.remaining_amount)} />}
                          {b.refund_status && (
                            <div className="pt-1.5 mt-1.5 border-t border-dashed border-zinc-200 space-y-1">
                              <Row label="Hoàn tiền" value={refund || ""} />
                              {b.refund_bank_account && (
                                <Row
                                  label="Tài khoản nhận"
                                  value={`${b.refund_bank_account} (${b.refund_bank_name || ""}) - ${b.refund_account_holder || ""}`}
                                />
                              )}
                              {b.refund_reason && <p className="text-[11px] text-zinc-500">{b.refund_reason}</p>}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>

      {cancelTarget && cancelPreview && (
        <div className="fixed inset-0 z-50 bg-zinc-950/50 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-zinc-200">
            <h3 className="font-bold text-base text-zinc-950">Hủy Đơn {bookingCode(cancelTarget)}</h3>

            <div
              className={`mt-3 p-3 rounded-xl border text-xs leading-relaxed ${
                cancelPreview.refund_amount > 0 || cancelPreview.paid_amount === 0
                  ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                  : "bg-rose-50 border-rose-200 text-rose-900"
              }`}
            >
              <p className="font-semibold">{cancelPreview.message}</p>
              <p className="mt-1.5">
                Đã thanh toán: <strong>{formatVND(cancelPreview.paid_amount)}</strong> • Được hoàn:{" "}
                <strong>{formatVND(cancelPreview.refund_amount)}</strong>
              </p>
              <p className="mt-1 text-[11px] opacity-80">
                Chính sách: hủy trước giờ chơi từ {cancelPreview.full_refund_hours} tiếng được hoàn 100%; sau mốc đó tiền
                cọc không được hoàn.
              </p>
            </div>

            <form onSubmit={submitCancel} className="mt-4 space-y-3.5">
              {cancelPreview.refund_amount > 0 && (
                <>
                  <div>
                    <label className="block text-xs font-semibold text-zinc-700 mb-1">Ngân hàng nhận tiền hoàn *</label>
                    <select
                      value={refundForm.bank_name}
                      onChange={(e) => setRefundForm({ ...refundForm, bank_name: e.target.value })}
                      className="w-full px-3 py-2 border border-zinc-200 rounded-xl text-xs bg-white text-zinc-900 font-medium focus:outline-none focus:border-zinc-900"
                    >
                      {VIETNAMESE_BANKS.map((bank) => (
                        <option key={bank} value={bank}>
                          {bank}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-zinc-700 mb-1">Số tài khoản *</label>
                    <input
                      type="text"
                      required
                      inputMode="numeric"
                      value={refundForm.bank_account}
                      onChange={(e) => setRefundForm({ ...refundForm, bank_account: e.target.value })}
                      className="w-full px-3 py-2 border border-zinc-200 rounded-xl text-xs text-zinc-900 font-mono font-medium focus:outline-none focus:border-zinc-900"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-zinc-700 mb-1">Tên chủ tài khoản (in hoa không dấu) *</label>
                    <input
                      type="text"
                      required
                      value={refundForm.account_holder}
                      onChange={(e) => setRefundForm({ ...refundForm, account_holder: e.target.value.toUpperCase() })}
                      className="w-full px-3 py-2 border border-zinc-200 rounded-xl text-xs text-zinc-900 font-medium uppercase focus:outline-none focus:border-zinc-900"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-xs font-semibold text-zinc-700 mb-1">Lý do hủy (không bắt buộc)</label>
                <input
                  type="text"
                  maxLength={300}
                  value={refundForm.reason}
                  onChange={(e) => setRefundForm({ ...refundForm, reason: e.target.value })}
                  className="w-full px-3 py-2 border border-zinc-200 rounded-xl text-xs text-zinc-900 font-medium focus:outline-none focus:border-zinc-900"
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  disabled={cancelling}
                  onClick={() => setCancelTarget(null)}
                  className="flex-1 py-2 rounded-xl bg-zinc-100 hover:bg-zinc-200 text-zinc-700 text-xs font-semibold transition cursor-pointer"
                >
                  Giữ Lại Đơn
                </button>
                <button
                  type="submit"
                  disabled={cancelling}
                  className="flex-1 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition cursor-pointer shadow-xs disabled:opacity-50"
                >
                  {cancelling ? "Đang hủy..." : "Xác Nhận Hủy Đơn"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {checkoutBookingId && (
        <SepayCheckoutModal
          bookingId={checkoutBookingId}
          isOpen={!!checkoutBookingId}
          onClose={(wasPaid) => {
            setCheckoutBookingId(null);
            loadMyBookings();
            if (wasPaid) setFilter("upcoming");
          }}
          onPaymentSuccess={loadMyBookings}
        />
      )}

      <Footer />
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-start gap-3">
      <span className="text-zinc-500">{label}:</span>
      <span className={`text-right text-zinc-900 ${mono ? "font-mono font-bold" : "font-semibold"}`}>{value}</span>
    </div>
  );
}

export default function PlayerBookingsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-zinc-50">
          <div className="w-8 h-8 border-3 border-zinc-900 border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <PlayerBookingsContent />
    </Suspense>
  );
}
