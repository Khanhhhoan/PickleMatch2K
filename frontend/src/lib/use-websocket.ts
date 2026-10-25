"use client";

import { useState, useEffect, useRef, useCallback } from "react";

export interface WsMessage {
  type: string;
  venue_id?: number;
  venue_name?: string;
  date?: string;
  slots?: Array<{
    court_id: number;
    court_name?: string;
    date: string;
    start_time: string;
    end_time: string;
    is_available: boolean;
  }>;
  match_id?: number;
  booking_id?: number;
  message?: string;
  participants_count?: number;
  num_players?: number;
  is_full?: boolean;
  [key: string]: unknown;
}

/** Địa chỉ WebSocket ứng với endpoint: theo biến môi trường, không có thì cùng máy với API (cổng 8000). */
function websocketUrl(endpoint: string): string {
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  if (process.env.NEXT_PUBLIC_WS_URL) {
    return `${process.env.NEXT_PUBLIC_WS_URL}${cleanEndpoint}`;
  }
  if (process.env.NEXT_PUBLIC_API_URL) {
    try {
      const u = new URL(process.env.NEXT_PUBLIC_API_URL);
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}${cleanEndpoint}`;
    } catch {
      return `ws://localhost:8000${cleanEndpoint}`;
    }
  }
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.port ? `${window.location.hostname}:8000` : window.location.host;
    return `${proto}//${host}${cleanEndpoint}`;
  }
  return `ws://localhost:8000${cleanEndpoint}`;
}

export function useWebSocket(endpoint: string = "/api/v1/ws/live") {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [liveActivities, setLiveActivities] = useState<Array<{ id: string; text: string; time: string; type: string }>>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;

    // Khai báo hàm (không phải biến) để onclose gọi lại được chính nó khi tự kết nối lại
    function open() {
      try {
        socket = new WebSocket(websocketUrl(endpoint));
        wsRef.current = socket;
        const current = socket;

        current.onopen = () => {
          setIsConnected(true);
        };

        current.onmessage = (event) => {
          try {
            const data: WsMessage = JSON.parse(event.data);
            setLastMessage(data);

            if (data.message) {
              const newAct = {
                id: Math.random().toString(36).substring(7),
                text: data.message,
                time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
                type: data.type || "INFO",
              };
              setLiveActivities((prev) => [newAct, ...prev.slice(0, 9)]);
            }
          } catch {
            // ignore non-JSON messages (e.g. pong)
          }
        };

        current.onclose = () => {
          setIsConnected(false);
          // Automatic reconnection attempt after 3s
          if (!closed) reconnectTimeoutRef.current = setTimeout(open, 3000);
        };

        current.onerror = () => {
          // Silently close without throwing unhandled console warnings
          try {
            current.close();
          } catch {}
        };
      } catch (e) {
        console.warn("WebSocket connection attempt failed:", e);
      }
    }

    open();
    return () => {
      closed = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          try {
            socket.close();
          } catch {}
        }
      }
    };
  }, [endpoint]);

  const send = useCallback((msg: string | object) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload = typeof msg === "string" ? msg : JSON.stringify(msg);
      wsRef.current.send(payload);
    }
  }, []);

  return { isConnected, lastMessage, liveActivities, send };
}
