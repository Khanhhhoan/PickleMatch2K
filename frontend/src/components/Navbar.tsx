"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";

import Logo from "@/components/Logo";

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();
  const { info: toastInfo } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const displayName =
    user?.player_profile?.full_name ||
    user?.owner_profile?.full_name ||
    user?.email?.split("@")[0] ||
    "User";

  return (
    <header className="fixed top-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-b border-zinc-200/90 shadow-2xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-18">
          {/* Modern Vector Logo */}
          <Logo />

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-2">
            <Link
              href="/"
              className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all ${
                pathname === "/" || pathname.startsWith("/venues")
                  ? "bg-zinc-100 text-zinc-950 font-bold"
                  : "text-zinc-600 hover:text-zinc-950 hover:bg-zinc-50"
              }`}
            >
              Tìm Sân
            </Link>

            <button
              onClick={() => {
                if (!user) {
                  toastInfo("Vui lòng đăng nhập để sử dụng tính năng Ghép Trận!");
                  router.push("/login");
                } else {
                  router.push("/matches");
                }
              }}
              className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all cursor-pointer ${
                pathname === "/matches"
                  ? "bg-zinc-100 text-zinc-950 font-bold"
                  : "text-zinc-600 hover:text-zinc-950 hover:bg-zinc-50"
              }`}
            >
              Ghép Trận
            </button>

            {/* Dedicated Create Room Feature on Navbar */}
            <button
              onClick={() => {
                if (!user) {
                  toastInfo("Vui lòng đăng nhập để tạo phòng!");
                  router.push("/login");
                } else {
                  router.push("/matches/create");
                }
              }}
              className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all cursor-pointer ${
                pathname === "/matches/create"
                  ? "bg-zinc-100 text-zinc-950 font-bold"
                  : "text-zinc-600 hover:text-zinc-950 hover:bg-zinc-50"
              }`}
            >
              Tạo Phòng
            </button>

            {user && (
              <Link
                href="/bookings"
                className={`px-3.5 py-2 text-sm font-semibold rounded-xl transition-all ${
                  pathname.startsWith("/bookings")
                    ? "bg-zinc-100 text-zinc-950 font-bold"
                    : "text-zinc-600 hover:text-zinc-950 hover:bg-zinc-50"
                }`}
              >
                Lịch Đặt Sân
              </Link>
            )}

            {/* Direct Shortcuts for Owner / Staff / Admin if logged in */}
            {user?.role === "STAFF" && (
              <Link
                href="/staff/dashboard"
                className="px-4 py-2 text-sm font-bold text-zinc-950 bg-amber-400 hover:bg-amber-500 rounded-xl transition-all shadow-xs"
              >
                Cổng Nhân Viên
              </Link>
            )}

            {user?.role === "OWNER" && (
              <Link
                href="/owner/dashboard"
                className="px-4 py-2 text-sm font-semibold text-zinc-900 bg-zinc-100 hover:bg-zinc-200 rounded-xl transition-all border border-zinc-200"
              >
                Cổng Chủ Sân
              </Link>
            )}

            {user?.role === "ADMIN" && (
              <Link
                href="/admin"
                className="px-4 py-2 text-sm font-semibold text-zinc-900 bg-zinc-100 hover:bg-zinc-200 rounded-xl transition-all border border-zinc-200"
              >
                Cổng Quản Trị
              </Link>
            )}

            {/* User Profile / Auth Area */}
            {isLoading ? (
              <div className="w-9 h-9 rounded-full bg-zinc-200 animate-pulse ml-2" />
            ) : user ? (
              <div className="relative ml-2">
                <button
                  onClick={() => setMenuOpen(!menuOpen)}
                  className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl hover:bg-zinc-100 border border-zinc-200 transition-all cursor-pointer"
                >
                  <div className="w-7 h-7 rounded-full bg-zinc-950 flex items-center justify-center text-white font-bold text-xs">
                    {displayName[0].toUpperCase()}
                  </div>
                  <span className="text-sm font-semibold text-zinc-900 max-w-[120px] truncate">
                    {displayName}
                  </span>
                  <svg className="w-4 h-4 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                    <div className="absolute right-0 mt-2 w-56 bg-white rounded-2xl shadow-xl border border-zinc-200 py-2 z-50 animate-in fade-in">
                      <div className="px-4 py-2.5 border-b border-zinc-100">
                        <p className="text-[11px] text-zinc-400 font-medium">Tài khoản hiện tại</p>
                        <p className="text-sm font-bold text-zinc-950 truncate">{user.email}</p>
                        <span className="inline-flex items-center px-2 py-0.5 mt-1 rounded text-xs font-semibold bg-zinc-100 text-zinc-700">
                          {user.role === "PLAYER" ? "Khách hàng" : user.role === "OWNER" ? "Chủ sân" : user.role === "STAFF" ? "Nhân viên trực ca" : "Quản trị viên"}
                        </span>
                      </div>

                      <div className="py-1.5">
                        {user.role === "STAFF" && (
                          <Link
                            href="/staff/dashboard"
                            onClick={() => setMenuOpen(false)}
                            className="flex items-center px-4 py-2 text-sm font-bold text-amber-700 bg-amber-50 hover:bg-amber-100 transition-colors"
                          >
                            Cổng Nhân Viên Ca Trực
                          </Link>
                        )}
                        {user.role === "OWNER" && (
                          <Link
                            href="/owner/dashboard"
                            onClick={() => setMenuOpen(false)}
                            className="flex items-center px-4 py-2 text-sm font-bold text-zinc-900 bg-zinc-50 hover:bg-zinc-100 transition-colors"
                          >
                            Cổng Chủ Sân
                          </Link>
                        )}
                        <Link
                          href="/profile"
                          onClick={() => setMenuOpen(false)}
                          className="flex items-center px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 transition-colors"
                        >
                          Hồ sơ & Trình độ DUPR
                        </Link>
                        <Link
                          href="/profile?tab=payments"
                          onClick={() => setMenuOpen(false)}
                          className="flex items-center px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 transition-colors"
                        >
                          Lịch sử thanh toán
                        </Link>
                      </div>

                      <div className="border-t border-zinc-100 pt-1.5">
                        <button
                          onClick={() => {
                            logout();
                            setMenuOpen(false);
                          }}
                          className="w-full flex items-center px-4 py-2 text-left text-sm font-semibold text-rose-600 hover:bg-rose-50/60 transition-colors cursor-pointer"
                        >
                          Đăng xuất
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2.5 ml-2">
                <Link
                  href="/login"
                  className="px-4 py-2 text-sm font-semibold text-zinc-800 hover:text-zinc-950 transition"
                >
                  Đăng Nhập
                </Link>
                <Link
                  href="/register"
                  className="px-5 py-2 text-sm font-bold text-white bg-zinc-950 hover:bg-zinc-800 rounded-xl transition-all btn-press shadow-xs"
                >
                  Đăng Ký
                </Link>
              </div>
            )}
          </nav>

          {/* Mobile Right Actions & Hamburger Button */}
          <div className="flex items-center md:hidden gap-2">
            {user ? (
              <Link href="/profile" className="flex items-center p-1.5 rounded-full hover:bg-zinc-100">
                <div className="w-8 h-8 rounded-full bg-zinc-950 flex items-center justify-center text-white font-bold text-xs">
                  {displayName[0].toUpperCase()}
                </div>
              </Link>
            ) : (
              <Link
                href="/login"
                className="px-3.5 py-1.5 text-xs font-bold text-white bg-zinc-950 rounded-lg"
              >
                Đăng Nhập
              </Link>
            )}

            <button
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
              className="p-2 rounded-xl text-zinc-700 hover:bg-zinc-100 transition cursor-pointer"
              aria-label="Toggle Menu"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                {mobileNavOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile Navigation Dropdown Drawer */}
        {mobileNavOpen && (
          <div className="md:hidden py-4 border-t border-zinc-200/80 space-y-2 animate-in fade-in">
            <Link
              href="/"
              onClick={() => setMobileNavOpen(false)}
              className={`block px-4 py-2.5 text-sm font-semibold rounded-xl ${
                pathname === "/" ? "bg-zinc-100 text-zinc-950 font-bold" : "text-zinc-700"
              }`}
            >
              Tìm Sân
            </Link>
            <button
              onClick={() => {
                setMobileNavOpen(false);
                if (!user) {
                  toastInfo("Vui lòng đăng nhập để sử dụng tính năng Ghép Trận!");
                  router.push("/login");
                } else {
                  router.push("/matches");
                }
              }}
              className={`block w-full text-left px-4 py-2.5 text-sm font-semibold rounded-xl cursor-pointer ${
                pathname === "/matches" ? "bg-zinc-100 text-zinc-950 font-bold" : "text-zinc-700"
              }`}
            >
              Ghép Trận
            </button>
            <button
              onClick={() => {
                setMobileNavOpen(false);
                if (!user) {
                  toastInfo("Vui lòng đăng nhập để tạo phòng!");
                  router.push("/login");
                } else {
                  router.push("/matches/create");
                }
              }}
              className={`block w-full text-left px-4 py-2.5 text-sm font-semibold rounded-xl cursor-pointer ${
                pathname === "/matches/create" ? "bg-zinc-100 text-zinc-950 font-bold" : "text-zinc-700"
              }`}
            >
              Tạo Phòng
            </button>
            {user && (
              <Link
                href="/bookings"
                onClick={() => setMobileNavOpen(false)}
                className="block px-4 py-2.5 text-sm font-semibold text-zinc-700 rounded-xl"
              >
                Lịch Đặt Sân
              </Link>
            )}
            {user?.role === "OWNER" && (
              <Link
                href="/owner/dashboard"
                onClick={() => setMobileNavOpen(false)}
                className="block px-4 py-2.5 text-sm font-semibold text-zinc-900 bg-zinc-100 rounded-xl"
              >
                Cổng Quản Lý Chủ Sân
              </Link>
            )}
            {user?.role === "ADMIN" && (
              <Link
                href="/admin"
                onClick={() => setMobileNavOpen(false)}
                className="block px-4 py-2.5 text-sm font-semibold text-zinc-900 bg-zinc-100 rounded-xl"
              >
                Cổng Quản Trị Admin
              </Link>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

