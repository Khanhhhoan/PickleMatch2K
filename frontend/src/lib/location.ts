export interface UserLocation {
  name: string;
  lat: number;
  lng: number;
  accuracy?: number;
  isGps?: boolean;
}

export interface PresetLocation {
  city: "HCM";
  cityName: string;
  district: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
}

export const PRESET_LOCATIONS: PresetLocation[] = [
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Quận Gò Vấp",
    name: "Sân Pickleball Gò Vấp - Pickleball Club 88",
    address: "RMJM+288, Hẻm Số 2 Lê Đức Thọ, Hạnh Thông, Gò Vấp",
    lat: 10.835400,
    lng: 106.678900,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Quận Gò Vấp",
    name: "CLB Nhà Mình Pickleball - Gò Vấp",
    address: "509 Đ. Phạm Huy Thông, Phường 6, Gò Vấp",
    lat: 10.844140,
    lng: 106.686860,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Quận 1",
    name: "Sân Pickleball 102 Cung VH Lao Động",
    address: "55B Nguyễn Thị Minh Khai, P. Bến Thành, Q.1",
    lat: 10.7745,
    lng: 106.6918,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Quận 3",
    name: "CLB Pickleball Hồ Xuân Hương Quận 3",
    address: "02 Hồ Xuân Hương, P. Võ Thị Sáu, Q.3",
    lat: 10.7758,
    lng: 106.6908,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Tân Bình",
    name: "Sân VPP Saigon (VPP Pickleball Club)",
    address: "16 Đ. 18E Cộng Hòa, P.4, Tân Bình",
    lat: 10.8035,
    lng: 106.6572,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "TP. Thủ Đức",
    name: "PickoLand Thảo Điền (PickoLand Club)",
    address: "188/A6 Nguyễn Văn Hưởng, Thảo Điền, TP. Thủ Đức",
    lat: 10.8142,
    lng: 106.7325,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "TP. Thủ Đức",
    name: "USC Thạnh Mỹ Lợi (Thủ Thiêm Villa)",
    address: "91 Trương Văn Bang, Thạnh Mỹ Lợi, TP. Thủ Đức",
    lat: 10.7682,
    lng: 106.7561,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Phú Nhuận",
    name: "Sân Pickleball Rạch Miễu Phú Nhuận",
    address: "01 Hoa Phượng, P.2, Phú Nhuận",
    lat: 10.7972,
    lng: 106.6890,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Tân Phú",
    name: "Sân Pickleball 130 Chế Lan Viên Tân Phú",
    address: "130 Chế Lan Viên, P. Tây Thạnh, Tân Phú",
    lat: 10.8128,
    lng: 106.6265,
  },
  {
    city: "HCM",
    cityName: "TP. Hồ Chí Minh",
    district: "Bình Thạnh",
    name: "Sân Pickleball Liber Đặng Thùy Trâm",
    address: "235/50/31 Đặng Thùy Trâm, P.13, Bình Thạnh",
    lat: 10.8250,
    lng: 106.7025,
  },
];

const LOCAL_STORAGE_KEY = "pickleball_user_location";

export function getSavedLocation(): UserLocation | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function saveLocation(loc: UserLocation): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(loc));
  } catch (err) {
    console.error("Failed to save location to localStorage", err);
  }
}

// Great circle distance in km
export function calculateDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371; // Earth's radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c * 10) / 10;
}

// Find closest preset location for fallback naming
export function findClosestPreset(lat: number, lng: number): PresetLocation {
  let closest = PRESET_LOCATIONS[0];
  let minDistance = Infinity;

  for (const preset of PRESET_LOCATIONS) {
    const dist = calculateDistanceKm(lat, lng, preset.lat, preset.lng);
    if (dist < minDistance) {
      minDistance = dist;
      closest = preset;
    }
  }
  return closest;
}

// Reverse geocode with BigDataCloud (fast, accurate for VN) & OpenStreetMap fallback
export async function reverseGeocode(lat: number, lng: number): Promise<string> {
  // 1. Try BigDataCloud Client Geocoding (Rất chính xác cấp Quận/Phường tại Việt Nam, không giới hạn CORS)
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);

    const res = await fetch(
      `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lng}&localityLanguage=vi`,
      { signal: controller.signal }
    );
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      const locality = data.locality?.trim() || "";
      const city = data.city?.trim() || data.principalSubdivision?.trim() || "TP. Hồ Chí Minh";
      if (locality && city) {
        return locality !== city ? `${locality}, ${city}` : city;
      }
      if (city) return city;
    }
  } catch {
    // Continue to provider 2
  }

  // 2. Try OpenStreetMap Nominatim
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);

    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`,
      {
        signal: controller.signal,
        headers: {
          "Accept-Language": "vi,en;q=0.8",
        },
      }
    );
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      if (data.address) {
        const addr = data.address;
        const parts = [
          addr.suburb || addr.quarter || addr.neighbourhood,
          addr.city_district || addr.district || addr.county || addr.town,
          addr.city || addr.state || "TP. Hồ Chí Minh",
        ].filter(Boolean);
        if (parts.length > 0) {
          return parts.join(", ");
        }
      }
      if (data.display_name) {
        return data.display_name;
      }
    }
  } catch {
    // Continue to fallback
  }

  // 3. Fallback: Trả về tọa độ GPS thực tế thay vì gán nhãn sân mẫu ngẫu nhiên
  return `Tọa độ GPS (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
}

// Search address using Nominatim geocoding (supports exact Google Maps style addresses)
export async function searchAddressGeocode(query: string): Promise<UserLocation[]> {
  if (!query.trim()) return [];
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const searchQuery = query.toLowerCase().includes("việt nam") || query.toLowerCase().includes("vietnam")
      ? query
      : `${query}, Hồ Chí Minh, Việt Nam`;

    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}&limit=5&countrycodes=vn&addressdetails=1`,
      {
        signal: controller.signal,
        headers: {
          "Accept-Language": "vi,en;q=0.8",
        },
      }
    );
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        return data.map((item: any) => ({
          name: item.display_name,
          lat: parseFloat(item.lat),
          lng: parseFloat(item.lon),
          isGps: false,
        }));
      }
    }
  } catch (err) {
    console.error("Geocoding search failed", err);
  }
  return [];
}

// High Accuracy Geolocation API wrapper with intelligent retry for desktop/mobile
export function getCurrentGpsPosition(): Promise<{ lat: number; lng: number; accuracy: number }> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !navigator.geolocation) {
      reject(new Error("Trình duyệt không hỗ trợ Geolocation"));
      return;
    }

    // 1. Thử độ chính xác cao trước
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        });
      },
      (firstErr) => {
        // 2. Nếu timeout hoặc máy tính không có phần cứng GPS riêng, thử chế độ tiêu chuẩn qua Wi-Fi/IP
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            resolve({
              lat: pos.coords.latitude,
              lng: pos.coords.longitude,
              accuracy: pos.coords.accuracy,
            });
          },
          (secondErr) => {
            reject(secondErr || firstErr);
          },
          {
            enableHighAccuracy: false,
            timeout: 10000,
            maximumAge: 60000,
          }
        );
      },
      {
        enableHighAccuracy: true,
        timeout: 7000,
        maximumAge: 10000,
      }
    );
  });
}

// Universal Google Maps URL Builder for Venues (Jumps directly to the venue place card)
export function getGoogleMapsUrl(venue?: {
  name?: string | null;
  address?: string | null;
  google_maps_url?: string | null;
  latitude?: number | null;
  longitude?: number | null;
} | null): string {
  if (!venue) return "https://www.google.com/maps";

  // 1. Direct Share Link (e.g. maps.app.goo.gl, goo.gl/maps, or verified place link)
  if (venue.google_maps_url && typeof venue.google_maps_url === "string") {
    const trimmed = venue.google_maps_url.trim();
    if (
      trimmed &&
      !trimmed.includes("place//@") &&
      !trimmed.endsWith("query=")
    ) {
      if (trimmed.includes("goo.gl") || (trimmed.includes("/place/") && !trimmed.includes("place//@"))) {
        return trimmed;
      }
      if (trimmed.includes("query=") && !/^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=\d/.test(trimmed)) {
        return trimmed;
      }
    }
  }

  // 2. Search by Clean Venue Name & District (Opens the exact Business Place Card on Google Maps)
  if (venue.name && venue.name.trim()) {
    // Remove disruptive hyphens that cause Google negative search (e.g. " - " -> " ")
    const cleanName = venue.name.replace(/\s*[-–—]\s*/g, " ").trim();
    const query = cleanName.toLowerCase().includes("gò vấp") || cleanName.toLowerCase().includes("hồ chí minh") || cleanName.toLowerCase().includes("tp.hcm")
      ? cleanName
      : `${cleanName}, Hồ Chí Minh`;
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }

  // 3. Fallback: Search by Address
  if (venue.address && venue.address.trim()) {
    const cleanAddress = venue.address.replace(/\s*[-–—]\s*/g, " ").trim();
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(cleanAddress)}`;
  }

  // 4. Fallback: Search by GPS Coordinates
  const lat = venue.latitude != null ? Number(venue.latitude) : null;
  const lng = venue.longitude != null ? Number(venue.longitude) : null;
  if (lat != null && lng != null && !isNaN(lat) && !isNaN(lng) && (lat !== 0 || lng !== 0)) {
    return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
  }

  return "https://www.google.com/maps";
}

