"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { fetchApi, formatVND } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWebSocket } from "@/lib/use-websocket";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import VenueImageHoverSlider from "@/components/VenueImageHoverSlider";
import LocationPickerModal from "@/components/LocationPickerModal";
import {
  UserLocation,
  getSavedLocation,
  getGoogleMapsUrl,
  saveLocation,
} from "@/lib/location";

interface Recommendation {
  venue: any;
  score: number;
  distance_score: number | null;
  price_score: number | null;
  time_score: number;
  rating_score: number;
  preference_score: number | null;
  distance_km: number | null;
  avg_price: number | null;
  avg_rating: number | null;
  review_count: number;
  free_slots: number;
  total_slots: number;
}

const WEEKDAY_INDEX = (new Date().getDay() + 6) % 7; // 0 = Thứ Hai, khớp day_of_week của máy chủ

export default function HomePage() {
  const { user } = useAuth();
  const [keyword, setKeyword] = useState("");
  const [venues, setVenues] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false);

  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  // Gợi ý theo điểm đa tiêu chí (khoảng cách, giá, giờ trống, đánh giá, tiện ích ưa thích)
  const loadRecommendations = async (coords?: { lat: number; lng: number }) => {
    try {
      const params = new URLSearchParams({ top_n: "3" });
      if (coords) {
        params.append("latitude", coords.lat.toString());
        params.append("longitude", coords.lng.toString());
      }
      const data = await fetchApi(`/recommendations/venues?${params.toString()}`);
      setRecommendations(Array.isArray(data) ? data : []);
    } catch {
      setRecommendations([]);
    }
  };

  // Load venues based on keyword and coordinates
  const loadVenues = async (searchKeyword = "", coords?: { lat: number; lng: number }) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchKeyword) params.append("keyword", searchKeyword);
      
      const activeCoords = coords || (userLocation ? { lat: userLocation.lat, lng: userLocation.lng } : undefined);
      if (activeCoords) {
        params.append("latitude", activeCoords.lat.toString());
        params.append("longitude", activeCoords.lng.toString());
      }
      
      const qs = params.toString() ? `?${params.toString()}` : "";
      const data = await fetchApi(`/search/venues${qs}`);
      setVenues(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Vị trí: ưu tiên nơi người dùng vừa chọn, rồi tới hồ sơ. Chưa có thì KHÔNG giả định vị trí nào.
  useEffect(() => {
    const saved = getSavedLocation();
    const profile = user?.player_profile;
    let initialLoc: UserLocation | null = null;
    if (saved) {
      initialLoc = saved;
    } else if (profile?.latitude != null && profile?.longitude != null) {
      initialLoc = { name: "Vị trí trong hồ sơ", lat: profile.latitude, lng: profile.longitude, isGps: false };
    }

    setUserLocation(initialLoc);
    const coords = initialLoc ? { lat: initialLoc.lat, lng: initialLoc.lng } : undefined;
    loadVenues(keyword, coords);
    loadRecommendations(coords);
  }, [user]);

  // Số khung giờ trống thay đổi khi có người đặt/hủy: làm mới phần gợi ý
  useEffect(() => {
    if (!lastMessage || !["SLOT_BOOKED", "SLOT_RELEASED"].includes(lastMessage.type)) return;
    loadRecommendations(userLocation ? { lat: userLocation.lat, lng: userLocation.lng } : undefined);
  }, [lastMessage]);

  const handleSelectLocation = (loc: UserLocation) => {
    saveLocation(loc);
    setUserLocation(loc);
    loadVenues(keyword, { lat: loc.lat, lng: loc.lng });
    loadRecommendations({ lat: loc.lat, lng: loc.lng });
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadVenues(keyword);
  };

  const [selectedDistrict, setSelectedDistrict] = useState("all");

  const ALL_DISTRICTS = [
    { id: "all", name: "Tất cả khu vực TP.HCM", label: "Tất cả", keywords: [] },
    { id: "govap", name: "Quận Gò Vấp", label: "Gò Vấp", keywords: ["gò vấp"] },
    { id: "thuduc", name: "TP. Thủ Đức", label: "Thủ Đức", keywords: ["thủ đức", "quận 2", "quận 9", "an khánh", "thảo điền", "thủ thiêm", "hiệp bình", "linh trung", "linh tây"] },
    { id: "q1", name: "Quận 1", label: "Quận 1", keywords: ["quận 1,", "quận 1 ", "bến thành", "bến nghé", "đakao"] },
    { id: "q3", name: "Quận 3", label: "Quận 3", keywords: ["quận 3"] },
    { id: "q4", name: "Quận 4", label: "Quận 4", keywords: ["quận 4"] },
    { id: "q5", name: "Quận 5", label: "Quận 5", keywords: ["quận 5"] },
    { id: "q6", name: "Quận 6", label: "Quận 6", keywords: ["quận 6"] },
    { id: "q7", name: "Quận 7", label: "Quận 7", keywords: ["quận 7", "tân thuận", "tân phong", "phú mỹ hưng"] },
    { id: "q8", name: "Quận 8", label: "Quận 8", keywords: ["quận 8"] },
    { id: "q10", name: "Quận 10", label: "Quận 10", keywords: ["quận 10", "cách mạng tháng 8"] },
    { id: "q11", name: "Quận 11", label: "Quận 11", keywords: ["quận 11"] },
    { id: "q12", name: "Quận 12", label: "Quận 12", keywords: ["quận 12", "an phú đông", "tân chánh hiệp"] },
    { id: "binhthanh", name: "Quận Bình Thạnh", label: "Bình Thạnh", keywords: ["bình thạnh"] },
    { id: "tanbinh", name: "Quận Tân Bình", label: "Tân Bình", keywords: ["tân bình", "cộng hòa"] },
    { id: "tanphu", name: "Quận Tân Phú", label: "Tân Phú", keywords: ["tân phú", "chế lan viên"] },
    { id: "phunhuan", name: "Quận Phú Nhuận", label: "Phú Nhuận", keywords: ["phú nhuận", "hoa phượng"] },
    { id: "binhtan", name: "Quận Bình Tân", label: "Bình Tân", keywords: ["bình tân", "tên lửa"] },
    { id: "binhchanh", name: "Huyện Bình Chánh", label: "Bình Chánh", keywords: ["bình chánh"] },
    { id: "hocmon", name: "Huyện Hóc Môn", label: "Hóc Môn", keywords: ["hóc môn"] },
    { id: "cuchi", name: "Huyện Củ Chi", label: "Củ Chi", keywords: ["củ chi"] },
    { id: "nhabe", name: "Huyện Nhà Bè", label: "Nhà Bè", keywords: ["nhà bè"] },
    { id: "cangio", name: "Huyện Cần Giờ", label: "Cần Giờ", keywords: ["cần giờ"] },
  ];

  // Dynamic District/Area Venue Counts
  const districtCounts = useMemo(() => {
    const counts: Record<string, number> = { all: venues.length };
    ALL_DISTRICTS.forEach((d) => {
      if (d.id === "all") return;
      const count = venues.filter((v) => {
        const text = `${v.address || ""} ${v.name || ""}`.toLowerCase();
        return d.keywords.some((kw) => text.includes(kw));
      }).length;
      counts[d.id] = count;
    });
    return counts;
  }, [venues]);

  // Filter venues by selected district
  const filteredVenues = useMemo(() => {
    if (selectedDistrict === "all") return venues;
    const targetDistrict = ALL_DISTRICTS.find((d) => d.id === selectedDistrict);
    if (!targetDistrict || targetDistrict.keywords.length === 0) return venues;

    return venues.filter((v) => {
      const text = `${v.address || ""} ${v.name || ""}`.toLowerCase();
      return targetDistrict.keywords.some((kw) => text.includes(kw));
    });
  }, [venues, selectedDistrict]);

  const handleResetFilters = () => {
    setSelectedDistrict("all");
    setKeyword("");
    loadVenues("");
  };

  const [detailModalVenue, setDetailModalVenue] = useState<any | null>(null);

  // Chỉ hiển thị thông tin cụm sân thật sự có trong hệ thống; thiếu thì nói là chưa có
  const getVenueDetails = (v: any) => {
    const today = (v.operating_hours || []).find((h: any) => h.day_of_week === WEEKDAY_INDEX);
    return {
      description: v.description || "",
      amenities: (Array.isArray(v.amenities) ? v.amenities : []).map((a: any) => a.name).filter(Boolean) as string[],
      openHours: today ? `Hôm nay mở ${today.open_time.slice(0, 5)} - ${today.close_time.slice(0, 5)}` : "Hôm nay nghỉ",
      courtCount: v.courts?.length || 0,
    };
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900 selection:bg-zinc-900 selection:text-white">
      <Navbar />

      {/* Hero Section with Court Photo Background */}
      <section className="relative overflow-hidden bg-zinc-950 py-16 sm:py-24 px-4 sm:px-6">
        {/* Background Court Image */}
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/images/hero_bg.jpg')" }}
        />
        {/* Sleek Dark Gradient Overlay for Readability */}
        <div className="absolute inset-0 bg-gradient-to-b from-zinc-950/80 via-zinc-950/65 to-zinc-950/85 backdrop-blur-[1px]" />

        <div className="max-w-5xl mx-auto text-center space-y-6 relative z-10">
          <h1 className="text-2xl sm:text-4xl md:text-5xl font-black text-white tracking-tight leading-tight drop-shadow-md">
            Đặt Sân & Ghép Trận Pickleball Thông Minh
          </h1>

          {/* Large & Wide Search Box */}
          <form
            onSubmit={handleSearch}
            className="mt-6 bg-white/95 backdrop-blur-md rounded-2xl sm:rounded-full p-2 sm:p-2.5 border border-white/30 shadow-2xl flex flex-col sm:flex-row items-stretch gap-2 focus-within:border-white transition-all max-w-4xl mx-auto"
          >
            <div className="flex-1 flex items-center px-4 sm:px-6">
              <input
                type="text"
                placeholder="Tìm tên sân, đường, quận tại TP.HCM..."
                className="w-full py-3 sm:py-3.5 text-sm sm:text-lg text-zinc-900 placeholder-zinc-500 focus:outline-none bg-transparent font-medium"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>

            <button
              type="submit"
              className="bg-zinc-950 hover:bg-zinc-800 text-white px-8 sm:px-10 py-3 sm:py-3.5 rounded-xl sm:rounded-full font-black text-sm sm:text-base transition-all btn-press shrink-0 cursor-pointer shadow-md"
            >
              Tìm Sân
            </button>
          </form>

        </div>
      </section>

      {/* Venues Listing & Simple District Filter */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {/* Vị trí đang dùng để tính khoảng cách */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm bg-white border border-zinc-200 rounded-2xl px-4 py-3">
          <span className="text-zinc-600">
            {userLocation ? (
              <>
                Khoảng cách tính từ: <strong className="text-zinc-950">{userLocation.name}</strong>
              </>
            ) : (
              "Chưa có vị trí của bạn nên chưa tính được khoảng cách tới các cụm sân."
            )}
          </span>
          <button
            type="button"
            onClick={() => setIsLocationModalOpen(true)}
            className="px-3.5 py-1.5 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs font-bold cursor-pointer"
          >
            {userLocation ? "Đổi vị trí" : "Chọn vị trí"}
          </button>
        </div>

        {/* Gợi ý theo điểm đa tiêu chí */}
        {recommendations.length > 0 && (
          <div className="mb-8">
            <h2 className="text-xl sm:text-2xl font-black text-zinc-950 tracking-tight">Gợi Ý Cho Bạn Hôm Nay</h2>
            <p className="text-xs text-zinc-500 mt-1 mb-4">
              Xếp hạng theo khoảng cách, giá, số khung giờ còn trống, đánh giá và tiện ích bạn ưu tiên. Tiêu chí chưa có
              dữ liệu (ví dụ chưa chọn vị trí) không được tính.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {recommendations.map((rec, index) => (
                <Link
                  key={rec.venue.id}
                  href={`/venues/${rec.venue.id}`}
                  className="bg-white rounded-2xl border border-zinc-200/90 shadow-xs hover:shadow-md transition p-4 space-y-2.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-black text-zinc-950 text-sm leading-snug">
                      <span className="text-zinc-400 mr-1.5">#{index + 1}</span>
                      {rec.venue.name}
                    </p>
                    <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-zinc-900 text-white shrink-0">
                      {(rec.score * 100).toFixed(0)} điểm
                    </span>
                  </div>
                  <ul className="text-[11px] text-zinc-600 space-y-1">
                    <ScoreRow label="Khoảng cách" score={rec.distance_score} detail={rec.distance_km != null ? `${rec.distance_km} km` : "chưa có vị trí"} />
                    <ScoreRow label="Giá" score={rec.price_score} detail={rec.avg_price != null ? `${formatVND(rec.avg_price)}/giờ` : "chưa có giá"} />
                    <ScoreRow label="Giờ trống" score={rec.time_score} detail={`${rec.free_slots}/${rec.total_slots} khung`} />
                    <ScoreRow label="Đánh giá" score={rec.rating_score} detail={rec.review_count > 0 ? `${rec.avg_rating?.toFixed(1)} (${rec.review_count})` : "chưa có đánh giá"} />
                    <ScoreRow label="Tiện ích ưu tiên" score={rec.preference_score} detail={rec.preference_score == null ? "chưa khai trong hồ sơ" : ""} />
                  </ul>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Simple & Clean District Filter Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-2">
            <h2 className="text-xl sm:text-2xl font-black text-zinc-950 tracking-tight">
              Danh Sách Cụm Sân
            </h2>
            <span className="text-xs font-black text-zinc-600 bg-zinc-100 border border-zinc-200 px-2.5 py-0.5 rounded-full">
              {filteredVenues.length}
            </span>
          </div>

          {/* District Dropdown Selector */}
          <div className="relative shrink-0">
            <select
              value={selectedDistrict}
              onChange={(e) => setSelectedDistrict(e.target.value)}
              className="bg-white border-2 border-zinc-950 text-zinc-950 font-bold text-xs sm:text-sm rounded-xl px-4 py-2.5 pr-9 focus:outline-none focus:ring-2 focus:ring-zinc-950 cursor-pointer shadow-xs appearance-none transition"
            >
              <option value="all">Tất cả khu vực TP.HCM ({venues.length})</option>
              {ALL_DISTRICTS.filter((d) => d.id !== "all").map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} {districtCounts[d.id] > 0 ? `(${districtCounts[d.id]} sân)` : ""}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-zinc-900 font-bold">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {[1, 2].map((i) => (
              <div key={i} className="bg-white rounded-3xl p-8 border border-zinc-200 animate-pulse space-y-4">
                <div className="h-6 bg-zinc-100 rounded-lg w-3/4" />
                <div className="h-4 bg-zinc-100 rounded-lg w-1/2" />
                <div className="h-12 bg-zinc-100 rounded-2xl mt-4" />
              </div>
            ))}
          </div>
        ) : filteredVenues.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-3xl border border-zinc-200 shadow-sm space-y-3">
            <p className="text-sm font-bold text-zinc-700">
              Hiện chưa có cụm sân nào tại{" "}
              <strong className="text-zinc-950 font-black">
                {ALL_DISTRICTS.find((d) => d.id === selectedDistrict)?.name || "khu vực này"}
              </strong>
            </p>
            <p className="text-xs text-zinc-500 max-w-md mx-auto">
              Bạn có thể chọn khu vực lân cận hoặc bấm bên dưới để khám phá tất cả các cụm sân đang hoạt động tại TP.HCM.
            </p>
            <button
              type="button"
              onClick={handleResetFilters}
              className="mt-2 px-5 py-2.5 bg-zinc-950 text-white rounded-xl text-xs sm:text-sm font-bold cursor-pointer btn-press transition shadow-xs"
            >
              Xem Tất Cả Sân TP.HCM ({venues.length})
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 sm:gap-8">
            {filteredVenues.map((venue) => {
              const baseRule = venue.price_rules?.find((r: any) => r.rule_type === "BASE");
              const mapDirUrl = getGoogleMapsUrl(venue);

              return (
                <div
                  key={venue.id}
                  className="bg-white rounded-3xl border border-zinc-200/90 shadow-sm hover:shadow-md transition-all overflow-hidden flex flex-col justify-between group"
                >
                  {/* Interactive Auto-cycling Venue Image Hover Slider */}
                  <VenueImageHoverSlider
                    venue={venue}
                    className="h-48 sm:h-56"
                    showBadges={true}
                    showDistance={true}
                    isLoggedIn={!!user}
                  />

                  <div className="p-6 sm:p-7 flex-1 flex flex-col justify-between">
                    <div>
                      <p className="text-xs sm:text-sm text-zinc-600 leading-relaxed line-clamp-2">
                        {venue.address}
                      </p>
                    </div>

                    {/* Pricing & CTA Buttons */}
                    <div className="mt-5 pt-4 border-t border-zinc-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <span className="text-[10px] text-zinc-400 block font-bold uppercase tracking-wider">
                          Giá thuê từ
                        </span>
                        {baseRule ? (
                          <span className="text-lg sm:text-xl font-black text-zinc-950">
                            {formatVND(baseRule.price)}
                            <span className="text-xs font-normal text-zinc-500"> / giờ</span>
                          </span>
                        ) : (
                          <span className="text-base font-black text-zinc-500">Chưa công bố</span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                        <button
                          type="button"
                          onClick={() => setDetailModalVenue(venue)}
                          className="px-3 py-2 bg-zinc-100 hover:bg-zinc-200 border border-zinc-200 rounded-xl text-xs font-bold text-zinc-800 transition cursor-pointer text-center"
                        >
                          Chi Tiết
                        </button>
                        <a
                          href={mapDirUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-2 bg-zinc-100 hover:bg-zinc-200 border border-zinc-200 rounded-xl text-xs font-bold text-zinc-800 transition cursor-pointer text-center"
                        >
                          Bản đồ
                        </a>
                        <Link
                          href={`/venues/${venue.id}`}
                          className="px-4 py-2 bg-zinc-950 hover:bg-zinc-800 text-white rounded-xl text-xs font-bold transition btn-press cursor-pointer shadow-xs text-center whitespace-nowrap"
                        >
                          Đặt Sân Ngay
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Interactive Venue Details & Amenities Modal */}
      {detailModalVenue && (() => {
        const details = getVenueDetails(detailModalVenue);
        const mapUrl = getGoogleMapsUrl(detailModalVenue);

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/60 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-2xl w-full shadow-2xl border border-zinc-200 max-h-[85vh] flex flex-col">
              {/* Header */}
              <div className="flex items-start justify-between pb-4 border-b border-zinc-100 shrink-0">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="px-2.5 py-0.5 rounded-md bg-zinc-100 text-zinc-800 text-[11px] font-bold">
                      {details.openHours}
                    </span>
                    <span className="px-2.5 py-0.5 rounded-md bg-zinc-950 text-white text-[11px] font-bold">
                      {details.courtCount} sân
                    </span>
                  </div>
                  <h3 className="text-xl sm:text-2xl font-black text-zinc-950">
                    {detailModalVenue.name}
                  </h3>
                  <p className="text-xs sm:text-sm text-zinc-500 mt-1">
                    {detailModalVenue.address}
                  </p>
                </div>

                <button
                  onClick={() => setDetailModalVenue(null)}
                  className="w-8 h-8 rounded-full bg-zinc-100 hover:bg-zinc-200 flex items-center justify-center text-zinc-600 font-bold text-sm cursor-pointer shrink-0 ml-2"
                >
                  ✕
                </button>
              </div>

              {/* Scrollable Content */}
              <div className="overflow-y-auto py-5 pr-1 space-y-6 flex-1 text-zinc-700">
                {/* Venue Photo Banner with Auto Slideshow */}
                <div className="w-full rounded-2xl overflow-hidden shadow-xs">
                  <VenueImageHoverSlider
                    venue={detailModalVenue}
                    className="h-56 sm:h-72"
                    showBadges={true}
                    showDistance={false}
                    isLoggedIn={false}
                  />
                </div>

                {/* Introduction Section */}
                <div>
                  <h4 className="text-xs sm:text-sm font-black text-zinc-950 uppercase tracking-wider mb-2">
                    Giới Thiệu Cụm Sân
                  </h4>
                  <p className="text-xs sm:text-sm text-zinc-600 leading-relaxed bg-zinc-50 p-4 rounded-2xl border border-zinc-100">
                    {details.description || "Cụm sân chưa cập nhật phần giới thiệu."}
                  </p>
                </div>

                {/* Amenities & Utilities */}
                <div>
                  <h4 className="text-xs sm:text-sm font-black text-zinc-950 uppercase tracking-wider mb-3">
                    Tiện Ích & Dịch Vụ Cung Cấp
                  </h4>
                  {details.amenities.length === 0 ? (
                    <p className="text-xs text-zinc-500">Cụm sân chưa khai báo tiện ích.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {details.amenities.map((name) => (
                        <span key={name} className="px-3 py-1.5 rounded-full bg-zinc-50 border border-zinc-200/70 text-xs font-semibold text-zinc-800">
                          {name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Operating Rules & Policies */}
                <div>
                  <h4 className="text-xs sm:text-sm font-black text-zinc-950 uppercase tracking-wider mb-2">
                    Đặt Sân & Hủy Lịch
                  </h4>
                  <ul className="text-xs text-zinc-600 space-y-1.5 bg-zinc-50 p-4 rounded-2xl border border-zinc-100 list-disc pl-5">
                    <li>Mỗi khung giờ dài 60 phút. Đặt cọc 50% qua chuyển khoản VietQR trong 15 phút để giữ sân.</li>
                    <li>Phần còn lại thanh toán tại sân khi đến nhận sân.</li>
                    <li>Hủy trước giờ chơi từ 12 tiếng: hoàn 100% số tiền đã thanh toán.</li>
                    <li>Hủy muộn hơn hoặc không đến: tiền cọc không được hoàn.</li>
                  </ul>
                </div>
              </div>

              {/* Modal Actions */}
              <div className="pt-4 border-t border-zinc-100 flex items-center justify-between gap-3 shrink-0">
                <a
                  href={mapUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2.5 bg-zinc-100 hover:bg-zinc-200 border border-zinc-200 text-zinc-800 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer"
                >
                  Mở Google Maps
                </a>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setDetailModalVenue(null)}
                    className="px-4 py-2.5 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer"
                  >
                    Đóng
                  </button>
                  <Link
                    href={`/venues/${detailModalVenue.id}`}
                    className="px-5 py-2.5 bg-zinc-950 hover:bg-zinc-800 text-white rounded-xl text-xs sm:text-sm font-bold transition btn-press cursor-pointer shadow-xs"
                  >
                    Xem Giờ & Đặt Sân Ngay →
                  </Link>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      <LocationPickerModal
        isOpen={isLocationModalOpen}
        onClose={() => setIsLocationModalOpen(false)}
        currentLocation={userLocation}
        onSelectLocation={handleSelectLocation}
      />

      {/* Rich Interactive Footer */}
      <Footer />
    </div>
  );
}

function ScoreRow({ label, score, detail }: { label: string; score: number | null; detail: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className="w-24 shrink-0">{label}</span>
      <span className="flex-1 h-1.5 rounded-full bg-zinc-100 overflow-hidden">
        {score != null && <span className="block h-full bg-zinc-900 rounded-full" style={{ width: `${Math.round(score * 100)}%` }} />}
      </span>
      <span className="w-28 shrink-0 text-right text-zinc-500 truncate">{detail || (score != null ? `${Math.round(score * 100)}%` : "—")}</span>
    </li>
  );
}
