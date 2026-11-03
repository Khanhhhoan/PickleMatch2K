"use client";

import React, { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { fetchApi } from "@/lib/api";
import {
  UserLocation,
  getCurrentGpsPosition,
  reverseGeocode,
  searchAddressGeocode,
  saveLocation,
} from "@/lib/location";
import type { MapVenue } from "@/components/LocationMap";

// Leaflet cần window: chỉ nạp bản đồ trên trình duyệt
const LocationMap = dynamic(() => import("@/components/LocationMap"), {
  ssr: false,
  loading: () => <div className="h-60 w-full rounded-xl border border-zinc-200 bg-zinc-50 animate-pulse" />,
});

interface LocationPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentLocation: UserLocation | null;
  onSelectLocation: (location: UserLocation) => void;
}

export default function LocationPickerModal({
  isOpen,
  onClose,
  currentLocation,
  onSelectLocation,
}: LocationPickerModalProps) {
  const [gpsLoading, setGpsLoading] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);

  // Address search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<UserLocation[]>([]);

  // Selected candidate in modal
  const [selectedCandidate, setSelectedCandidate] = useState<UserLocation | null>(currentLocation);

  // Mỗi lần mở hộp thoại: bắt đầu từ vị trí đang dùng (vị trí có thể chỉ có sau khi tải xong hồ sơ)
  const [wasOpen, setWasOpen] = useState(isOpen);
  if (isOpen !== wasOpen) {
    setWasOpen(isOpen);
    if (isOpen) setSelectedCandidate(currentLocation);
  }

  // Các cụm sân của hệ thống, để vẽ lên bản đồ (tải một lần khi hộp thoại mở lần đầu)
  const [venues, setVenues] = useState<MapVenue[] | null>(null);
  useEffect(() => {
    if (!isOpen || venues !== null) return;
    fetchApi("/venues")
      .then((list: { id: number; name: string; latitude?: number | null; longitude?: number | null }[]) =>
        setVenues(
          (Array.isArray(list) ? list : [])
            .filter((v) => v.latitude != null && v.longitude != null)
            .map((v) => ({ id: v.id, name: v.name, lat: Number(v.latitude), lng: Number(v.longitude) }))
        )
      )
      .catch(() => setVenues([]));
  }, [isOpen, venues]);

  if (!isOpen) return null;

  const handleGpsClick = async () => {
    setGpsLoading(true);
    setGpsError(null);
    try {
      const pos = await getCurrentGpsPosition();
      const addrName = await reverseGeocode(pos.lat, pos.lng);
      const loc: UserLocation = {
        name: addrName || `GPS (${pos.lat.toFixed(4)}, ${pos.lng.toFixed(4)})`,
        lat: pos.lat,
        lng: pos.lng,
        accuracy: Math.round(pos.accuracy),
        isGps: true,
      };
      setSelectedCandidate(loc);
    } catch (err) {
      console.error(err);
      setGpsError(
        "Không thể lấy GPS từ trình duyệt hoặc thiết bị chưa cấp quyền. Bạn có thể bấm chọn một điểm trên bản đồ bên dưới."
      );
    } finally {
      setGpsLoading(false);
    }
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setGpsError(null);
    try {
      const results = await searchAddressGeocode(searchQuery.trim());
      setSearchResults(results);
      if (results.length === 0) {
        setGpsError("Không tìm thấy địa chỉ phù hợp. Vui lòng thử từ khóa khác hoặc bấm chọn trên bản đồ.");
      }
    } catch {
      setGpsError("Lỗi kết nối khi tìm kiếm địa chỉ.");
    } finally {
      setSearching(false);
    }
  };

  // Bấm lên bản đồ / kéo ghim: chọn ngay toạ độ đó, tên địa chỉ được điền sau khi tra xong
  const handleMapPick = (lat: number, lng: number, venueName?: string) => {
    const fallback = `Điểm trên bản đồ (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
    setGpsError(null);
    setSearchResults([]);
    setSelectedCandidate({ name: venueName ? `Tại ${venueName}` : fallback, lat, lng, isGps: false });
    if (venueName) return;
    reverseGeocode(lat, lng).then((name) => {
      const label = name && !name.startsWith("Tọa độ GPS") ? name : fallback;
      setSelectedCandidate((current) => (current && current.lat === lat && current.lng === lng ? { ...current, name: label } : current));
    });
  };

  const handleConfirm = () => {
    if (selectedCandidate) {
      saveLocation(selectedCandidate);
      onSelectLocation(selectedCandidate);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-xs animate-fade-in">
      <div className="bg-white rounded-2xl max-w-xl w-full max-h-[85vh] shadow-xl border border-zinc-200/80 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-zinc-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div>
              <h3 className="font-bold text-zinc-900 text-sm">Chọn Vị Trí Của Bạn</h3>
              <p className="text-[11px] text-zinc-500 font-normal">
                Dùng để tính khoảng cách từ bạn tới các cụm sân
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700 flex items-center justify-center transition-colors cursor-pointer text-sm"
          >
            ✕
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-5 overflow-y-auto space-y-4 flex-1">
          {/* Quick GPS Action */}
          <div className="p-3.5 rounded-xl bg-zinc-50 border border-zinc-200/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-zinc-900 text-white flex items-center justify-center shrink-0">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-zinc-900">Định vị GPS tự động</h4>
                <p className="text-[11px] text-zinc-500">
                  Lấy tọa độ thực tế từ thiết bị của bạn
                </p>
              </div>
            </div>
            <button
              onClick={handleGpsClick}
              disabled={gpsLoading}
              className="w-full sm:w-auto px-3.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 active:bg-zinc-950 text-white text-xs font-medium rounded-lg transition btn-press flex items-center justify-center gap-1.5 cursor-pointer shrink-0"
            >
              {gpsLoading ? (
                <span>Đang định vị...</span>
              ) : (
                <span>Lấy GPS Ngay</span>
              )}
            </button>
          </div>

          {gpsError && (
            <div className="p-2.5 bg-zinc-100 border border-zinc-200 rounded-lg text-zinc-700 text-xs flex items-center gap-2">
              <span>{gpsError}</span>
            </div>
          )}

          {/* Search by Address */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-700 block">
              Tìm theo địa chỉ tại TP.HCM:
            </label>
            <form onSubmit={handleSearchSubmit} className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="VD: 509 Đ. Phạm Huy Thông, An Nhơn, Gò Vấp..."
                className="flex-1 px-3 py-1.5 text-xs border border-zinc-200 rounded-lg focus:outline-none focus:border-zinc-900 bg-white"
              />
              <button
                type="submit"
                disabled={searching}
                className="px-3.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-white font-medium text-xs rounded-lg transition cursor-pointer shrink-0"
              >
                {searching ? "Đang tìm..." : "Tìm kiếm"}
              </button>
            </form>

            {searchResults.length > 0 && (
              <div className="p-1.5 border border-zinc-200 rounded-lg bg-zinc-50 space-y-1 max-h-36 overflow-y-auto">
                {searchResults.map((res, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setSelectedCandidate(res);
                      setSearchResults([]);
                    }}
                    className="w-full text-left p-1.5 hover:bg-white rounded-md text-xs text-zinc-800 flex items-center justify-between transition cursor-pointer border border-transparent hover:border-zinc-200"
                  >
                    <span className="truncate pr-2">{res.name}</span>
                    <span className="text-[10px] text-zinc-500 font-medium shrink-0">Chọn</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Chọn điểm trên bản đồ */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-700 block">
              Hoặc bấm chọn một điểm trên bản đồ:
            </label>
            <LocationMap value={selectedCandidate} venues={venues ?? []} onPick={handleMapPick} />
            <p className="text-[11px] text-zinc-500">
              Bấm vào bản đồ hoặc kéo ghim đen để đổi vị trí. Chấm xanh là các cụm sân, bấm vào chấm để chọn ngay tại sân đó.
            </p>
          </div>

          {/* Currently Selected Location Summary */}
          {selectedCandidate && (
            <div className="p-3 bg-zinc-100 rounded-xl flex items-center justify-between gap-2 border border-zinc-200/80">
              <div className="truncate">
                <span className="text-[9px] uppercase tracking-wider font-semibold text-zinc-500 block">
                  Vị trí đang chọn:
                </span>
                <p className="text-xs font-semibold text-zinc-900 truncate">{selectedCandidate.name}</p>
              </div>
              <span className="text-[10px] text-zinc-500 font-mono shrink-0">
                {selectedCandidate.lat.toFixed(3)}, {selectedCandidate.lng.toFixed(3)}
              </span>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="px-5 py-3 border-t border-zinc-100 bg-zinc-50/50 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 rounded-lg transition cursor-pointer"
          >
            Hủy
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!selectedCandidate}
            className="px-4 py-1.5 bg-zinc-900 hover:bg-zinc-800 disabled:opacity-50 text-white text-xs font-medium rounded-lg transition btn-press cursor-pointer"
          >
            Áp Dụng Vị Trí
          </button>
        </div>
      </div>
    </div>
  );
}
