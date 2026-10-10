"use client";

import React from "react";

export const INPUT =
  "w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15";
export const BTN_PRIMARY =
  "px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold cursor-pointer disabled:opacity-50 transition";
export const BTN_SECONDARY =
  "px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold cursor-pointer disabled:opacity-50 transition";
export const BTN_DANGER =
  "px-3 py-1.5 text-rose-600 hover:bg-rose-50 border border-rose-200 rounded-lg text-xs font-semibold cursor-pointer disabled:opacity-50 transition";

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-white border border-slate-200 rounded-xl shadow-xs ${className}`}>{children}</div>;
}

export function Badge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`inline-block px-2 py-0.5 rounded-md border text-xs font-semibold whitespace-nowrap ${tone}`}>{children}</span>;
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="block text-xs font-bold text-slate-700 mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-slate-500 mt-1">{hint}</span>}
    </label>
  );
}

export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-40 bg-slate-900/50 flex items-center justify-center p-4 overflow-y-auto">
      <div className={`bg-white rounded-2xl shadow-xl border border-slate-200 w-full ${wide ? "max-w-2xl" : "max-w-lg"} p-6 my-auto`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-slate-900">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Đóng" className="w-8 h-8 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer">
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

export function Chips<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition ${
            value === option.value ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
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
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-500 border-b border-slate-200 bg-slate-50/60">
            {headers.map((header, index) => (
              <th key={index} className="px-4 py-2.5 font-bold whitespace-nowrap">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty && <p className="p-8 text-center text-sm text-slate-500">Không có dữ liệu.</p>}
    </Card>
  );
}

export const TD = "px-4 py-3 align-top border-b border-slate-100";
