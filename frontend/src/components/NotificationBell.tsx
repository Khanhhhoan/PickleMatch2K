"use client";

/**
 * Chuông thông báo của người đang đăng nhập. Thông báo lưu ở máy chủ (đọc lại được khi vừa online trở lại);
 * chuông tải lại khi mở trang, mỗi phút, khi quay lại tab và ngay khi kênh WebSocket riêng báo có thông báo mới.
 */
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi, parseUtcDate } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWebSocket } from "@/lib/use-websocket";

interface AppNotification {
  id: number;
  kind: string;
  title: string;
  body: string;
  link?: string | null;
  created_at: string;
  read_at?: string | null;
}

const REFRESH_MS = 60_000;

function timeAgo(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - parseUtcDate(iso).getTime()) / 60_000));
  if (minutes < 1) return "vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return parseUtcDate(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function NotificationBell({ align = "right" }: { align?: "right" | "left" }) {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);

  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const channel = user && token ? `/api/v1/ws/user/${user.id}?token=${encodeURIComponent(token)}` : "/api/v1/ws/live";
  const { lastMessage } = useWebSocket(channel);

  const load = useCallback(() => {
    if (!user) return;
    fetchApi("/notifications?limit=20")
      .then((data) => {
        setItems(Array.isArray(data?.items) ? data.items : []);
        setUnread(Number(data?.unread_count) || 0);
      })
      .catch(() => {
        // mất mạng tạm thời: giữ danh sách đang có, lần tải sau sẽ cập nhật
      });
  }, [user]);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    window.addEventListener("focus", load);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", load);
    };
  }, [load]);

  useEffect(() => {
    if (lastMessage?.type === "NOTIFICATION_CREATED") load();
  }, [lastMessage, load]);

  if (!user) return null;

  const openItem = async (item: AppNotification) => {
    setOpen(false);
    if (!item.read_at) {
      await fetchApi(`/notifications/${item.id}/read`, { method: "POST" }).catch(() => null);
      load();
    }
    if (item.link) router.push(item.link);
  };

  const readAll = async () => {
    await fetchApi("/notifications/read-all", { method: "POST" }).catch(() => null);
    load();
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={unread > 0 ? `Thông báo, ${unread} chưa đọc` : "Thông báo"}
        className="relative p-2 rounded-xl text-zinc-700 hover:bg-zinc-100 border border-transparent hover:border-zinc-200 transition cursor-pointer"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-600 text-white text-[10px] font-black flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className={`absolute ${align === "right" ? "right-0" : "left-0"} mt-2 w-[min(22rem,calc(100vw-2rem))] bg-white rounded-2xl shadow-xl border border-zinc-200 z-50 animate-in fade-in`}
          >
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-zinc-100">
              <p className="text-sm font-black text-zinc-950">Thông báo</p>
              {unread > 0 && (
                <button type="button" onClick={readAll} className="text-xs font-bold text-zinc-600 hover:text-zinc-950 cursor-pointer">
                  Đánh dấu đã đọc tất cả
                </button>
              )}
            </div>
            <ul className="max-h-96 overflow-y-auto py-1">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => openItem(item)}
                    className={`w-full text-left px-4 py-3 hover:bg-zinc-50 transition cursor-pointer ${item.read_at ? "" : "bg-amber-50/50"}`}
                  >
                    <p className="flex items-center gap-2 text-sm font-bold text-zinc-950">
                      {!item.read_at && <span className="w-2 h-2 rounded-full bg-rose-600 shrink-0" />}
                      {item.title}
                    </p>
                    <p className="text-xs text-zinc-600 mt-0.5 leading-relaxed">{item.body}</p>
                    <p className="text-[11px] text-zinc-400 mt-1">{timeAgo(item.created_at)}</p>
                  </button>
                </li>
              ))}
              {items.length === 0 && <li className="px-4 py-6 text-center text-xs text-zinc-500">Chưa có thông báo nào.</li>}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
