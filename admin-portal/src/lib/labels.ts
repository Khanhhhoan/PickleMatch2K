export const ROLE_LABEL: Record<string, string> = {
  PLAYER: "Người chơi",
  OWNER: "Chủ sân",
  STAFF: "Nhân viên",
  ADMIN: "Quản trị viên",
};

export const VENUE_STATUS_LABEL: Record<string, string> = {
  PENDING: "Chờ duyệt",
  ACTIVE: "Đang hoạt động",
  MAINTENANCE: "Tạm đóng bảo trì",
  INACTIVE: "Ngừng hiển thị",
  REJECTED: "Đã từ chối",
};

export const BOOKING_STATUS_LABEL: Record<string, string> = {
  PENDING: "Chờ thanh toán cọc",
  CONFIRMED: "Đã xác nhận",
  CHECKED_IN: "Đã nhận sân",
  COMPLETED: "Đã hoàn thành",
  NO_SHOW: "Không đến sân",
  CANCELLED: "Đã hủy",
  EXPIRED: "Hết hạn giữ chỗ",
};

export const PAYMENT_STATUS_LABEL: Record<string, string> = {
  UNPAID: "Chưa thanh toán",
  PARTIALLY_PAID: "Chuyển chưa đủ cọc",
  DEPOSIT_PAID: "Đã cọc",
  FULLY_PAID: "Đã thanh toán đủ",
};

export const MATCH_STATUS_LABEL: Record<string, string> = {
  OPEN: "Đang tuyển",
  FULL: "Đã đủ người",
  CANCELLED: "Đã hủy",
  COMPLETED: "Đã kết thúc",
};

export const KIND_LABEL: Record<string, string> = { DEPOSIT: "Tiền cọc / trả trước", BALANCE: "Thu tại sân", REFUND: "Hoàn tiền" };
export const METHOD_LABEL: Record<string, string> = { BANK_TRANSFER: "Chuyển khoản", CASH: "Tiền mặt" };
export const PURPOSE_LABEL: Record<string, string> = { recreational: "Giao lưu", practice: "Luyện tập", competitive: "Thi đấu" };

/** Màu nhãn theo ý nghĩa trạng thái (tốt / đang chờ / kết thúc / xấu). */
const TONE = {
  good: "bg-emerald-50 text-emerald-800 border-emerald-200",
  wait: "bg-amber-50 text-amber-800 border-amber-200",
  info: "bg-sky-50 text-sky-800 border-sky-200",
  done: "bg-[#eef1f6] text-[#51627c] border-[#dde4ef]",
  bad: "bg-rose-50 text-rose-700 border-rose-200",
};

const STATUS_TONE: Record<string, string> = {
  ACTIVE: TONE.good, CONFIRMED: TONE.good, FULLY_PAID: TONE.good, OPEN: TONE.good,
  PENDING: TONE.wait, PARTIALLY_PAID: TONE.wait, MAINTENANCE: TONE.wait,
  CHECKED_IN: TONE.info, DEPOSIT_PAID: TONE.info, FULL: TONE.info,
  COMPLETED: TONE.done, INACTIVE: TONE.done, UNPAID: TONE.done, CANCELLED: TONE.done, EXPIRED: TONE.done,
  NO_SHOW: TONE.bad, REJECTED: TONE.bad,
};

export function statusTone(status: string | null | undefined): string {
  return STATUS_TONE[status || ""] || TONE.done;
}

export function userDisplayName(user: {
  email: string;
  player_profile?: { full_name?: string | null } | null;
  owner_profile?: { full_name?: string | null } | null;
  staff_profile?: { full_name?: string | null } | null;
}): string {
  return user.player_profile?.full_name || user.owner_profile?.full_name || user.staff_profile?.full_name || user.email.split("@")[0];
}

export function userPhone(user: {
  player_profile?: { phone?: string | null } | null;
  owner_profile?: { phone?: string | null } | null;
  staff_profile?: { phone?: string | null } | null;
}): string {
  return user.player_profile?.phone || user.owner_profile?.phone || user.staff_profile?.phone || "";
}
