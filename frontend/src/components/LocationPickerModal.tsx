"use client";

import React, { useState } from "react";
import {
  PRESET_LOCATIONS,
  PresetLocation,
  UserLocation,
  getCurrentGpsPosition,
  reverseGeocode,
  searchAddressGeocode,
  saveLocation,
} from "@/lib/location";

interface LocationPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentLocation: UserLocation | null;
  onSelectLocation: (location: UserLocation) => void;
}

type AreaTab = "all" | "central" | "east" | "south" | "north";

const AREA_TABS: { id: AreaTab; label: string }[] = [
  { id: "all", label: "Tất cả 10 sân" },
  { id: "central", label: "Trung tâm" },
  { id: "east", label: "Thủ Đức" },
  { id: "south", label: "Quận 7" },
  { id: "north", label: "Tân Bình/Khác" },
];

export default function LocationPickerModal({
  isOpen,
  onClose,
  currentLocation,
  onSelectLocation,
}: LocationPickerModalProps) {
  const [activeAreaTab, setActiveAreaTab] = useState<AreaTab>("all");
  const [gpsLoading, setGpsLoading] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);

  // Address search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<UserLocation[]>([]);

  // Selected candidate in modal
  const [selectedCandidate, setSelectedCandidate] = useState<UserLocation | null>(currentLocation);

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
        "Không thể lấy GPS từ trình duyệt hoặc thiết bị chưa cấp quyền. Bạn có thể chọn cụm sân bên dưới."
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
        setGpsError("Không tìm thấy địa chỉ phù hợp. Vui lòng thử từ khóa khác hoặc chọn cụm sân có sẵn.");
      }
    } catch {
      setGpsError("Lỗi kết nối khi tìm kiếm địa chỉ.");
    } finally {
      setSearching(false);
    }
  };

  const handleSelectPreset = (preset: PresetLocation) => {
    const loc: UserLocation = {
      name: `${preset.name} (${preset.district})`,
      lat: preset.lat,
      lng: preset.lng,
      isGps: false,
    };
    setSelectedCandidate(loc);
  };

  const handleConfirm = () => {
    if (selectedCandidate) {
      saveLocation(selectedCandidate);
      onSelectLocation(selectedCandidate);
      onClose();
    }
  };

  const filteredPresets = PRESET_LOCATIONS.filter((p) => {
    if (activeAreaTab === "all") return true;
    if (activeAreaTab === "central") {
      return ["Quận 1", "Quận 3", "Quận 10"].includes(p.district);
    }
    if (activeAreaTab === "east") {
      return ["TP. Thủ Đức"].includes(p.district);
    }
    if (activeAreaTab === "south") {
      return ["Quận 7"].includes(p.district);
    }
    if (activeAreaTab === "north") {
      return ["Tân Bình", "Phú Nhuận", "Bình Thạnh", "Tân Phú"].includes(p.district);
    }
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-xs animate-fade-in">
      <div className="bg-white rounded-2xl max-w-xl w-full max-h-[85vh] shadow-xl border border-zinc-200/80 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-zinc-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div>
              <h3 className="font-bold text-zinc-900 text-sm">Chọn Vị Trí Của Bạn</h3>
              <p className="text-[11px] text-zinc-500 font-normal">
                Tính khoảng cách chuẩn xác tới 10 cụm sân Pickleball TP.HCM
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
              Tìm hoặc nhập địa chỉ Google Maps bất kỳ tại TP.HCM:
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

          {/* Quick Select by 10 Venues / Districts */}
          <div className="space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
              <label className="text-xs font-medium text-zinc-700 block">
                Hoặc chọn nhanh 10 cụm sân tại TP.HCM:
              </label>
              <div className="flex items-center gap-1 bg-zinc-100 p-0.5 rounded-lg overflow-x-auto no-scrollbar">
                {AREA_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveAreaTab(tab.id)}
                    className={`px-2 py-0.5 text-[10px] font-medium rounded-md whitespace-nowrap transition cursor-pointer ${
                      activeAreaTab === tab.id
                        ? "bg-white text-zinc-900 shadow-xs font-semibold"
                        : "text-zinc-500 hover:text-zinc-800"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-52 overflow-y-auto p-0.5">
              {filteredPresets.map((preset, idx) => {
                const isSelected =
                  selectedCandidate &&
                  Math.abs(selectedCandidate.lat - preset.lat) < 0.001 &&
                  Math.abs(selectedCandidate.lng - preset.lng) < 0.001;

                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSelectPreset(preset)}
                    className={`p-2.5 rounded-xl text-left border transition-all cursor-pointer flex items-center justify-between ${
                      isSelected
                        ? "bg-zinc-900 text-white border-zinc-900"
                        : "bg-white border-zinc-200 text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50 text-xs"
                    }`}
                  >
                    <div className="truncate pr-2">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className={`text-[9px] font-semibold px-1.5 py-0.2 rounded ${isSelected ? "bg-zinc-800 text-zinc-200" : "bg-zinc-100 text-zinc-600"}`}>
                          {preset.district}
                        </span>
                      </div>
                      <span className="text-xs font-medium block truncate">{preset.name}</span>
                      <span className={`text-[10px] block truncate ${isSelected ? "text-zinc-400" : "text-zinc-400"}`}>
                        {preset.address}
                      </span>
                    </div>
                    {isSelected && (
                      <span className="text-[10px] font-semibold text-white shrink-0 ml-1 px-1 py-0.2 bg-zinc-800 rounded">
                        Đang chọn
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
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
