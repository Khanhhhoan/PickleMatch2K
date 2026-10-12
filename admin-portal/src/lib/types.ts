/** Kiểu dữ liệu trả về từ API mà cổng quản trị sử dụng. */

export interface User {
  id: number;
  email: string;
  role: "PLAYER" | "OWNER" | "STAFF" | "ADMIN";
  is_active: boolean;
  player_profile?: {
    full_name?: string | null;
    phone?: string | null;
    skill_level?: number | null;
    play_style?: string | null;
    purpose?: string | null;
  } | null;
  owner_profile?: { full_name?: string | null; phone?: string | null; company_name?: string | null; bank_account?: string | null } | null;
  staff_profile?: { full_name?: string | null; phone?: string | null; venue_id?: number | null; venue_name?: string | null; owner_name?: string | null } | null;
}

export interface Venue {
  id: number;
  owner_id: number;
  name: string;
  address?: string | null;
  description?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  status: "PENDING" | "ACTIVE" | "INACTIVE" | "MAINTENANCE" | "REJECTED";
  courts: { id: number; name: string; status: string }[];
  price_rules: { rule_type: string; price: number }[];
  owner_full_name?: string | null;
  owner_company_name?: string | null;
  owner_bank_account?: string | null;
}

export interface BookingDetail {
  court_id: number;
  date: string;
  start_time: string;
  end_time: string;
  is_active: boolean;
  court_name?: string | null;
  venue_id?: number | null;
  venue_name?: string | null;
}

export interface Booking {
  id: number;
  booking_code?: string | null;
  source: "ONLINE" | "DESK";
  total_price: number;
  deposit_amount: number;
  paid_amount: number;
  remaining_amount: number;
  status: string;
  payment_status: string;
  refund_status?: string | null;
  refund_amount?: number | null;
  created_at: string;
  details: BookingDetail[];
  user_name?: string | null;
  user_phone?: string | null;
  user_email?: string | null;
}

export interface Transaction {
  id: number;
  transaction_code?: string | null;
  booking_id: number;
  gateway: string;
  method?: string | null;
  kind?: string | null;
  amount_in: number;
  transaction_content?: string | null;
  reference_number?: string | null;
  status: string;
  created_at?: string | null;
  booking?: { booking_code?: string | null } | null;
}

export interface MatchParticipant {
  id: number;
  user_id: number;
  user_name?: string | null;
  skill_level?: number | null;
  phone?: string | null;
}

export interface Match {
  id: number;
  creator_id: number;
  venue_id: number;
  court_id?: number | null;
  booking_code?: string | null;
  date: string;
  start_time: string;
  end_time: string;
  required_skill?: number | null;
  num_players: number;
  purpose?: string | null;
  notes?: string | null;
  status: "OPEN" | "FULL" | "CANCELLED" | "COMPLETED";
  venue_name?: string | null;
  court_name?: string | null;
  creator_name?: string | null;
  participants: MatchParticipant[];
}

export interface DailyActivity {
  /** Ngày theo giờ Việt Nam, dạng YYYY-MM-DD. */
  date: string;
  /** Thực thu trong ngày: khoản thu trừ khoản hoàn. */
  revenue: number;
  /** Số đơn đặt sân được tạo trong ngày. */
  bookings: number;
}

export interface Stats {
  total_revenue: number;
  collected_amount: number;
  refunded_amount: number;
  completed_bookings: number;
  pending_bookings: number;
  pending_refunds: number;
  total_bookings: number;
  total_courts: number;
  /** Chỉ gồm những ngày có phát sinh, cũ trước mới sau. */
  daily?: DailyActivity[];
}

export interface AdminData {
  users: User[];
  venues: Venue[];
  bookings: Booking[];
  matches: Match[];
  transactions: Transaction[];
  stats: Stats | null;
}

export interface TabProps {
  data: AdminData;
  /** Chạy một thao tác ghi, hiện thông báo và tải lại dữ liệu. Trả về true nếu thành công. */
  run: (action: () => Promise<unknown>, successMessage?: string) => Promise<boolean>;
}
