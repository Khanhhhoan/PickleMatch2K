"use client";

import React from "react";
import Link from "next/link";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  showSubtitle?: boolean;
  className?: string;
  isLight?: boolean;
}

export default function Logo({
  size = "md",
  showSubtitle = true,
  className = "",
  isLight = false,
}: LogoProps) {
  const iconSizes = {
    sm: "w-9 h-9",
    md: "w-11 h-11 sm:w-12 sm:h-12",
    lg: "w-14 h-14 sm:w-16 sm:h-16",
  };

  const textSizes = {
    sm: "text-base font-black",
    md: "text-xl sm:text-2xl font-black",
    lg: "text-2xl sm:text-3xl font-black",
  };

  return (
    <Link href="/" className={`flex items-center gap-2.5 sm:gap-3 group select-none ${className}`}>
      {/* User's Exact Circular Crest Logo */}
      <div
        className={`${iconSizes[size]} shrink-0 flex items-center justify-center relative transition-transform duration-200 group-hover:scale-105`}
      >
        <img
          src="/images/logo_transparent.png"
          alt="PickleMatch2K Logo"
          className="w-full h-full object-contain filter drop-shadow-xs"
        />
      </div>

      {/* Brand Typography */}
      <div className="flex flex-col justify-center">
        <div className="flex items-center">
          <span
            className={`${textSizes[size]} tracking-tight leading-none ${
              isLight ? "text-white" : "text-zinc-950"
            }`}
          >
            PickleMatch
          </span>
          <span className="ml-1.5 px-1.5 py-0.5 rounded-lg bg-zinc-950 text-white font-black text-xs sm:text-sm tracking-wider uppercase shadow-2xs">
            2K
          </span>
        </div>
        {showSubtitle && (
          <span
            className={`text-[11px] sm:text-xs font-medium tracking-wide leading-none mt-1 hidden sm:block ${
              isLight ? "text-zinc-400" : "text-zinc-500"
            }`}
          >
            Hệ thống đặt sân & ghép trận
          </span>
        )}
      </div>
    </Link>
  );
}
