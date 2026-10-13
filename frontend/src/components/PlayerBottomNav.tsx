"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function PlayerBottomNav() {
  const pathname = usePathname();
  const { user } = useAuth();

  // Don't show bottom nav in owner, staff or admin portals
  if (pathname.startsWith("/owner") || pathname.startsWith("/staff") || pathname.startsWith("/admin")) {
    return null;
  }

  const navItems = [
    {
      href: "/",
      label: "Tìm Sân",
      icon: (active: boolean) => (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.2 : 1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      ),
      isActive: pathname === "/" || pathname.startsWith("/venues"),
    },
    {
      href: "/matches",
      label: "Ghép Trận",
      badge: "AI",
      icon: (active: boolean) => (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.2 : 1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      isActive: pathname.startsWith("/matches"),
    },
    {
      href: "/bookings",
      label: "Vé Đặt Sân",
      icon: (active: boolean) => (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.2 : 1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      ),
      isActive: pathname.startsWith("/bookings"),
    },
    {
      href: user
        ? user.role === "STAFF"
          ? "/staff/dashboard"
          : user.role === "OWNER"
          ? "/owner/dashboard"
          : "/profile"
        : "/login",
      label: user
        ? user.role === "STAFF"
          ? "Ca Trực"
          : user.role === "OWNER"
          ? "Chủ Sân"
          : "Hồ Sơ"
        : "Tài Khoản",
      icon: (active: boolean) => (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.2 : 1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
      isActive:
        pathname.startsWith("/profile") ||
        pathname.startsWith("/login") ||
        pathname.startsWith("/staff") ||
        pathname.startsWith("/owner"),
    },
  ];

  return (
    <nav aria-label="Điều hướng chính" className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white/90 backdrop-blur-md border-t border-zinc-200/80 px-2 py-1">
      <div className="flex items-center justify-around">
        {navItems.map((item) => {
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`relative flex flex-col items-center py-1.5 px-3 rounded-lg transition-colors ${
                item.isActive
                  ? "text-zinc-950 font-semibold"
                  : "text-zinc-500 font-medium hover:text-zinc-800"
              }`}
            >
              <div className="relative">
                {item.icon(item.isActive)}
                {item.badge && (
                  <span className="absolute -top-1 -right-2 px-1 py-0.2 bg-zinc-100 border border-zinc-200 text-zinc-700 text-[8px] font-semibold rounded">
                    {item.badge}
                  </span>
                )}
              </div>
              <span className="text-[10px] mt-0.5 tracking-tight">{item.label}</span>
              {item.isActive && (
                <span className="w-1 h-1 rounded-full bg-zinc-900 mt-0.5" />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

