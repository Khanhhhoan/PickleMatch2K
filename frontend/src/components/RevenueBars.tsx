import React from "react";

export interface RevenueBar {
  key: string;         // ngày YYYY-MM-DD hoặc tháng YYYY-MM
  label: string;       // chữ dưới cột, để trống thì không hiện
  title: string;       // chú thích khi rê chuột
  amount: number;      // thực thu, có thể âm khi hoàn nhiều hơn thu
  selected?: boolean;  // kỳ đang xem chi tiết: cột tô đậm
  current?: boolean;   // hôm nay / tháng này: chữ dưới cột tô màu
  disabled?: boolean;  // kỳ chưa tới: không bấm được
}

/** Biểu đồ cột thực thu theo ngày hoặc theo tháng; bấm một cột để xem chi tiết kỳ đó. */
export default function RevenueBars({
  bars,
  onPick,
  empty,
  valueLabel,
  valuesFromSm = false,
}: {
  bars: RevenueBar[];
  onPick: (key: string) => void;
  empty: string;
  /** Số tiền ghi trên đầu cột; bỏ trống thì không ghi */
  valueLabel?: (amount: number) => string;
  /** Chỉ ghi số tiền trên đầu cột từ màn hình vừa trở lên (điện thoại không đủ chỗ) */
  valuesFromSm?: boolean;
}) {
  const max = Math.max(1, ...bars.map((bar) => Math.abs(bar.amount)));
  const dense = bars.length > 12;
  const gap = dense ? "gap-0.5 sm:gap-1" : bars.length > 7 ? "gap-1.5 sm:gap-3" : "gap-3";

  return (
    <div className="relative mt-3">
      <div className={`flex items-end ${gap} h-32 border-b border-[#e8edf3]`}>
        {bars.map((bar) => (
          <button
            key={bar.key}
            type="button"
            onClick={() => onPick(bar.key)}
            disabled={bar.disabled}
            aria-pressed={bar.selected}
            title={bar.title}
            className="group flex-1 min-w-0 flex flex-col items-center justify-end h-full gap-1.5 cursor-pointer disabled:cursor-default"
          >
            {valueLabel && (
              <span className={`text-[10px] font-bold text-[#51627c] whitespace-nowrap ${valuesFromSm ? "hidden sm:inline" : ""}`}>
                {bar.amount !== 0 ? valueLabel(bar.amount) : ""}
              </span>
            )}
            <div
              className={`w-full ${dense ? "rounded-t-sm" : "max-w-14 rounded-t-lg"} transition ${
                bar.amount < 0
                  ? "bg-rose-300"
                  : bar.selected
                    ? "bg-[#476cf3]"
                    : bar.disabled
                      ? "bg-[#e8edf3]"
                      : "bg-[#c7d3f6] group-hover:bg-[#a9bbef]"
              }`}
              style={{ height: bar.amount === 0 ? "3px" : `${Math.max(6, (Math.abs(bar.amount) / max) * 100)}%` }}
            />
          </button>
        ))}
      </div>
      <div className={`flex ${gap} mt-1.5`}>
        {bars.map((bar) => (
          <span key={bar.key} className="relative flex-1 min-w-0 h-3.5">
            <span
              className={`absolute left-1/2 -translate-x-1/2 text-[10px] font-bold whitespace-nowrap ${
                bar.selected || bar.current ? "text-[#476cf3]" : "text-[#718096]"
              }`}
            >
              {bar.label}
            </span>
          </span>
        ))}
      </div>
      {bars.every((bar) => bar.amount === 0) && (
        <p className="absolute inset-x-0 top-10 text-center text-xs text-[#8a97ab] pointer-events-none">{empty}</p>
      )}
    </div>
  );
}
