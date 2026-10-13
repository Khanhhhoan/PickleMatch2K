"use client";

/** Kiểu và khung hộp thoại dùng chung trong cổng Chủ sân và cổng Nhân viên, để các màn hình nhìn như một. */
import React from "react";

export const INPUT = "w-full h-10 px-3 bg-white border border-[#dde4ef] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3]";
export const LABEL = "block text-[11px] font-bold text-[#51627c] mb-1";
export const PRIMARY = "px-4 py-2.5 bg-[#476cf3] text-white rounded-xl text-xs font-bold whitespace-nowrap hover:bg-[#3b61e8] disabled:opacity-50 transition cursor-pointer";
export const SECONDARY = "px-3 py-2 bg-[#f1f4fb] hover:bg-[#e4ebf7] border border-[#d5dfed] rounded-xl text-xs font-bold whitespace-nowrap text-[#405c94] cursor-pointer disabled:opacity-50";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 bg-[#081b34]/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-xl border border-[#e8edf3] my-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-black text-[#17253d] m-0">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Đóng" className="w-8 h-8 rounded-lg hover:bg-[#f1f4fb] text-[#718096] cursor-pointer">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Line({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-xs">
      <span className="text-[#718096]">{label}</span>
      <span className="font-bold text-[#17253d] text-right">{value}</span>
    </div>
  );
}
