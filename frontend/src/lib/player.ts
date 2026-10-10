/**
 * Các giá trị hồ sơ người chơi dùng cho gợi ý sân và mô hình ghép cặp.
 * Phải khớp với backend (app/ml/features.py): PLAY_STYLES, PURPOSES, DAYS x PERIODS.
 */

export const PLAY_STYLES: { value: string; label: string; short: string }[] = [
  { value: "Offensive", label: "Tấn công (Power / Smash)", short: "Tấn công" },
  { value: "Defensive", label: "Phòng thủ (Reset / Defense)", short: "Phòng thủ" },
  { value: "All-Round", label: "Toàn diện (All-Round)", short: "Toàn diện" },
  { value: "Serve & Volley", label: "Giao bóng & Bắt lưới (Serve & Volley)", short: "Giao & Lưới" },
  { value: "Dinking & Control", label: "Kiểm soát & Bỏ nhỏ (Dinking & Control)", short: "Kiểm soát" },
];

export const PURPOSES: { value: string; label: string }[] = [
  { value: "recreational", label: "Giao lưu vui vẻ" },
  { value: "practice", label: "Luyện tập kỹ thuật" },
  { value: "competitive", label: "Thi đấu tính điểm" },
];

export const AVAILABILITY_DAYS: { value: string; label: string }[] = [
  { value: "mon", label: "T2" },
  { value: "tue", label: "T3" },
  { value: "wed", label: "T4" },
  { value: "thu", label: "T5" },
  { value: "fri", label: "T6" },
  { value: "sat", label: "T7" },
  { value: "sun", label: "CN" },
];

export const AVAILABILITY_PERIODS: { value: string; label: string }[] = [
  { value: "morning", label: "Sáng" },
  { value: "afternoon", label: "Chiều" },
  { value: "evening", label: "Tối" },
];

export const SKILL_LEVELS: { value: string; label: string }[] = [
  { value: "2.0", label: "2.0 - Mới tập chơi" },
  { value: "2.5", label: "2.5 - Đã biết luật cơ bản" },
  { value: "3.0", label: "3.0 - Đánh ổn định" },
  { value: "3.5", label: "3.5 - Điều bóng tốt, có chiến thuật" },
  { value: "4.0", label: "4.0 - Trình độ cao" },
  { value: "4.5", label: "4.5 - Bán chuyên" },
  { value: "5.0", label: "5.0 - Chuyên nghiệp" },
  { value: "5.5", label: "5.5+" },
];

/** Tên hiển thị của các trường hồ sơ mà mô hình ghép cặp báo còn thiếu. */
export const PROFILE_FIELD_LABEL: Record<string, string> = {
  skill_level: "trình độ",
  location: "vị trí",
  availability: "khung giờ rảnh",
  purpose: "mục đích chơi",
  play_style: "lối đánh",
};

const LEGACY_STYLE_KEYWORDS: [string, string][] = [
  ["toàn diện", "All-Round"],
  ["all-round", "All-Round"],
  ["all-around", "All-Round"],
  ["giao bóng", "Serve & Volley"],
  ["serve", "Serve & Volley"],
  ["dinking", "Dinking & Control"],
  ["kiểm soát", "Dinking & Control"],
  ["phòng thủ", "Defensive"],
  ["defensive", "Defensive"],
  ["tấn công", "Offensive"],
  ["offensive", "Offensive"],
];

/** Đưa nhãn lối đánh cũ về giá trị chuẩn; chuỗi rỗng nếu chưa khai hoặc không nhận ra. */
export function canonicalPlayStyle(value?: string | null): string {
  if (!value) return "";
  const lowered = value.trim().toLowerCase();
  const found = LEGACY_STYLE_KEYWORDS.find(([keyword]) => lowered.includes(keyword));
  return found ? found[1] : "";
}

export function playStyleLabel(value?: string | null, short = false): string {
  const style = PLAY_STYLES.find((item) => item.value === canonicalPlayStyle(value));
  if (!style) return "Chưa khai";
  return short ? style.short : style.label;
}

export function purposeLabel(value?: string | null): string {
  return PURPOSES.find((item) => item.value === value)?.label || "Chưa khai";
}
