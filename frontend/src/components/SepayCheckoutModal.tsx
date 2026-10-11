"use client";

import React, { useCallback, useEffect, useState } from "react";
import { fetchApi, formatVND } from "@/lib/api";
import { formatCountdown } from "@/lib/booking";
import { useWebSocket } from "@/lib/use-websocket";
import { useToast } from "@/components/Toast";

interface SepayCheckoutModalProps {
  bookingId: number;
  isOpen: boolean;
  onClose: (wasPaid?: boolean) => void;
  onPaymentSuccess?: () => void;
}

interface CheckoutInfo {
  booking_id: number;
  booking_code?: string | null;
  status: string;
  total_price: number;
  deposit_amount: number;
  paid_amount: number;
  amount_due: number;
  remaining_amount: number;
  payment_status: string;
  venue_name: string;
  bank_name: string;
  bank_code: string;
  bank_account_number: string;
  account_holder_name: string;
  transfer_content: string;
  qr_code_url: string;
  expires_in_seconds: number;
  simulator_enabled: boolean;
}

const POLL_INTERVAL_MS = 5000;

export default function SepayCheckoutModal({
  bookingId,
  isOpen,
  onClose,
  onPaymentSuccess,
}: SepayCheckoutModalProps) {
  const { error: toastError } = useToast();
  const [checkout, setCheckout] = useState<CheckoutInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [timeLeft, setTimeLeft] = useState(0);
  const [notified, setNotified] = useState(false);

  // Kênh công khai chỉ báo "đơn X vừa đổi trạng thái"; số liệu luôn được tải lại qua API có xác thực
  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  const loadCheckout = useCallback(async () => {
    try {
      const data: CheckoutInfo = await fetchApi(`/payments/checkout/${bookingId}`);
      setCheckout(data);
      setTimeLeft(data.expires_in_seconds || 0);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Không tải được thông tin thanh toán.");
    } finally {
      setLoading(false);
    }
  }, [bookingId]);

  const status = checkout?.status;
  const isPaid = status === "CONFIRMED" || status === "CHECKED_IN" || status === "COMPLETED";
  const isWaiting = status === "PENDING" && timeLeft > 0;
  const isClosed = !!checkout && !isPaid && !isWaiting; // hết hạn hoặc đã hủy

  useEffect(() => {
    if (!isOpen || !bookingId) return;
    setLoading(true);
    setCheckout(null);
    setNotified(false);
    loadCheckout();
  }, [isOpen, bookingId, loadCheckout]);

  // Đếm ngược theo hạn thanh toán do máy chủ trả về
  useEffect(() => {
    if (!isOpen || !isWaiting) return;
    const timer = setInterval(() => setTimeLeft((prev) => Math.max(0, prev - 1)), 1000);
    return () => clearInterval(timer);
  }, [isOpen, isWaiting]);

  // Tải lại khi có sự kiện của đơn này, và định kỳ phòng khi mất kết nối WebSocket
  useEffect(() => {
    if (!lastMessage || Number(lastMessage.booking_id) !== bookingId) return;
    loadCheckout();
  }, [lastMessage, bookingId, loadCheckout]);

  useEffect(() => {
    if (!isOpen || !isWaiting) return;
    const poll = setInterval(loadCheckout, POLL_INTERVAL_MS);
    return () => clearInterval(poll);
  }, [isOpen, isWaiting, loadCheckout]);

  useEffect(() => {
    if (isPaid && !notified) {
      setNotified(true);
      onPaymentSuccess?.();
    }
  }, [isPaid, notified, onPaymentSuccess]);

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleSimulatePayment = async () => {
    setSimulating(true);
    try {
      await fetchApi(`/payments/simulate-sepay/${bookingId}`, { method: "POST" });
      await loadCheckout();
    } catch (err) {
      toastError("Không giả lập được thanh toán: " + (err instanceof Error ? err.message : ""));
    } finally {
      setSimulating(false);
    }
  };

  if (!isOpen) return null;

  const code = checkout?.booking_code || `#${bookingId}`;
  const amountDue = checkout?.amount_due ?? 0;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-zinc-950/40 backdrop-blur-xs p-4 overflow-y-auto font-sans">
      <div className="bg-white w-full max-w-md my-auto rounded-2xl shadow-xl border border-zinc-200/80 overflow-hidden relative animate-in fade-in duration-150">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-zinc-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-zinc-900 mb-0.5">Thanh Toán Cọc Qua VietQR</h3>
            <p className="text-[11px] text-zinc-500 font-normal">
              Mã đơn: <strong className="text-zinc-900 font-mono font-semibold">{code}</strong>
              {checkout?.venue_name ? ` • ${checkout.venue_name}` : ""}
            </p>
          </div>
          <button
            onClick={() => onClose(isPaid)}
            aria-label="Đóng"
            className="w-7 h-7 rounded-lg hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700 flex items-center justify-center text-sm transition cursor-pointer"
          >
            ✕
          </button>
        </div>

        {loading ? (
          <div className="p-10 text-center">
            <div className="w-6 h-6 border-2 border-zinc-300 border-t-zinc-900 rounded-full animate-spin mx-auto mb-2.5" />
            <p className="text-xs text-zinc-500">Đang tải thông tin thanh toán...</p>
          </div>
        ) : loadError || !checkout ? (
          <div className="p-6 text-center space-y-3">
            <p className="text-sm font-semibold text-zinc-900">Chưa thể thanh toán đơn này</p>
            <p className="text-xs text-zinc-600 leading-relaxed">{loadError}</p>
            <button
              onClick={() => onClose(false)}
              className="w-full py-2.5 bg-zinc-100 hover:bg-zinc-200 text-zinc-800 rounded-xl font-medium text-xs transition cursor-pointer"
            >
              Đóng
            </button>
          </div>
        ) : isPaid ? (
          <div className="p-6 text-center space-y-4">
            <div className="w-12 h-12 bg-emerald-50 text-emerald-600 rounded-full flex items-center justify-center text-2xl mx-auto font-bold border border-emerald-200">
              ✓
            </div>
            <div>
              <h2 className="text-lg font-bold text-zinc-900">Đã Xác Nhận Giữ Sân</h2>
              <p className="text-xs text-zinc-500 mt-0.5">Hệ thống đã ghi nhận khoản chuyển của bạn cho đơn {code}.</p>
            </div>

            <div className="p-4 rounded-xl bg-zinc-50 border border-zinc-200/80 text-left space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-zinc-500">Cụm sân:</span>
                <span className="font-semibold text-zinc-900">{checkout.venue_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Tổng tiền:</span>
                <span className="font-medium text-zinc-800">{formatVND(checkout.total_price)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Đã thanh toán:</span>
                <span className="font-bold text-emerald-600">{formatVND(checkout.paid_amount)}</span>
              </div>
              <div className="flex justify-between pt-1 border-t border-zinc-200">
                <span className="text-zinc-500">Còn lại trả tại sân:</span>
                <span className="font-semibold text-zinc-900">
                  {formatVND(Math.max(0, checkout.total_price - checkout.paid_amount))}
                </span>
              </div>
            </div>

            <button
              onClick={() => onClose(true)}
              className="w-full py-2.5 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl font-medium text-xs transition btn-press cursor-pointer"
            >
              Xem Lịch Đặt Của Tôi
            </button>
          </div>
        ) : isClosed ? (
          <div className="p-6 text-center space-y-3">
            <p className="text-sm font-semibold text-zinc-900">
              {status === "CANCELLED" ? "Đơn đã bị hủy" : "Đơn đã hết hạn giữ chỗ"}
            </p>
            <p className="text-xs text-zinc-600 leading-relaxed">
              Khung giờ đã được trả lại cho người khác đặt. Nếu bạn đã chuyển khoản sau khi hết hạn, cụm sân sẽ
              hoàn lại số tiền đó cho bạn.
            </p>
            {checkout.paid_amount > 0 && (
              <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2">
                Đã ghi nhận {formatVND(checkout.paid_amount)} cho đơn này - đang chờ cụm sân hoàn tiền.
              </p>
            )}
            <button
              onClick={() => onClose(false)}
              className="w-full py-2.5 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl font-medium text-xs transition cursor-pointer"
            >
              Đóng
            </button>
          </div>
        ) : (
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between bg-zinc-50 border border-zinc-200 px-3 py-1.5 rounded-lg text-xs">
              <div className="flex items-center gap-2 text-zinc-700">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[11px] font-medium">Giữ chỗ tới khi hết thời gian</span>
              </div>
              <div className={`font-mono text-xs font-semibold ${timeLeft < 180 ? "text-rose-600" : "text-zinc-800"}`}>
                {formatCountdown(timeLeft)}
              </div>
            </div>

            {checkout.paid_amount > 0 && (
              <p className="text-[11px] text-amber-900 bg-amber-50 border border-amber-200 rounded-lg p-2 leading-relaxed">
                Đã nhận {formatVND(checkout.paid_amount)}. Vui lòng chuyển thêm{" "}
                <strong>{formatVND(amountDue)}</strong> để đủ tiền cọc.
              </p>
            )}

            <div className="flex flex-col sm:flex-row items-center gap-3.5">
              <div className="p-2 bg-white border border-zinc-200 rounded-xl text-center shrink-0">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={checkout.qr_code_url} alt="Mã VietQR chuyển khoản cọc" className="w-36 h-36 object-contain rounded-lg" />
                <p className="text-[9px] text-zinc-500 font-medium mt-1">Quét bằng ứng dụng ngân hàng</p>
              </div>

              <div className="flex-1 w-full space-y-1.5 text-xs">
                <div className="p-2 rounded-lg bg-zinc-50 border border-zinc-100">
                  <p className="text-[9px] text-zinc-400">Chủ tài khoản</p>
                  <p className="font-medium text-zinc-900 text-xs truncate">{checkout.account_holder_name || "—"}</p>
                </div>

                <div className="p-2 rounded-lg bg-zinc-50 border border-zinc-100">
                  <p className="text-[9px] text-zinc-400">Ngân hàng</p>
                  <p className="font-medium text-zinc-900 text-xs">
                    {checkout.bank_name} ({checkout.bank_code})
                  </p>
                </div>

                <CopyRow
                  label="Số tài khoản"
                  value={checkout.bank_account_number}
                  copied={copiedField === "acc"}
                  onCopy={() => copyToClipboard(checkout.bank_account_number, "acc")}
                />
                <CopyRow
                  label={`Số tiền cần chuyển (cọc ${formatVND(checkout.deposit_amount)})`}
                  value={formatVND(amountDue)}
                  highlight
                  copied={copiedField === "amount"}
                  onCopy={() => copyToClipboard(String(Math.round(amountDue)), "amount")}
                />
                <CopyRow
                  label="Nội dung chuyển khoản (ghi đúng mã đơn)"
                  value={checkout.transfer_content}
                  copied={copiedField === "content"}
                  onCopy={() => copyToClipboard(checkout.transfer_content, "content")}
                />
              </div>
            </div>

            <p className="text-[11px] text-zinc-500 leading-relaxed">
              Sau khi chuyển khoản, đơn tự chuyển sang “Đã xác nhận” khi ngân hàng báo có. Phần còn lại{" "}
              {formatVND(checkout.remaining_amount)} thanh toán tại sân.
            </p>

            <div className="pt-2 border-t border-zinc-100 flex flex-col gap-2">
              {checkout.simulator_enabled && (
                <button
                  type="button"
                  onClick={handleSimulatePayment}
                  disabled={simulating}
                  className="w-full py-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50 btn-press"
                >
                  {simulating ? "Đang giả lập..." : "Giả lập đã chuyển khoản (chỉ có ở môi trường demo)"}
                </button>
              )}
              <button
                type="button"
                onClick={() => onClose(false)}
                className="w-full py-1.5 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 rounded-lg text-xs font-semibold transition cursor-pointer text-center"
              >
                Để sau (đơn được giữ tới khi hết thời gian)
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CopyRow({
  label,
  value,
  copied,
  onCopy,
  highlight = false,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
  highlight?: boolean;
}) {
  return (
    <div
      className={`p-2 rounded-lg flex items-center justify-between gap-2 border ${
        highlight ? "bg-emerald-50/60 border-emerald-200/80" : "bg-zinc-50 border-zinc-100"
      }`}
    >
      <div className="min-w-0">
        <p className={`text-[9px] ${highlight ? "text-emerald-800 font-semibold" : "text-zinc-400"}`}>{label}</p>
        <p className="font-mono font-bold text-zinc-900 text-xs truncate">{value}</p>
      </div>
      <button
        type="button"
        onClick={onCopy}
        className="px-2 py-0.5 bg-white hover:bg-zinc-100 text-zinc-700 rounded border border-zinc-200 text-[10px] transition cursor-pointer shrink-0"
      >
        {copied ? "Đã chép" : "Sao chép"}
      </button>
    </div>
  );
}
