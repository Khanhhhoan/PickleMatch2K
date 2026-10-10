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
  message?: string;
  participants_count?: number;
  num_players?: number;
  is_full?: boolean;
  [key: string]: any;
}

export function useWebSocket(endpoint: string = "/api/v1/ws/live") {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [liveActivities, setLiveActivities] = useState<Array<{ id: string; text: string; time: string; type: string }>>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    try {
      const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
      let wsUrl = "";

      if (process.env.NEXT_PUBLIC_WS_URL) {
        wsUrl = `${process.env.NEXT_PUBLIC_WS_URL}${cleanEndpoint}`;
      } else if (process.env.NEXT_PUBLIC_API_URL) {
        try {
          const u = new URL(process.env.NEXT_PUBLIC_API_URL);
          const proto = u.protocol === "https:" ? "wss:" : "ws:";
          wsUrl = `${proto}//${u.host}${cleanEndpoint}`;
        } catch {
          wsUrl = `ws://localhost:8000${cleanEndpoint}`;
        }
      } else if (typeof window !== "undefined") {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = window.location.port ? `${window.location.hostname}:8000` : window.location.host;
        wsUrl = `${proto}//${host}${cleanEndpoint}`;
      } else {
        wsUrl = `ws://localhost:8000${cleanEndpoint}`;
      }

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
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

      ws.onclose = () => {
        setIsConnected(false);
        // Automatic reconnection attempt after 3s
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 3000);
      };

      ws.onerror = () => {
        // Silently close without throwing unhandled console warnings
        try {
          ws.close();
        } catch {}
      };
    } catch (e) {
      console.warn("WebSocket connection attempt failed:", e);
    }
  }, [endpoint]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
          try {
            wsRef.current.close();
          } catch {}
        }
      }
    };
  }, [connect]);

  const send = useCallback((msg: string | object) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload = typeof msg === "string" ? msg : JSON.stringify(msg);
      wsRef.current.send(payload);
    }
  }, []);

  return { isConnected, lastMessage, liveActivities, send };
}
