"use client";

import { getMediaUrl } from "@/lib/api";

interface AvatarProps {
  name?: string | null;
  url?: string | null;
  /** Kích thước, màu nền và cỡ chữ của vòng tròn (lớp Tailwind) */
  className?: string;
}

/** Ảnh đại diện tròn của người chơi; chưa có ảnh thì hiện chữ cái đầu của tên. */
export default function Avatar({ name, url, className = "w-8 h-8 text-xs bg-zinc-900 text-white" }: AvatarProps) {
  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- ảnh người chơi tải lên (máy chủ API hoặc Cloudinary), đã thu về 320x320
      <img
        src={getMediaUrl(url)}
        alt={name ? `Ảnh đại diện của ${name}` : "Ảnh đại diện"}
        loading="lazy"
        className={`${className} rounded-full object-cover shrink-0`}
      />
    );
  }
  const initial = (name || "").trim().charAt(0).toUpperCase() || "?";
  return (
    <span aria-hidden="true" className={`${className} rounded-full inline-flex items-center justify-center font-bold shrink-0`}>
      {initial}
    </span>
  );
}
