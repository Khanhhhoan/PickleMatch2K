// Cụm sân như API trả về (GET /search/venues, GET /venues/{id}); giờ ở dạng "HH:MM:SS".

export interface Court {
  id: number;
  venue_id: number;
  name: string;
  status?: string | null;
  /** Giá riêng của sân (VNĐ/giờ); không có thì dùng bảng giá chung của cụm sân. */
  price?: number | null;
}

export interface OperatingHour {
  id: number;
  venue_id: number;
  /** 0 = Thứ Hai ... 6 = Chủ Nhật */
  day_of_week: number;
  open_time: string;
  close_time: string;
}

export interface PriceRule {
  id: number;
  venue_id: number;
  rule_type: string; // BASE, PEAK, WEEKEND
  start_time?: string | null;
  end_time?: string | null;
  price: number;
}

export interface Amenity {
  id: number;
  name: string;
  icon?: string | null;
}

export interface Venue {
  id: number;
  owner_id: number;
  name: string;
  description?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  google_maps_url?: string | null;
  image_url?: string | null;
  images?: string | null;
  status?: string | null;
  unpaid_desk_release_minutes: number;
  courts: Court[];
  operating_hours: OperatingHour[];
  price_rules: PriceRule[];
  amenities: Amenity[];
  /** Chỉ có trong kết quả tìm kiếm có gửi kèm vị trí (km). */
  distance_km?: number | null;
}
