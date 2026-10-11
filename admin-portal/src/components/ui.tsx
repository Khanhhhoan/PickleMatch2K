"use client";

import React from "react";

// Kiểu dáng dùng chung với khu vực chủ sân của ứng dụng chính: cùng bảng màu, bo góc và cỡ chữ
export const INPUT =
  "w-full min-h-10 px-3 py-2 bg-white border border-[#dde4ef] rounded-xl text-xs font-bold text-[#263b53] placeholder-[#9aa7bb] outline-none focus:border-[#476cf3]";
export const BTN_PRIMARY =
  "px-4 py-2.5 bg-[#476cf3] hover:bg-[#3b61e8] text-white rounded-xl text-xs font-bold whitespace-nowrap cursor-pointer disabled:opacity-50 transition";
export const BTN_SECONDARY =
  "px-3 py-2 bg-[#f1f4fb] hover:bg-[#e4ebf7] border border-[#d5dfed] text-[#405c94] rounded-xl text-xs font-bold whitespace-nowrap cursor-pointer disabled:opacity-50 transition";
export const BTN_DANGER =
  "px-3 py-2 text-rose-600 hover:bg-rose-50 border border-rose-200 rounded-xl text-xs font-bold whitespace-nowrap cursor-pointer disabled:opacity-50 transition";

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-white rounded-2xl border border-[#e8edf3] shadow-[0_12px_35px_rgba(29,51,87,0.035)] ${className}`}>{children}</div>;
}

export function Badge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`inline-block px-2 py-0.5 rounded-md border text-[11px] font-bold whitespace-nowrap ${tone}`}>{children}</span>;
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-bold text-[#51627c] mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-[#8a97ab] mt-1">{hint}</span>}
    </label>
  );
}

export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 bg-[#081b34]/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
      <div className={`bg-white rounded-2xl shadow-xl border border-[#e8edf3] w-full ${wide ? "max-w-2xl" : "max-w-lg"} p-6 my-auto`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-black text-[#17253d]">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Đóng" className="w-8 h-8 rounded-lg hover:bg-[#f1f4fb] text-[#718096] cursor-pointer">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Toolbar({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center justify-between gap-3">{children}</div>;
}

/** Bộ lọc dạng nút gạt, giống thanh thẻ của khu vực chủ sân. */
export function Chips<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return (
    <div className="inline-flex flex-wrap p-1 rounded-xl bg-white border border-[#e3e9f3]">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap cursor-pointer transition ${
            value === option.value ? "bg-[#476cf3] text-white shadow-sm" : "text-[#51627c] hover:text-[#17253d]"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Bảng dữ liệu đơn giản có tiêu đề cột và trạng thái rỗng. */
export function DataTable({ headers, children, empty }: { headers: string[]; children: React.ReactNode; empty: boolean }) {
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[11px] text-[#8a97ab] border-b border-[#eef1f6]">
            {headers.map((header, index) => (
              <th key={index} className="px-5 py-3 font-bold whitespace-nowrap">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty && <p className="p-10 text-center text-xs text-[#8a97ab]">Không có dữ liệu.</p>}
    </Card>
  );
}

export const TD = "px-5 py-3 align-top border-b border-[#f3f5f9]";
