export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    const port = window.location.port ? ":8000" : "";
    return `${window.location.protocol}//${window.location.hostname}${port}`;
  }
  return "http://localhost:8000";
}

export const API_BASE_URL = getApiBaseUrl();
export const TOKEN_KEY = "admin_token";
export const UNAUTHORIZED_EVENT = "pm2k-admin:unauthorized";

/** Chuyển `detail` của FastAPI (chuỗi, hoặc danh sách lỗi kiểm tra dữ liệu) thành một câu đọc được. */
export function describeApiError(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        const msg = (item as { msg?: unknown })?.msg;
        return typeof msg === "string" ? msg.replace(/^Value error, /, "") : "";
      })
      .filter(Boolean);
    if (parts.length > 0) return parts.join("; ");
  }
  return fallback;
}

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((options.headers as Record<string, string>) || {}),
  };

  const normalizedEndpoint = endpoint.startsWith("/api/v1") ? endpoint : `/api/v1${endpoint}`;
  const response = await fetch(`${getApiBaseUrl()}${normalizedEndpoint}`, { ...options, headers });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    if (response.status === 401 && token && typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new Error(describeApiError(errorData.detail, `Yêu cầu không thực hiện được (${response.status}).`));
  }

  if (response.status === 204) return null;
  return response.json();
}

export const apiGet = (endpoint: string) => fetchApi(endpoint);
export const apiPost = (endpoint: string, body?: unknown) =>
  fetchApi(endpoint, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const apiPut = (endpoint: string, body: unknown) => fetchApi(endpoint, { method: "PUT", body: JSON.stringify(body) });
export const apiDelete = (endpoint: string) => fetchApi(endpoint, { method: "DELETE" });

export function formatVND(amount: number | null | undefined): string {
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(amount || 0);
}

/**
 * Format Date to YYYY-MM-DD using local time (avoiding UTC -7 skew in Vietnam between 00:00 - 07:00 AM)
 */
export function formatLocalDate(date: Date | string = new Date()): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (isNaN(d.getTime())) return "";
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Mốc thời gian từ máy chủ luôn là UTC; chuỗi thiếu múi giờ được hiểu là UTC. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const iso = value.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(value) ? value : value.replace(" ", "T") + "Z";
  const date = new Date(iso);
  return isNaN(date.getTime()) ? "" : date.toLocaleString("vi-VN");
}
