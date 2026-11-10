/** Bộ chọn tháng dùng chung (doanh thu theo tháng, lịch sử kết ca): ‹ [Tháng ▾] [Năm ▾] › [Tháng này]. */
import React from "react";

export const PICKER_BUTTON =
  "h-9 min-w-9 px-2.5 bg-white hover:bg-[#f1f4fb] border border-[#d5dfed] rounded-xl text-xs font-bold text-[#405c94] whitespace-nowrap cursor-pointer disabled:opacity-40 disabled:cursor-default";
export const PICKER_SELECT =
  "h-9 pl-2.5 pr-1.5 bg-white border border-[#d5dfed] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3] cursor-pointer";

/** Tháng (YYYY-MM) cách `month` một số tháng. */
export function shiftMonth(month: string, offset: number): string {
  const [year, value] = month.split("-").map(Number);
  const moved = new Date(year, value - 1 + offset, 1);
  return `${moved.getFullYear()}-${String(moved.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * Chọn một tháng (YYYY-MM) từ tháng 1 của `firstYear` tới `thisMonth`: không chọn được tháng chưa tới.
 * `monthLabel`, `yearLabel` là nhãn đọc màn hình của hai ô chọn.
 */
export default function MonthPicker({ month, onChange, thisMonth, firstYear, monthLabel, yearLabel }: {
  month: string;
  onChange: (month: string) => void;
  thisMonth: string;
  firstYear: number;
  monthLabel: string;
  yearLabel: string;
}) {
  const thisYear = Number(thisMonth.slice(0, 4));
  const years = Array.from({ length: thisYear - firstYear + 1 }, (_, index) => thisYear - index);
  const choose = (value: string) => onChange(value > thisMonth ? thisMonth : value);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        className={PICKER_BUTTON}
        onClick={() => onChange(shiftMonth(month, -1))}
        disabled={month <= `${firstYear}-01`}
        aria-label="Tháng trước"
        title="Tháng trước"
      >
        ‹
      </button>
      <select
        className={PICKER_SELECT}
        value={Number(month.slice(5))}
        onChange={(e) => choose(`${month.slice(0, 4)}-${e.target.value.padStart(2, "0")}`)}
        aria-label={monthLabel}
      >
        {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => (
          <option key={value} value={value} disabled={`${month.slice(0, 4)}-${String(value).padStart(2, "0")}` > thisMonth}>
            Tháng {value}
          </option>
        ))}
      </select>
      <select className={PICKER_SELECT} value={month.slice(0, 4)} onChange={(e) => choose(`${e.target.value}-${month.slice(5)}`)} aria-label={yearLabel}>
        {years.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>
      <button
        type="button"
        className={PICKER_BUTTON}
        onClick={() => onChange(shiftMonth(month, 1))}
        disabled={month >= thisMonth}
        aria-label="Tháng sau"
        title="Tháng sau"
      >
        ›
      </button>
      <button type="button" className={PICKER_BUTTON} onClick={() => onChange(thisMonth)} disabled={month === thisMonth}>
        Tháng này
      </button>
    </div>
  );
}
