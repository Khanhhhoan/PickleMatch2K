"use client";

import React, { useState, useEffect, use, useMemo, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { fetchApi, formatVND, getMediaUrl, formatLocalDate } from "@/lib/api";
import { MAX_ADVANCE_DAYS } from "@/lib/booking";
import { useAuth } from "@/lib/auth-context";
import { useWebSocket } from "@/lib/use-websocket";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import SepayCheckoutModal from "@/components/SepayCheckoutModal";
import { getGoogleMapsUrl, calculateDistanceKm, getSavedLocation } from "@/lib/location";

interface TimeSlot {
  start_time: string;
  end_time: string;
  price: number;
  is_available: boolean;
  is_past?: boolean;      // khung giờ đã trôi qua
  is_held?: boolean;      // đang được người khác giữ tạm
  held_by_me?: boolean;   // đang được chính mình giữ tạm
  hold_seconds_remaining?: number;
}

interface Review {
  id: number;
  rating: number;
  comment?: string | null;
  created_at?: string | null;
  author_name: string;
}

const WEEKDAY_NAMES = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];
const PRICE_RULE_LABEL: Record<string, string> = { BASE: "Giờ thường", PEAK: "Giờ cao điểm", WEEKEND: "Cuối tuần" };

interface CourtAvailability {
  court_id: number;
  court_name: string;
  slots: TimeSlot[];
}

const slotKey = (courtId: number, startTime: string) => `${courtId}-${startTime}`;

export default function VenueDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user } = useAuth();
  const router = useRouter();
  const { success: toastSuccess, error: toastError, info: toastInfo } = useToast();
  const [venue, setVenue] = useState<any>(null);
  const [availability, setAvailability] = useState<CourtAvailability[]>([]);
  const [selectedDate, setSelectedDate] = useState(() => {
    return formatLocalDate();
  });
  const [selectedSlots, setSelectedSlots] = useState<{ court_id: number; court_name: string; start_time: string; end_time: string; price: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);
  const [checkoutBookingId, setCheckoutBookingId] = useState<number | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewForm, setReviewForm] = useState({ rating: 5, comment: "" });
  const [sendingReview, setSendingReview] = useState(false);
  const [liveNotice, setLiveNotice] = useState<string | null>(null);

  // Real-time WebSocket connection for this venue
  const { isConnected, lastMessage } = useWebSocket(`/api/v1/ws/venues/${id}`);

  const requestedDate = useRef(selectedDate);       // ngày được yêu cầu gần nhất
  const loadedDate = useRef<string | null>(null);   // ngày của bảng giờ đang hiển thị
  const restoredDate = useRef<string | null>(null); // ngày đã đưa lại các khung mình đang giữ tạm vào giỏ
  const busySlots = useRef(new Set<string>());      // khung giờ đang chờ máy chủ trả lời (chống bấm đúp)
  // Sau khi đăng nhập, quay lại đúng cụm sân đang xem
  const loginUrl = `/login?next=${encodeURIComponent(`/venues/${id}`)}`;

  const loadAvailability = async (targetDate: string) => {
    requestedDate.current = targetDate;
    try {
      const data = await fetchApi(`/search/venues/${id}/availability?target_date=${targetDate}`);
      if (requestedDate.current !== targetDate) return; // phản hồi đến muộn của ngày đã rời đi
      loadedDate.current = targetDate;
      setAvailability(data.courts || []);
    } catch {
      if (requestedDate.current !== targetDate) return;
      loadedDate.current = null;
      setAvailability([]);
    }
  };

  useEffect(() => {
    fetchApi(`/venues/${id}`)
      .then((data) => {
        setVenue(data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
    fetchApi(`/venues/${id}/reviews`)
      .then((data) => setReviews(Array.isArray(data) ? data : []))
      .catch(() => setReviews([]));
  }, [id]);

  // Giữ giỏ chọn khớp với bảng giờ mới nhất: bỏ khung không còn đặt được (người khác vừa đặt hoặc đang giữ),
  // và khi mở một ngày thì đưa lại các khung mình đang giữ tạm (ví dụ sau khi tải lại trang).
  useEffect(() => {
    if (availability.length === 0 || loadedDate.current !== selectedDate) return;
    const live = new Map<string, { court: CourtAvailability; slot: TimeSlot }>();
    availability.forEach((court) => court.slots.forEach((slot) => live.set(slotKey(court.court_id, slot.start_time), { court, slot })));

    const lost = selectedSlots.filter((s) => {
      const entry = live.get(slotKey(s.court_id, s.start_time));
      return !entry || !entry.slot.is_available || entry.slot.is_held;
    });
    let next = lost.length > 0 ? selectedSlots.filter((s) => !lost.includes(s)) : selectedSlots;

    if (restoredDate.current !== selectedDate) {
      restoredDate.current = selectedDate;
      const known = new Set(next.map((s) => slotKey(s.court_id, s.start_time)));
      const mine = [...live.values()]
        .filter(({ court, slot }) => slot.held_by_me && slot.is_available && !known.has(slotKey(court.court_id, slot.start_time)))
        .map(({ court, slot }) => ({
          court_id: court.court_id,
          court_name: court.court_name,
          start_time: slot.start_time,
          end_time: slot.end_time,
          price: slot.price,
        }));
      if (mine.length > 0) next = [...next, ...mine];
    }

    if (next !== selectedSlots) setSelectedSlots(next);
    if (lost.length > 0) {
      const names = lost.map((s) => `${s.start_time.slice(0, 5)} (${s.court_name})`).join(", ");
      toastInfo(`Khung giờ ${names} không còn trống nên đã được bỏ khỏi lựa chọn của bạn.`);
    }
  }, [availability, selectedSlots, selectedDate]);

  const submitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    setSendingReview(true);
    try {
      const saved: Review = await fetchApi(`/venues/${id}/reviews`, {
        method: "POST",
        body: JSON.stringify({ rating: reviewForm.rating, comment: reviewForm.comment.trim() || null }),
      });
      setReviews((prev) => [saved, ...prev.filter((r) => r.id !== saved.id)]);
      setReviewForm({ rating: 5, comment: "" });
      toastSuccess("Cảm ơn bạn đã đánh giá cụm sân!");
    } catch (err: any) {
      toastError(err.message || "Chưa gửi được đánh giá.");
    } finally {
      setSendingReview(false);
    }
  };

  useEffect(() => {
    if (selectedDate && id) {
      loadAvailability(selectedDate);
    }
  }, [id, selectedDate]);

  // Handle Real-Time WebSocket Events
  useEffect(() => {
    if (!lastMessage) return;

    if (
      lastMessage.type === "SLOT_BOOKED" ||
      lastMessage.type === "SLOT_RELEASED" ||
      lastMessage.type === "SLOT_HELD" ||
      lastMessage.type === "BOOKING_RESCHEDULED" ||
      lastMessage.type === "PAYMENT_CONFIRMED" ||
      lastMessage.type === "BOOKING_STATUS_CHANGED" ||
      lastMessage.type === "PRICE_UPDATED"
    ) {
      // If the event corresponds to the current date or venue
      if (lastMessage.date === selectedDate || !lastMessage.date) {
        loadAvailability(selectedDate);
      }

      if (lastMessage.message) {
        setLiveNotice(lastMessage.message);
        setTimeout(() => setLiveNotice(null), 5000);
      }
    }
  }, [lastMessage, selectedDate]);

  const toggleSlot = async (court_id: number, court_name: string, start_time: string, end_time: string, price: number) => {
    if (!user) {
      toastInfo("Vui lòng đăng nhập tài khoản để đặt và giữ chỗ sân trong thời gian thực!");
      router.push(loginUrl);
      return;
    }

    // Bỏ qua lần bấm khi lần bấm trước trên cùng khung giờ chưa xong (bấm đúp), hoặc bảng giờ của ngày mới chưa tải xong
    const key = slotKey(court_id, start_time);
    if (busySlots.current.has(key) || loadedDate.current !== selectedDate) return;
    busySlots.current.add(key);

    const isSameSlot = (s: { court_id: number; start_time: string }) => s.court_id === court_id && s.start_time === start_time;
    const isCurrentlySelected = selectedSlots.some(isSameSlot);

    try {
      if (isCurrentlySelected) {
        // Release slot
        setSelectedSlots((prev) => prev.filter((s) => !isSameSlot(s)));
        await fetchApi("/bookings/release-slot", {
          method: "POST",
          body: JSON.stringify({
            venue_id: parseInt(id),
            court_id,
            date: selectedDate,
            start_time,
          }),
        }).catch(console.error);
      } else {
        // Hold slot in real-time
        try {
          await fetchApi("/bookings/hold-slot", {
            method: "POST",
            body: JSON.stringify({
              venue_id: parseInt(id),
              court_id,
              court_name,
              date: selectedDate,
              start_time,
              end_time,
            }),
          });

          setSelectedSlots((prev) => (prev.some(isSameSlot) ? prev : [...prev, { court_id, court_name, start_time, end_time, price }]));
        } catch (err: any) {
          toastError(err.message || "Khung giờ này đang có người khác giữ chỗ hoặc vừa được đặt!");
          loadAvailability(selectedDate);
        }
      }
    } finally {
      busySlots.current.delete(key);
    }
  };

  const totalPrice = selectedSlots.reduce((sum, slot) => sum + slot.price, 0);

  const handleBooking = async () => {
    if (!user) {
      toastInfo("Vui lòng đăng nhập tài khoản Khách hàng để hoàn tất đặt sân!");
      router.push(loginUrl);
      return;
    }
    if (selectedSlots.length === 0) return;

    setBooking(true);
    try {
      const details = selectedSlots.map((s) => ({
        court_id: s.court_id,
        date: selectedDate,
        start_time: s.start_time,
        end_time: s.end_time,
      }));
      const res = await fetchApi("/bookings", {
        method: "POST",
        body: JSON.stringify({ details }),
      });
      setSelectedSlots([]);
      setCheckoutBookingId(res.id);
      await loadAvailability(selectedDate);
    } catch (err: any) {
      toastError("Đặt sân thất bại: " + err.message);
      // Bảng giờ đã thay đổi: tải lại để khung không còn trống tự rời khỏi giỏ
      loadAvailability(selectedDate);
    } finally {
      setBooking(false);
    }
  };


  // Mini Calendar Month Grid State
  const [calendarDate, setCalendarDate] = useState(() => new Date());
  const todayStr = useMemo(() => formatLocalDate(), []);
  // Ngày xa nhất còn đặt được
  const lastBookableStr = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + MAX_ADVANCE_DAYS);
    return formatLocalDate(d);
  }, []);

  const currentYear = calendarDate.getFullYear();
  const currentMonth = calendarDate.getMonth();

  const daysInMonth = useMemo(() => {
    return new Date(currentYear, currentMonth + 1, 0).getDate();
  }, [currentYear, currentMonth]);

  const firstDayOfWeek = useMemo(() => {
    // 0 = Sunday, 1 = Monday ... convert to Monday = 0, Sunday = 6
    const day = new Date(currentYear, currentMonth, 1).getDay();
    return (day + 6) % 7;
  }, [currentYear, currentMonth]);

  const canGoPrevMonth = useMemo(() => {
    const today = new Date();
    return currentYear > today.getFullYear() || (currentYear === today.getFullYear() && currentMonth > today.getMonth());
  }, [currentYear, currentMonth]);

  const handlePrevMonth = () => {
    if (canGoPrevMonth) {
      setCalendarDate(new Date(currentYear, currentMonth - 1, 1));
    }
  };

  const canGoNextMonth = formatLocalDate(new Date(currentYear, currentMonth + 1, 1)) <= lastBookableStr;

  const handleNextMonth = () => {
    if (canGoNextMonth) {
      setCalendarDate(new Date(currentYear, currentMonth + 1, 1));
    }
  };

  const handleSelectDate = (dateStr: string) => {
    setSelectedDate(dateStr);
    setSelectedSlots([]);
    const [y, m] = dateStr.split("-").map(Number);
    setCalendarDate(new Date(y, m - 1, 1));
  };

  const handleQuickSelect = (type: "today" | "tomorrow" | "weekend" | "next_week") => {
    const d = new Date();
    if (type === "tomorrow") {
      d.setDate(d.getDate() + 1);
    } else if (type === "weekend") {
      const day = d.getDay();
      const diff = day === 6 ? 0 : (6 - day + 7) % 7;
      d.setDate(d.getDate() + diff);
    } else if (type === "next_week") {
      const day = d.getDay();
      const diff = ((1 - day + 7) % 7) || 7;
      d.setDate(d.getDate() + diff);
    }
    const dateStr = formatLocalDate(d);
    handleSelectDate(dateStr);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-50/50 font-sans">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 py-20 text-center">
          <div className="w-8 h-8 mx-auto border-2 border-zinc-300 border-t-zinc-900 rounded-full animate-spin" />
          <p className="mt-3 text-xs text-zinc-500">Đang tải thông tin sân & bảng giờ trống...</p>
        </div>
      </div>
    );
  }

  if (!venue) {
    return (
      <div className="min-h-screen bg-zinc-50/50 font-sans">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 py-20 text-center">
          <h2 className="text-base font-bold text-zinc-900 mb-1">Không tìm thấy cụm sân</h2>
          <Link href="/" className="text-zinc-600 font-medium text-xs hover:text-zinc-900 underline">← Về trang chủ</Link>
        </div>
      </div>
    );
  }

  const mapDirectionUrl = getGoogleMapsUrl(venue);
  // Chỉ hiện khoảng cách khi thật sự biết vị trí của người dùng
  const savedLocation = getSavedLocation();
  const playerLat = savedLocation?.lat ?? user?.player_profile?.latitude ?? null;
  const playerLng = savedLocation?.lng ?? user?.player_profile?.longitude ?? null;
  const distanceKm = (venue?.latitude && venue?.longitude && playerLat != null && playerLng != null)
    ? calculateDistanceKm(playerLat, playerLng, venue.latitude, venue.longitude)
    : null;
  const averageRating = reviews.length > 0 ? reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length : null;
  const hoursByDay: Record<number, { open_time: string; close_time: string }> = Object.fromEntries(
    (venue.operating_hours || []).map((h: any) => [h.day_of_week, h]),
  );

  return (
    <div className="min-h-screen bg-zinc-50/50 pb-28 md:pb-12 font-sans">
      <Navbar />

      {/* Real-time Notification Floating Banner */}
      {liveNotice && (
        <div className="bg-zinc-900 text-white px-4 py-2 text-xs font-medium text-center flex items-center justify-center gap-2 animate-in fade-in">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>{liveNotice} (Đã đồng bộ tự động)</span>
        </div>
      )}

      {/* Rich Venue Header with Venue Photo */}
      <div className="relative bg-zinc-950 text-white overflow-hidden">
        {/* Background Image with Dark Overlay */}
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat opacity-40 blur-xs scale-105"
          style={{
            backgroundImage: `url('${venue.image_url ? getMediaUrl(venue.image_url) : "/images/hero_bg.jpg"}')`,
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-zinc-950 via-zinc-950/85 to-zinc-950/70" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 relative z-10">
          <div className="mb-3">
            <Link href="/" className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-white transition">
              ← Quay lại danh sách sân
            </Link>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
            <div className="flex items-start gap-4">
              {/* Venue Cover Avatar / Photo Preview */}
              <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-2xl overflow-hidden bg-zinc-800 border-2 border-white/20 shadow-xl shrink-0">
                <img
                  src={venue.image_url ? getMediaUrl(venue.image_url) : "/images/hero_bg.jpg"}
                  alt={venue.name}
                  className="w-full h-full object-cover"
                  onError={(e: any) => {
                    e.currentTarget.src = "/images/hero_bg.jpg";
                  }}
                />
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  {averageRating !== null && (
                    <span className="px-2.5 py-0.5 rounded-full bg-amber-400/20 text-amber-300 border border-amber-400/30 text-[10px] font-bold">
                      ★ {averageRating.toFixed(1)} ({reviews.length} đánh giá)
                    </span>
                  )}
                  <span className="px-2.5 py-0.5 rounded-full bg-white/15 backdrop-blur-md text-zinc-200 text-[10px] font-bold">
                    {venue.courts?.length || 0} sân thi đấu
                  </span>
                  {distanceKm !== null && (
                    <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/25 border border-emerald-400/30 text-emerald-300 text-[10px] font-black inline-flex items-center">
                      Cách bạn {distanceKm.toFixed(1)} km
                    </span>
                  )}
                </div>

                <h1 className="text-xl sm:text-3xl font-black text-white">{venue.name}</h1>
                <p className="text-xs text-zinc-300 mt-1 max-w-xl">
                  {venue.address}
                </p>

                <div className="mt-3 flex items-center gap-2">
                  <a
                    href={mapDirectionUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/15 hover:bg-white/25 border border-white/20 text-white text-xs font-semibold backdrop-blur-md transition"
                  >
                    <span>Chỉ Đường Google Maps →</span>
                  </a>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left / Center Column: Date Picker & Interactive Slots Grid */}
          <div className="lg:col-span-2 space-y-5">
            {/* Modern Mini Calendar Month Grid & Shortcuts */}
            <div className="bg-white rounded-2xl p-5 sm:p-6 border border-zinc-200/80 shadow-xs space-y-4">
              {/* Header & Quick Reset */}
              <div className="flex items-center justify-between gap-3 pb-3.5 border-b border-zinc-100">
                <div className="flex items-center gap-2.5">
                  <span className="font-bold text-sm text-zinc-900 uppercase tracking-wider">
                    1. Chọn Ngày Đặt Sân:
                  </span>
                  <span className="px-3 py-1.5 rounded-xl bg-zinc-950 text-white text-xs sm:text-sm font-black shadow-xs">
                    {selectedDate}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => handleQuickSelect("today")}
                  className={`px-4 py-2 rounded-xl text-xs sm:text-sm font-bold border transition cursor-pointer ${
                    selectedDate === todayStr
                      ? "bg-zinc-950 text-white border-zinc-950 shadow-xs"
                      : "bg-zinc-100 hover:bg-zinc-200 text-zinc-800 border-zinc-200"
                  }`}
                >
                  Hôm nay
                </button>
              </div>

              {/* Month Navigation & Grid (Enlarged) */}
              <div className="bg-zinc-50/80 p-4 sm:p-5 rounded-2xl border border-zinc-200/80">
                {/* Month & Year Jump Dropdown Controls */}
                <div className="flex items-center justify-between mb-4 px-1 gap-2">
                  <button
                    type="button"
                    onClick={handlePrevMonth}
                    disabled={!canGoPrevMonth}
                    className="w-10 h-10 rounded-xl flex items-center justify-center border border-zinc-200 bg-white hover:bg-zinc-100 text-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition text-sm font-bold shadow-2xs"
                    title="Tháng trước"
                  >
                    ◀
                  </button>

                  <div className="flex items-center gap-2">
                    {/* Month Dropdown */}
                    <select
                      value={currentMonth}
                      onChange={(e) => {
                        const m = parseInt(e.target.value);
                        setCalendarDate(new Date(currentYear, m, 1));
                      }}
                      className="px-3 py-2 text-sm sm:text-base font-extrabold rounded-xl border border-zinc-300 bg-white text-zinc-950 focus:outline-none focus:border-zinc-950 cursor-pointer shadow-2xs"
                    >
                      {Array.from({ length: 12 }, (_, idx) => (
                        <option key={idx} value={idx}>
                          Tháng {idx + 1}
                        </option>
                      ))}
                    </select>

                    {/* Year Dropdown */}
                    <select
                      value={currentYear}
                      onChange={(e) => {
                        const y = parseInt(e.target.value);
                        setCalendarDate(new Date(y, currentMonth, 1));
                      }}
                      className="px-3 py-2 text-sm sm:text-base font-extrabold rounded-xl border border-zinc-300 bg-white text-zinc-950 focus:outline-none focus:border-zinc-950 cursor-pointer shadow-2xs"
                    >
                      {[new Date().getFullYear(), new Date().getFullYear() + 1].map((y) => (
                        <option key={y} value={y}>
                          Năm {y}
                        </option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="button"
                    onClick={handleNextMonth}
                    disabled={!canGoNextMonth}
                    className="w-10 h-10 rounded-xl flex items-center justify-center border border-zinc-200 bg-white hover:bg-zinc-100 text-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition text-sm font-bold shadow-2xs"
                    title="Tháng sau"
                  >
                    ▶
                  </button>
                </div>

                {/* Day of Week Headers */}
                <div className="grid grid-cols-7 gap-1.5 text-center mb-2">
                  {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((dw, idx) => (
                    <span
                      key={dw}
                      className={`text-xs sm:text-sm font-bold py-1 ${idx >= 5 ? "text-amber-700 font-black" : "text-zinc-500"}`}
                    >
                      {dw}
                    </span>
                  ))}
                </div>

                {/* Days Matrix (Large Touch Targets) */}
                <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
                  {/* Empty cells for offset */}
                  {Array.from({ length: firstDayOfWeek }).map((_, i) => (
                    <div key={`empty-${i}`} className="h-11 sm:h-13" />
                  ))}

                  {/* Month days */}
                  {Array.from({ length: daysInMonth }).map((_, i) => {
                    const dayNum = i + 1;
                    const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
                    const isSelected = selectedDate === dateStr;
                    const isPast = dateStr < todayStr;
                    const isTooFar = dateStr > lastBookableStr;
                    const isToday = dateStr === todayStr;

                    return (
                      <button
                        key={dateStr}
                        type="button"
                        disabled={isPast || isTooFar}
                        onClick={() => handleSelectDate(dateStr)}
                        title={isTooFar ? `Chỉ đặt trước tối đa ${MAX_ADVANCE_DAYS} ngày` : undefined}
                        className={`h-11 sm:h-13 rounded-xl text-xs sm:text-sm flex flex-col items-center justify-center transition-all cursor-pointer relative ${
                          isSelected
                            ? "bg-zinc-950 text-white font-black shadow-md ring-2 ring-zinc-950 ring-offset-2 scale-105 z-10"
                            : isPast || isTooFar
                            ? "text-zinc-300 bg-transparent cursor-not-allowed"
                            : "bg-white hover:bg-zinc-100 text-zinc-900 font-bold border border-zinc-200/90 hover:border-zinc-400 shadow-2xs"
                        }`}
                      >
                        <span className="leading-none text-sm sm:text-base font-bold">{dayNum}</span>
                        {isToday && (
                          <span
                            className={`w-1.5 h-1.5 rounded-full mt-1 ${
                              isSelected ? "bg-white" : "bg-emerald-500"
                            }`}
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Time Slot Availability Matrix */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-zinc-200/80 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3.5 pb-2.5 border-b border-zinc-100">
                <h2 className="font-semibold text-xs text-zinc-500 uppercase tracking-wider">
                  2. Chọn Khung Giờ
                </h2>
                <div className="flex items-center gap-3.5 text-xs text-zinc-600 font-medium">
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded bg-white border border-zinc-300 inline-block shadow-2xs" />
                    Trống
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded bg-amber-100 border border-amber-300 inline-block" />
                    Đang giữ
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded bg-zinc-200 border border-zinc-300 inline-block" />
                    Đã đặt / đã qua
                  </span>
                </div>
              </div>

              {availability.length === 0 ? (
                <div className="text-center py-10 text-zinc-400">
                  <p className="font-medium text-xs text-zinc-600">Cụm sân không mở cửa vào ngày này</p>
                  <p className="text-[11px] mt-0.5">Vui lòng chọn một ngày khác.</p>
                </div>
              ) : (
                <div className="space-y-3.5">
                  {availability.map((court) => (
                    <div key={court.court_id} className="p-3.5 rounded-xl bg-zinc-50/70 border border-zinc-200/70">
                      <div className="flex items-center justify-between mb-2.5">
                        <span className="font-bold text-xs text-zinc-900">
                          {court.court_name}
                        </span>
                        <span className="text-[10px] text-zinc-500 bg-white px-2 py-0.5 rounded border border-zinc-200">
                          {court.slots.filter(s => s.is_available).length} giờ trống
                        </span>
                      </div>

                      {/* Time Chips Grid */}
                      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-1.5">
                        {court.slots.map((slot, sIdx) => {
                          const isSelected = selectedSlots.some(
                            (s) => s.court_id === court.court_id && s.start_time === slot.start_time
                          );
                          const isHeldByOther = slot.is_held && !isSelected;

                          return (
                            <button
                              key={sIdx}
                              disabled={!slot.is_available || isHeldByOther}
                              onClick={() =>
                                toggleSlot(
                                  court.court_id,
                                  court.court_name,
                                  slot.start_time,
                                  slot.end_time,
                                  slot.price
                                )
                              }
                              title={
                                slot.is_past
                                  ? "Khung giờ đã qua"
                                  : isHeldByOther
                                  ? "Đang có người khác giữ tạm khung giờ này"
                                  : !slot.is_available
                                  ? "Đã có người đặt"
                                  : undefined
                              }
                              className={`p-1.5 rounded-lg text-center text-xs transition-all flex flex-col items-center justify-center cursor-pointer ${
                                !slot.is_available
                                  ? "bg-zinc-100 text-zinc-400 border border-zinc-200/80 cursor-not-allowed line-through"
                                  : isHeldByOther
                                  ? "bg-amber-50/90 text-amber-900 border border-amber-300/80 cursor-not-allowed shadow-xs"
                                  : isSelected
                                  ? "bg-zinc-900 text-white font-semibold border border-zinc-900 shadow-xs"
                                  : "bg-white text-zinc-800 font-medium border border-zinc-200 hover:border-zinc-400 hover:bg-zinc-50"
                              }`}
                            >
                              <span className="text-xs font-semibold flex items-center gap-1">
                                {isHeldByOther && <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />}
                                <span>{slot.start_time.slice(0, 5)} - {slot.end_time.slice(0, 5)}</span>
                              </span>
                              <span
                                className={`text-[10px] ${
                                  isSelected
                                    ? "text-zinc-300 font-bold"
                                    : isHeldByOther
                                    ? "text-amber-700 font-medium"
                                    : "text-zinc-500"
                                }`}
                              >
                                {slot.is_past
                                  ? "Đã qua"
                                  : isHeldByOther
                                  ? "Đang giữ"
                                  : !slot.is_available
                                  ? "Đã đặt"
                                  : `${(slot.price / 1000).toFixed(0)}k`}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Thông tin cụm sân */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-zinc-200/80 shadow-xs space-y-4">
              <h2 className="font-semibold text-xs text-zinc-500 uppercase tracking-wider">Thông Tin Cụm Sân</h2>
              {venue.description && <p className="text-sm text-zinc-700 leading-relaxed">{venue.description}</p>}

              {(venue.amenities || []).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {venue.amenities.map((amenity: any) => (
                    <span
                      key={amenity.id}
                      className="px-2.5 py-1 rounded-full bg-zinc-100 border border-zinc-200 text-[11px] font-medium text-zinc-700"
                    >
                      {amenity.name}
                    </span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                <div>
                  <p className="font-semibold text-zinc-900 mb-1.5">Giờ mở cửa</p>
                  <ul className="space-y-0.5 text-zinc-600">
                    {WEEKDAY_NAMES.map((name, day) => (
                      <li key={day} className="flex justify-between">
                        <span>{name}</span>
                        <span className="font-medium text-zinc-800">
                          {hoursByDay[day]
                            ? `${hoursByDay[day].open_time.slice(0, 5)} - ${hoursByDay[day].close_time.slice(0, 5)}`
                            : "Nghỉ"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-semibold text-zinc-900 mb-1.5">Bảng giá mỗi giờ</p>
                  {(venue.price_rules || []).length === 0 ? (
                    <p className="text-zinc-500">Cụm sân chưa công bố bảng giá.</p>
                  ) : (
                    <ul className="space-y-0.5 text-zinc-600">
                      {venue.price_rules.map((rule: any) => (
                        <li key={rule.id} className="flex justify-between">
                          <span>
                            {PRICE_RULE_LABEL[rule.rule_type] || rule.rule_type}
                            {rule.rule_type === "PEAK" && rule.start_time && rule.end_time
                              ? ` (${rule.start_time.slice(0, 5)} - ${rule.end_time.slice(0, 5)})`
                              : ""}
                          </span>
                          <span className="font-medium text-zinc-800">{formatVND(rule.price)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>

            {/* Đánh giá của người đã chơi */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-zinc-200/80 shadow-xs space-y-3.5">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-xs text-zinc-500 uppercase tracking-wider">Đánh Giá</h2>
                <span className="text-xs text-zinc-600">
                  {averageRating !== null
                    ? `★ ${averageRating.toFixed(1)} / 5 • ${reviews.length} đánh giá`
                    : "Chưa có đánh giá"}
                </span>
              </div>

              {reviews.length > 0 && (
                <ul className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                  {reviews.map((review) => (
                    <li key={review.id} className="p-3 rounded-lg bg-zinc-50 border border-zinc-100 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-zinc-900">{review.author_name}</span>
                        <span className="text-amber-600 font-bold">{"★".repeat(Math.round(review.rating))}</span>
                      </div>
                      {review.comment && <p className="text-zinc-600 mt-1 leading-relaxed">{review.comment}</p>}
                    </li>
                  ))}
                </ul>
              )}

              {user?.role === "PLAYER" && (
                <form onSubmit={submitReview} className="pt-3 border-t border-zinc-100 space-y-2">
                  <p className="text-[11px] text-zinc-500">
                    Bạn có thể đánh giá sau khi đã chơi xong ít nhất một lượt tại cụm sân này.
                  </p>
                  <div className="flex items-center gap-2">
                    <select
                      value={reviewForm.rating}
                      onChange={(e) => setReviewForm({ ...reviewForm, rating: Number(e.target.value) })}
                      className="px-2.5 py-2 rounded-lg border border-zinc-200 text-xs bg-white"
                      aria-label="Số sao"
                    >
                      {[5, 4, 3, 2, 1].map((star) => (
                        <option key={star} value={star}>
                          {star} sao
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      maxLength={1000}
                      value={reviewForm.comment}
                      onChange={(e) => setReviewForm({ ...reviewForm, comment: e.target.value })}
                      placeholder="Nhận xét của bạn (không bắt buộc)"
                      className="flex-1 px-3 py-2 rounded-lg border border-zinc-200 text-xs focus:outline-none focus:border-zinc-900"
                    />
                    <button
                      type="submit"
                      disabled={sendingReview}
                      className="px-3.5 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-white text-xs font-medium disabled:opacity-60 cursor-pointer"
                    >
                      {sendingReview ? "Đang gửi..." : "Gửi"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>

          {/* Right Column: Desktop Booking Summary */}
          <div className="hidden lg:block lg:col-span-1">
            <div className="sticky top-20 bg-white rounded-xl p-5 border border-zinc-200/80 shadow-xs">
              <div className="flex items-center justify-between mb-3 pb-2 border-b border-zinc-100">
                <h2 className="font-semibold text-xs text-zinc-500 uppercase tracking-wider">
                  Thông Tin Đặt Sân
                </h2>
                <span className="text-[10px] text-zinc-600 bg-zinc-100 px-1.5 py-0.2 rounded font-medium">
                  Giữ tạm 5 phút
                </span>
              </div>

              {selectedSlots.length === 0 ? (
                <div className="text-center py-6 text-zinc-400">
                  <p className="text-xs text-zinc-600 font-medium">Chưa chọn khung giờ nào</p>
                  <p className="text-[11px] text-zinc-400 mt-0.5">Bấm chọn các ô giờ trống trên bảng để giữ sân.</p>
                </div>
              ) : (
                <div className="space-y-3.5">
                  <div className="max-h-56 overflow-y-auto space-y-1.5 pr-0.5">
                    {selectedSlots.map((slot, i) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-zinc-50 border border-zinc-100 text-xs">
                        <div>
                          <p className="font-semibold text-zinc-900">{slot.court_name}</p>
                          <p className="text-[10px] text-zinc-500">
                            {selectedDate} • {slot.start_time.slice(0, 5)} - {slot.end_time.slice(0, 5)}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-zinc-900">{formatVND(slot.price)}</span>
                          <button
                            onClick={() => toggleSlot(slot.court_id, slot.court_name, slot.start_time, slot.end_time, slot.price)}
                            className="text-zinc-400 hover:text-rose-600 font-bold px-1 cursor-pointer"
                          >
                            ✕
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="pt-2.5 border-t border-zinc-100 space-y-1.5 text-xs">
                    <div className="flex justify-between items-center text-zinc-500">
                      <span>Đã chọn:</span>
                      <span className="font-semibold text-zinc-900">{selectedSlots.length} slot</span>
                    </div>
                    <div className="flex justify-between items-center text-zinc-600">
                      <span>Tổng tiền thuê:</span>
                      <span className="font-bold text-zinc-900">{formatVND(totalPrice)}</span>
                    </div>
                    <div className="flex justify-between items-center p-2 rounded-lg bg-emerald-50/70 border border-emerald-200/80 text-emerald-950 font-medium">
                      <span>Tiền cọc trước (50%):</span>
                      <span className="font-bold text-emerald-700">{formatVND(Math.round(totalPrice * 0.5))}</span>
                    </div>
                    <div className="flex justify-between items-center text-[11px] text-zinc-500">
                      <span>Còn lại thanh toán tại sân:</span>
                      <span className="font-semibold text-zinc-800">{formatVND(totalPrice - Math.round(totalPrice * 0.5))}</span>
                    </div>
                  </div>

                  {user ? (
                    <button
                      onClick={handleBooking}
                      disabled={booking}
                      className="w-full py-2.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-white font-medium text-xs transition-all btn-press disabled:opacity-60 cursor-pointer shadow-xs"
                    >
                      {booking ? "Đang tạo đơn..." : "Đặt Sân & Thanh Toán Cọc 50% →"}
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        toastInfo("Vui lòng đăng nhập để tiến hành đặt sân và thanh toán cọc 50%!");
                        router.push(loginUrl);
                      }}
                      className="w-full py-2.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white font-medium text-xs transition-all btn-press cursor-pointer shadow-xs flex items-center justify-center gap-1.5"
                    >
                      <span>Đăng Nhập Để Đặt Sân & Cọc 50%</span>
                    </button>
                  )}

                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Sticky Bottom Bar for Mobile Booking */}
      {selectedSlots.length > 0 && (
        <div className="lg:hidden fixed bottom-14 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-zinc-200 p-3 shadow-lg">
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
            <div>
              <p className="text-[10px] text-zinc-500 uppercase font-medium">
                {selectedSlots.length} khung giờ đã chọn
              </p>
              <p className="text-base font-bold text-zinc-900">
                {formatVND(totalPrice)}
              </p>
            </div>
            <button
              onClick={handleBooking}
              disabled={booking}
              className="px-5 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-white font-medium text-xs btn-press shrink-0 cursor-pointer"
            >
              {booking ? "Đang xử lý..." : "Đặt Sân Ngay →"}
            </button>
          </div>
        </div>
      )}

      {/* SePay Automated VietQR Checkout Modal */}
      {checkoutBookingId && (
        <SepayCheckoutModal
          bookingId={checkoutBookingId}
          isOpen={!!checkoutBookingId}
          onClose={(wasPaid) => {
            setCheckoutBookingId(null);
            if (wasPaid) {
              router.push("/bookings?tab=upcoming");
            } else {
              router.push("/bookings?tab=pending");
            }
          }}
          onPaymentSuccess={() => {
            loadAvailability(selectedDate);
          }}
        />
      )}

      {/* Rich Interactive Footer */}
      <Footer />
    </div>
  );
}

