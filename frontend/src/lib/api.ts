export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    // If running in browser without explicit env var, use current hostname on port 8000
    // This allows phone/tablet testing on LAN (192.168.x.x) seamlessly
    const port = window.location.port ? ":8000" : "";
    return `${window.location.protocol}//${window.location.hostname}${port}`;
  }
  return "http://localhost:8000";
}

/** Sự kiện phát ra khi máy chủ từ chối token (hết hạn hoặc tài khoản bị khóa). */
export const UNAUTHORIZED_EVENT = "pm2k:unauthorized";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

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
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };

  // Only set Content-Type to application/json if body is not FormData
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  // Ensure endpoint starts with /api/v1
  const normalizedEndpoint = endpoint.startsWith("/api/v1") ? endpoint : `/api/v1${endpoint}`;
  const baseUrl = getApiBaseUrl();

  const response = await fetch(`${baseUrl}${normalizedEndpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    if (response.status === 401 && token && typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(describeApiError(errorData.detail, "Yêu cầu không thực hiện được. Vui lòng thử lại."), response.status);
  }

  if (response.status === 204) return null;
  return response.json();
}

export async function uploadVenueImage(venueId: number, file: File, isPrimary: boolean = true) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("is_primary", isPrimary.toString());

  return fetchApi(`/venues/${venueId}/upload-image`, {
    method: "POST",
    body: formData,
  });
}

/** Đính kèm chứng từ chuyển hoàn (ảnh hoặc PDF) cho đơn đã xác nhận hoàn tiền. */
export async function uploadRefundProof(bookingId: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return fetchApi(`/bookings/${bookingId}/refund-proof`, { method: "POST", body: formData });
}

/** Mở chứng từ hoàn tiền trong tab mới. Tệp không công khai nên phải tải kèm phiên đăng nhập rồi mới mở. */
export async function openRefundProof(bookingId: number) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const opened = window.open("", "_blank"); // mở trước để trình duyệt không chặn cửa sổ bật lên
  const response = await fetch(`${getApiBaseUrl()}/api/v1/bookings/${bookingId}/refund-proof`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    opened?.close();
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(describeApiError(errorData.detail, "Không mở được chứng từ."), response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  if (opened) opened.location.href = url;
  else window.location.href = url;
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function deleteVenueImage(venueId: number, imageUrl: string) {
  const params = new URLSearchParams({ image_url: imageUrl });
  return fetchApi(`/venues/${venueId}/images?${params.toString()}`, {
    method: "DELETE",
  });
}

export function getMediaUrl(url?: string | null): string {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) {
    return url;
  }
  const base = getApiBaseUrl();
  if (url.startsWith("/")) {
    return `${base}${url}`;
  }
  return `${base}/${url}`;
}

export function formatVND(amount: number | null | undefined): string {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
  }).format(amount || 0);
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

/**
 * Parse an ISO date string from backend ensuring UTC interpretation
 * (prevents 7-hour timezone skew in Vietnam UTC+7 when string lacks 'Z')
 */
export function parseUtcDate(dateStr: string | null | undefined): Date {
  if (!dateStr) return new Date();
  if (dateStr.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(dateStr)) {
    return new Date(dateStr);
  }
  return new Date(dateStr.replace(" ", "T") + "Z");
}
