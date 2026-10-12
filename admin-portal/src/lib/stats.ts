import { DailyActivity } from "@/lib/types";

export type StatsUnit = "day" | "month" | "year";

export interface StatsBucket {
  key: string;
  /** Nhãn ngắn dưới cột: "13", "Th10", "2026". */
  label: string;
  /** Tên đầy đủ của cột: "13/10/2026", "Tháng 10/2026", "Năm 2026". */
  title: string;
  revenue: number;
  bookings: number;
  /** Cột của hôm nay, tháng này hoặc năm nay. */
  current: boolean;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** Các năm có thể chọn: từ năm đầu tiên có dữ liệu tới năm hiện tại, mới nhất trước. */
export function availableYears(daily: DailyActivity[], today: string): number[] {
  const currentYear = Number(today.slice(0, 4));
  const firstYear = daily.length > 0 ? Math.min(currentYear, Number(daily[0].date.slice(0, 4))) : currentYear;
  const years: number[] = [];
  for (let year = currentYear; year >= firstYear; year -= 1) years.push(year);
  return years;
}

/**
 * Gom chuỗi theo ngày thành các cột của biểu đồ: từng ngày của một tháng, từng tháng của một năm,
 * hoặc từng năm. `today` là ngày hiện tại dạng YYYY-MM-DD, dùng để đánh dấu cột hiện tại.
 */
export function buildBuckets(daily: DailyActivity[], unit: StatsUnit, year: number, month: number, today: string): StatsBucket[] {
  const keyLength = unit === "day" ? 10 : unit === "month" ? 7 : 4;
  const totals = new Map<string, { revenue: number; bookings: number }>();
  for (const day of daily) {
    const key = day.date.slice(0, keyLength);
    const total = totals.get(key) || { revenue: 0, bookings: 0 };
    total.revenue += day.revenue;
    total.bookings += day.bookings;
    totals.set(key, total);
  }
  const bucket = (key: string, label: string, title: string): StatsBucket => ({
    key,
    label,
    title,
    revenue: totals.get(key)?.revenue || 0,
    bookings: totals.get(key)?.bookings || 0,
    current: today.startsWith(key),
  });

  if (unit === "day") {
    const daysInMonth = new Date(year, month, 0).getDate();
    return Array.from({ length: daysInMonth }, (_, index) =>
      bucket(`${year}-${pad(month)}-${pad(index + 1)}`, String(index + 1), `${pad(index + 1)}/${pad(month)}/${year}`),
    );
  }
  if (unit === "month") {
    return Array.from({ length: 12 }, (_, index) => bucket(`${year}-${pad(index + 1)}`, `Th${index + 1}`, `Tháng ${index + 1}/${year}`));
  }
  return availableYears(daily, today)
    .reverse()
    .map((value) => bucket(String(value), String(value), `Năm ${value}`));
}
