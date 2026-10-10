/**
 * Kiểu dữ liệu và hàm hiển thị dùng chung cho đơn đặt sân ở cả ba cổng (người chơi, chủ sân, nhân viên).
 * Trạng thái luôn lấy trực tiếp từ máy chủ; giao diện không tự suy đoán từ thời gian tạo đơn hay số tiền.
 */
import { parseUtcDate } from "@/lib/api";

export type BookingStatus = "PENDING" | "CONFIRMED" | "CHECKED_IN" | "COMPLETED" | "NO_SHOW" | "CANCELLED" | "EXPIRED";
export type PaymentStatus = "UNPAID" | "PARTIALLY_PAID" | "DEPOSIT_PAID" | "FULLY_PAID";
export type BookingGroup = "pending" | "upcoming" | "completed" | "cancelled";

export interface BookingDetail {
  id: number;
  court_id: number;
  date: string;
  start_time: string;
  end_time: string;
  price: number;
  is_active: boolean;
  court_name?: string | null;
  venue_id?: number | null;
  venue_name?: string | null;
  venue_address?: string | null;
}

export interface Booking {
  id: number;
  booking_code?: string | null;
  user_id: number;
  source: "ONLINE" | "DESK";
  total_price: number;
  deposit_amount: number;
  paid_amount: number;
  remaining_amount: number;
  status: BookingStatus;
  payment_status: PaymentStatus;
  expires_at?: string | null;
  checked_in_at?: string | null;
  cancelled_at?: string | null;
  cancel_reason?: string | null;
  refund_status?: "PENDING" | "COMPLETED" | "REJECTED" | null;
  refund_amount?: number | null;
  refund_bank_account?: string | null;
  refund_bank_name?: string | null;
  refund_account_holder?: string | null;
  refund_reason?: string | null;
  refunded_at?: string | null;
  created_at: string;
  details: BookingDetail[];
  user_name?: string | null;
  user_phone?: string | null;
  user_email?: string | null;
}

export interface CancelPreview {
  booking_id: number;
  can_cancel: boolean;
  tier: "UNPAID" | "FULL_REFUND" | "RESCHEDULE_ONLY" | "NO_REFUND" | "NOT_ALLOWED";
  hours_before: number;
  paid_amount: number;
  refund_amount: number;
  full_refund_hours: number;
  reschedule_hours: number;
  message: string;
}

export const BOOKING_STATUS_LABEL: Record<BookingStatus, string> = {
  PENDING: "Chờ thanh toán cọc",
  CONFIRMED: "Đã xác nhận",
  CHECKED_IN: "Đã nhận sân",
  COMPLETED: "Đã hoàn thành",
  NO_SHOW: "Không đến sân",
  CANCELLED: "Đã hủy",
  EXPIRED: "Hết hạn giữ chỗ",
};

/** Lớp Tailwind cho nhãn trạng thái (nền + chữ + viền). */
export const BOOKING_STATUS_TONE: Record<BookingStatus, string> = {
  PENDING: "bg-amber-50 text-amber-800 border-amber-200",
  CONFIRMED: "bg-emerald-50 text-emerald-800 border-emerald-200",
  CHECKED_IN: "bg-sky-50 text-sky-800 border-sky-200",
  COMPLETED: "bg-purple-50 text-purple-700 border-purple-200",
  NO_SHOW: "bg-rose-50 text-rose-700 border-rose-200",
  CANCELLED: "bg-zinc-100 text-zinc-600 border-zinc-200",
  EXPIRED: "bg-zinc-100 text-zinc-600 border-zinc-200",
};

export const PAYMENT_STATUS_LABEL: Record<PaymentStatus, string> = {
  UNPAID: "Chưa thanh toán",
  PARTIALLY_PAID: "Chuyển chưa đủ cọc",
  DEPOSIT_PAID: "Đã cọc",
  FULLY_PAID: "Đã thanh toán đủ",
};

export const PAYMENT_STATUS_TONE: Record<PaymentStatus, string> = {
  UNPAID: "bg-zinc-100 text-zinc-600 border-zinc-200",
  PARTIALLY_PAID: "bg-amber-50 text-amber-800 border-amber-200",
  DEPOSIT_PAID: "bg-sky-50 text-sky-800 border-sky-200",
  FULLY_PAID: "bg-emerald-50 text-emerald-800 border-emerald-200",
};

export function bookingStatusLabel(status: string): string {
  return BOOKING_STATUS_LABEL[status as BookingStatus] || status;
}

export function bookingStatusTone(status: string): string {
  return BOOKING_STATUS_TONE[status as BookingStatus] || "bg-zinc-100 text-zinc-600 border-zinc-200";
}

export function paymentStatusLabel(status: string | null | undefined): string {
  return PAYMENT_STATUS_LABEL[(status || "UNPAID") as PaymentStatus] || String(status);
}

export function paymentStatusTone(status: string | null | undefined): string {
  return PAYMENT_STATUS_TONE[(status || "UNPAID") as PaymentStatus] || PAYMENT_STATUS_TONE.UNPAID;
}

export function bookingGroup(booking: Pick<Booking, "status">): BookingGroup {
  switch (booking.status) {
    case "PENDING":
      return "pending";
    case "CONFIRMED":
    case "CHECKED_IN":
      return "upcoming";
    case "COMPLETED":
    case "NO_SHOW":
      return "completed";
    default:
      return "cancelled";
  }
}

/** Mã đơn hiển thị cho khách và dùng làm nội dung chuyển khoản. */
export function bookingCode(booking: Pick<Booking, "id" | "booking_code">): string {
  return booking.booking_code || `#${booking.id}`;
}

/** Số giây còn lại tới hạn thanh toán cọc (0 nếu đã quá hạn hoặc đơn không có hạn). */
export function secondsUntil(isoTime: string | null | undefined): number {
  if (!isoTime) return 0;
  return Math.max(0, Math.floor((parseUtcDate(isoTime).getTime() - Date.now()) / 1000));
}

export function formatCountdown(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

const WEEKDAYS = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];

/** "2026-10-12" -> "Thứ Hai, 12/10/2026" (không phụ thuộc múi giờ của trình duyệt). */
export function formatDisplayDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const [year, month, day] = dateStr.split("-").map(Number);
  if (!year || !month || !day) return dateStr;
  const weekday = WEEKDAYS[new Date(year, month - 1, day).getDay()];
  return `${weekday}, ${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`;
}

export interface MergedSlot {
  court_id: number;
  court_name: string;
  date: string;
  start_time: string;
  end_time: string;
  slots_count: number;
  price: number;
}

/** Gộp các khung 60 phút liền nhau trên cùng một sân thành một dòng hiển thị (18:00 - 20:00). */
export function mergeSlots(details: BookingDetail[] | null | undefined): MergedSlot[] {
  const sorted = [...(details || [])].sort(
    (a, b) => a.date.localeCompare(b.date) || a.court_id - b.court_id || a.start_time.localeCompare(b.start_time),
  );
  const merged: MergedSlot[] = [];
  for (const item of sorted) {
    const start = item.start_time.slice(0, 5);
    const end = item.end_time.slice(0, 5);
    const last = merged[merged.length - 1];
    if (last && last.court_id === item.court_id && last.date === item.date && last.end_time === start) {
      last.end_time = end;
      last.slots_count += 1;
      last.price += item.price || 0;
    } else {
      merged.push({
        court_id: item.court_id,
        court_name: item.court_name || `Sân #${item.court_id}`,
        date: item.date,
        start_time: start,
        end_time: end,
        slots_count: 1,
        price: item.price || 0,
      });
    }
  }
  return merged;
}

/** Tên ngân hàng dùng trong biểu mẫu nhận tiền hoàn. */
export const VIETNAMESE_BANKS = [
  "MBBank", "Vietcombank", "Techcombank", "VietinBank", "ACB", "VPBank", "TPBank", "BIDV", "Sacombank", "VIB",
];
