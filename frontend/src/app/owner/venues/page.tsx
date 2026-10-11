"use client";

import React, { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { deleteVenueImage, fetchApi, formatVND, getMediaUrl, uploadVenueImage } from "@/lib/api";
import { searchAddressGeocode } from "@/lib/location";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";

type Tab = "info_sepay" | "courts_pricing" | "hours" | "staff";

interface Court {
  id: number;
  name: string;
  status: string;
  price?: number | null;
}

interface Venue {
  id: number;
  name: string;
  address: string;
  description?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  image_url?: string | null;
  images?: string | null;
  status: string;
  courts: Court[];
  operating_hours: { day_of_week: number; open_time: string; close_time: string }[];
  price_rules: { rule_type: string; price: number; start_time?: string | null; end_time?: string | null }[];
  amenities: { id: number; name: string }[];
  owner_company_name?: string | null;
  owner_bank_account?: string | null;
}

interface Staff {
  id: number;
  email: string;
  is_active: boolean;
  staff_profile?: { full_name?: string | null; phone?: string | null; venue_id?: number | null } | null;
}

const TABS: { key: Tab; label: string }[] = [
  { key: "info_sepay", label: "Thông tin & nhận tiền" },
  { key: "courts_pricing", label: "Sân & bảng giá" },
  { key: "hours", label: "Giờ hoạt động" },
  { key: "staff", label: "Nhân sự" },
];

const BANKS = ["Techcombank", "MBBank", "Vietcombank", "Sacombank", "ACB", "VPBank", "VietinBank", "BIDV", "TPBank", "VIB"];
const WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];
const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Đang hoạt động",
  MAINTENANCE: "Tạm đóng bảo trì",
  INACTIVE: "Ngừng hiển thị",
  PENDING: "Chờ Admin duyệt",
  REJECTED: "Bị từ chối",
};

const CARD = "bg-white rounded-2xl border border-[#e8edf3] shadow-[0_12px_35px_rgba(29,51,87,0.035)] p-6 space-y-4";
const LABEL = "block text-[11px] font-bold text-[#51627c] mb-1";
const INPUT = "w-full h-10 px-3 bg-white border border-[#dde4ef] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3]";
const PRIMARY = "px-4 py-2.5 bg-[#476cf3] text-white rounded-xl text-xs font-bold whitespace-nowrap hover:bg-[#3b61e8] disabled:opacity-50 transition cursor-pointer";
const SECONDARY = "px-3 py-2 bg-[#f1f4fb] hover:bg-[#e4ebf7] border border-[#d5dfed] rounded-xl text-xs font-bold whitespace-nowrap text-[#405c94] cursor-pointer disabled:opacity-50";
// Thao tác phụ trên từng dòng của danh sách
const ROW_ACTION = "px-2 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap text-[#405c94] hover:bg-[#eef2fb] cursor-pointer disabled:opacity-50";
const ROW_DANGER = "px-2 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap text-rose-600 hover:bg-rose-50 cursor-pointer disabled:opacity-50";
const ROW = "flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border border-[#e8edf3] bg-white hover:bg-[#fafbfe]";

/** Tách "0123456789 - MBBank" hoặc "0123456789 (MBBank)" thành số tài khoản và tên ngân hàng. */
function parseBankAccount(raw?: string | null): { number: string; bank: string } {
  const text = (raw || "").trim();
  if (!text) return { number: "", bank: "" };
  const number = (text.match(/\d{6,}/) || [""])[0];
  const bank = BANKS.find((name) => text.toLowerCase().includes(name.toLowerCase())) || "";
  return { number, bank };
}

function parseImages(venue: Venue): string[] {
  try {
    const parsed = venue.images ? JSON.parse(venue.images) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function OwnerVenueManagementContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const { success: toastSuccess, error: toastError } = useToast();

  const [venues, setVenues] = useState<Venue[]>([]);
  const [staffList, setStaffList] = useState<Staff[]>([]);
  const [amenities, setAmenities] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("info_sepay");
  const [selectedVenueId, setSelectedVenueId] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [info, setInfo] = useState({ name: "", address: "", description: "", latitude: "", longitude: "", amenity_ids: [] as number[] });
  const [bank, setBank] = useState({ bank: "", number: "", holder: "" });
  const [prices, setPrices] = useState({ base: "", peak: "", weekend: "", peak_start: "17:00", peak_end: "23:00" });
  const [hours, setHours] = useState(WEEKDAYS.map(() => ({ open: false, open_time: "06:00", close_time: "22:00" })));
  const [newCourt, setNewCourt] = useState({ name: "", price: "" });
  const [staffForm, setStaffForm] = useState({ id: 0, email: "", password: "", full_name: "", phone: "" });
  const [showStaffForm, setShowStaffForm] = useState(false);
  const [newVenue, setNewVenue] = useState({ name: "", address: "" });

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && TABS.some((t) => t.key === tab)) setActiveTab(tab as Tab);
  }, [searchParams]);

  const venue = useMemo(() => venues.find((v) => v.id === selectedVenueId) || venues[0] || null, [venues, selectedVenueId]);

  const loadData = useCallback(async () => {
    try {
      const [venueData, staffData, amenityData] = await Promise.all([
        fetchApi("/venues/me"),
        fetchApi("/users/owner/staff").catch(() => []),
        fetchApi("/venues/amenities").catch(() => []),
      ]);
      setVenues(Array.isArray(venueData) ? venueData : []);
      setStaffList(Array.isArray(staffData) ? staffData : []);
      setAmenities(Array.isArray(amenityData) ? amenityData : []);
    } catch (err: any) {
      toastError(err.message || "Không tải được dữ liệu cụm sân.");
    } finally {
      setLoading(false);
    }
  }, [toastError]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  // Đổ dữ liệu thật của cụm sân vào biểu mẫu; ô chưa có dữ liệu để trống
  useEffect(() => {
    if (!venue) return;
    setInfo({
      name: venue.name || "",
      address: venue.address || "",
      description: venue.description || "",
      latitude: venue.latitude != null ? String(venue.latitude) : "",
      longitude: venue.longitude != null ? String(venue.longitude) : "",
      amenity_ids: venue.amenities.map((a) => a.id),
    });
    const parsed = parseBankAccount(venue.owner_bank_account);
    setBank({ bank: parsed.bank, number: parsed.number, holder: venue.owner_company_name || "" });

    const rule = (type: string) => venue.price_rules.find((r) => r.rule_type === type);
    const peak = rule("PEAK");
    setPrices({
      base: rule("BASE") ? String(rule("BASE")!.price) : "",
      peak: peak ? String(peak.price) : "",
      weekend: rule("WEEKEND") ? String(rule("WEEKEND")!.price) : "",
      peak_start: peak?.start_time?.slice(0, 5) || "17:00",
      peak_end: peak?.end_time?.slice(0, 5) || "23:00",
    });
    setHours(
      WEEKDAYS.map((_, day) => {
        const row = venue.operating_hours.find((h) => h.day_of_week === day);
        return row
          ? { open: true, open_time: row.open_time.slice(0, 5), close_time: row.close_time.slice(0, 5) }
          : { open: false, open_time: "06:00", close_time: "22:00" };
      }),
    );
  }, [venue]);

  /** Chạy một thao tác ghi, báo kết quả và tải lại dữ liệu. */
  const run = async (key: string, action: () => Promise<unknown>, successMessage: string) => {
    setBusy(key);
    try {
      await action();
      toastSuccess(successMessage);
      await loadData();
      return true;
    } catch (err: any) {
      toastError(err.message || "Thao tác không thực hiện được.");
      return false;
    } finally {
      setBusy(null);
    }
  };

  const put = (path: string, body: unknown) => fetchApi(path, { method: "PUT", body: JSON.stringify(body) });
  const post = (path: string, body: unknown) => fetchApi(path, { method: "POST", body: JSON.stringify(body) });

  // ------------------------------------------------------------------ handlers
  const handleGeocode = async () => {
    if (!info.address.trim()) return;
    setBusy("geocode");
    try {
      const results = await searchAddressGeocode(info.address);
      if (results.length > 0) {
        setInfo((prev) => ({ ...prev, latitude: results[0].lat.toFixed(6), longitude: results[0].lng.toFixed(6) }));
        toastSuccess("Đã tìm thấy toạ độ. Kiểm tra lại rồi bấm Lưu.");
      } else {
        toastError("Không tìm thấy toạ độ cho địa chỉ này. Bạn có thể nhập tay.");
      }
    } finally {
      setBusy(null);
    }
  };

  const saveInfo = (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue) return;
    const latitude = info.latitude.trim() ? Number(info.latitude) : null;
    const longitude = info.longitude.trim() ? Number(info.longitude) : null;
    if ((latitude !== null && Number.isNaN(latitude)) || (longitude !== null && Number.isNaN(longitude))) {
      toastError("Toạ độ phải là số (ví dụ 10.8334).");
      return;
    }
    run("info", () => put(`/venues/${venue.id}`, {
      name: info.name,
      address: info.address,
      description: info.description || null,
      ...(latitude !== null && longitude !== null ? { latitude, longitude } : {}),
      amenity_ids: info.amenity_ids,
    }), "Đã lưu thông tin cụm sân.");
  };

  const saveBank = (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue) return;
    if (!bank.bank || !/^\d{6,}$/.test(bank.number.trim()) || !bank.holder.trim()) {
      toastError("Vui lòng chọn ngân hàng, nhập số tài khoản (chỉ gồm chữ số) và tên chủ tài khoản.");
      return;
    }
    run("bank", () => put(`/venues/${venue.id}`, {
      bank_account: `${bank.number.trim()} - ${bank.bank}`,
      company_name: bank.holder.trim().toUpperCase(),
    }), "Đã lưu tài khoản nhận tiền.");
  };

  const setStatus = (status: string) =>
    venue && run("status", () => put(`/venues/${venue.id}/status`, { status }), `Đã chuyển cụm sân sang “${STATUS_LABEL[status]}”.`);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !venue) return;
    await run("upload", () => uploadVenueImage(venue.id, file, !venue.image_url), "Đã tải ảnh lên.");
  };

  const savePrices = (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue) return;
    run("prices", () => put(`/venues/${venue.id}/pricing`, {
      base_price: Number(prices.base),
      peak_price: prices.peak ? Number(prices.peak) : null,
      weekend_price: prices.weekend ? Number(prices.weekend) : null,
      peak_start: prices.peak_start,
      peak_end: prices.peak_end,
    }), "Đã lưu bảng giá.");
  };

  const addCourt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue || !newCourt.name.trim()) return;
    const ok = await run("court-add", () => post(`/venues/${venue.id}/courts`, {
      name: newCourt.name.trim(),
      price: newCourt.price ? Number(newCourt.price) : null,
    }), "Đã thêm sân.");
    if (ok) setNewCourt({ name: "", price: "" });
  };

  const updateCourt = (court: Court, changes: Record<string, unknown>, message: string) =>
    venue && run(`court-${court.id}`, () => put(`/venues/${venue.id}/courts/${court.id}`, changes), message);

  const renameCourt = (court: Court) => {
    const name = window.prompt("Tên mới của sân:", court.name)?.trim();
    if (name && name !== court.name) updateCourt(court, { name }, "Đã đổi tên sân.");
  };

  const setCourtPrice = (court: Court) => {
    const raw = window.prompt("Giá riêng của sân (VNĐ/giờ). Để trống hoặc 0 để dùng bảng giá chung:", court.price ? String(court.price) : "");
    if (raw === null) return;
    const price = Number(raw.trim() || 0);
    if (Number.isNaN(price) || price < 0) {
      toastError("Giá không hợp lệ.");
      return;
    }
    updateCourt(court, { price }, price > 0 ? "Đã đặt giá riêng cho sân." : "Sân dùng lại bảng giá chung.");
  };

  const deleteCourt = (court: Court) => {
    if (!venue || !window.confirm(`Xóa ${court.name}? Chỉ xóa được sân chưa từng có lịch đặt.`)) return;
    run(`court-${court.id}`, () => fetchApi(`/venues/${venue.id}/courts/${court.id}`, { method: "DELETE" }), "Đã xóa sân.");
  };

  const saveHours = (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue) return;
    const invalid = hours.find((h) => h.open && h.open_time >= h.close_time);
    if (invalid) {
      toastError("Giờ mở cửa phải trước giờ đóng cửa.");
      return;
    }
    run("hours", () => put(`/venues/${venue.id}/operating-hours`, {
      hours: hours.map((h, day) => ({ ...h, day })).filter((h) => h.open)
        .map((h) => ({ day_of_week: h.day, open_time: h.open_time, close_time: h.close_time })),
    }), "Đã lưu giờ hoạt động.");
  };

  const saveStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue) return;
    const editing = staffForm.id > 0;
    const ok = await run("staff", () => editing
      ? put(`/users/owner/staff/${staffForm.id}`, {
          full_name: staffForm.full_name,
          phone: staffForm.phone,
          ...(staffForm.password ? { password: staffForm.password } : {}),
        })
      : post("/users/owner/staff", {
          email: staffForm.email,
          password: staffForm.password,
          full_name: staffForm.full_name,
          phone: staffForm.phone || null,
          venue_id: venue.id,
        }), editing ? "Đã cập nhật nhân viên." : "Đã tạo tài khoản nhân viên.");
    if (ok) {
      setShowStaffForm(false);
      setStaffForm({ id: 0, email: "", password: "", full_name: "", phone: "" });
    }
  };

  const deleteStaff = async (staff: Staff) => {
    if (!window.confirm(`Xóa tài khoản ${staff.email}? Nhân viên đã từng thao tác trên đơn sẽ được khóa thay vì xóa.`)) return;
    setBusy("staff");
    try {
      const result = await fetchApi(`/users/owner/staff/${staff.id}`, { method: "DELETE" });
      toastSuccess(result?.message || "Đã xóa nhân viên.");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Không xóa được nhân viên.");
    } finally {
      setBusy(null);
    }
  };

  const registerVenue = async (e: React.FormEvent) => {
    e.preventDefault();
    await run("register", () => post("/venues", newVenue), "Đã gửi đăng ký cụm sân. Cụm sân sẽ hiển thị công khai sau khi Admin duyệt.");
  };

  // ------------------------------------------------------------------ render
  if (loading) return <div className="p-10 text-center text-xs text-[#51627c]">Đang tải dữ liệu cụm sân...</div>;

  if (!venue) {
    return (
      <div className="max-w-xl mx-auto">
        <form onSubmit={registerVenue} className={CARD}>
          <h1 className="text-lg font-black text-[#17253d] m-0">Đăng ký cụm sân</h1>
          <p className="text-xs text-[#51627c]">
            Tài khoản của bạn chưa quản lý cụm sân nào. Sau khi gửi đăng ký, quản trị viên sẽ xét duyệt trước khi cụm sân hiển thị cho người chơi.
          </p>
          <div>
            <label className={LABEL}>Tên cụm sân</label>
            <input className={INPUT} required value={newVenue.name} onChange={(e) => setNewVenue({ ...newVenue, name: e.target.value })} />
          </div>
          <div>
            <label className={LABEL}>Địa chỉ</label>
            <input className={INPUT} required value={newVenue.address} onChange={(e) => setNewVenue({ ...newVenue, address: e.target.value })} />
          </div>
          <button type="submit" disabled={busy === "register"} className={PRIMARY}>Gửi đăng ký</button>
        </form>
      </div>
    );
  }

  const images = parseImages(venue);
  const venueStaff = staffList.filter((s) => s.staff_profile?.venue_id === venue.id);
  const awaitingAdmin = venue.status === "PENDING" || venue.status === "REJECTED";

  return (
    <div className="space-y-6 max-w-[1650px] mx-auto font-sans">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold text-[#6b7ba1]">Cài đặt cụm sân</p>
          <div className="flex flex-wrap items-center gap-2.5 mt-0.5">
            <h1 className="text-2xl sm:text-[26px] font-black text-[#17253d] tracking-tight m-0">{venue.name}</h1>
            <span
              className={`px-2.5 py-1 rounded-full border text-[11px] font-bold whitespace-nowrap ${
                venue.status === "ACTIVE" ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-amber-50 border-amber-200 text-amber-800"
              }`}
            >
              {STATUS_LABEL[venue.status] || venue.status}
            </span>
          </div>
          {venue.status !== "ACTIVE" && (
            <p className="text-xs text-[#51627c] mt-1">Người chơi hiện không nhìn thấy và không đặt được cụm sân này.</p>
          )}
        </div>
        {venues.length > 1 && (
          <select
            value={venue.id}
            onChange={(e) => setSelectedVenueId(Number(e.target.value))}
            aria-label="Chọn cụm sân quản lý"
            className="bg-white border border-[#dde4ef] px-3.5 py-2 rounded-xl text-xs font-bold text-[#17253d] cursor-pointer"
          >
            {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        )}
      </div>

      <div className="overflow-x-auto">
        <div className="inline-flex p-1 rounded-xl bg-white border border-[#e3e9f3]">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-lg text-xs font-bold whitespace-nowrap cursor-pointer transition ${
                activeTab === tab.key ? "bg-[#476cf3] text-white shadow-sm" : "text-[#51627c] hover:text-[#17253d]"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "info_sepay" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <form onSubmit={saveInfo} className={CARD}>
            <h3 className="text-sm font-black text-[#17253d] m-0">Thông tin chung</h3>
            <div>
              <label className={LABEL}>Tên cụm sân</label>
              <input className={INPUT} required value={info.name} onChange={(e) => setInfo({ ...info, name: e.target.value })} />
            </div>
            <div>
              <label className={LABEL}>Địa chỉ</label>
              <div className="flex gap-2">
                <input className={INPUT} required value={info.address} onChange={(e) => setInfo({ ...info, address: e.target.value })} />
                <button type="button" onClick={handleGeocode} disabled={busy === "geocode"} className={`${SECONDARY} whitespace-nowrap`}>
                  {busy === "geocode" ? "Đang tìm..." : "Tìm toạ độ"}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL}>Vĩ độ</label>
                <input className={`${INPUT} font-mono`} inputMode="decimal" placeholder="Chưa có" value={info.latitude}
                  onChange={(e) => setInfo({ ...info, latitude: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Kinh độ</label>
                <input className={`${INPUT} font-mono`} inputMode="decimal" placeholder="Chưa có" value={info.longitude}
                  onChange={(e) => setInfo({ ...info, longitude: e.target.value })} />
              </div>
            </div>
            <p className="text-[11px] text-[#8a97ab] -mt-2">Toạ độ dùng để tính khoảng cách từ người chơi tới sân.</p>
            <div>
              <label className={LABEL}>Giới thiệu</label>
              <textarea rows={3} className="w-full p-3 bg-white border border-[#dde4ef] rounded-xl text-xs font-medium text-[#263b53] outline-none resize-none"
                value={info.description} onChange={(e) => setInfo({ ...info, description: e.target.value })} />
            </div>
            <div>
              <label className={LABEL}>Tiện ích có tại cụm sân</label>
              <div className="flex flex-wrap gap-1.5">
                {amenities.map((amenity) => {
                  const checked = info.amenity_ids.includes(amenity.id);
                  return (
                    <button
                      key={amenity.id}
                      type="button"
                      aria-pressed={checked}
                      onClick={() => setInfo((prev) => ({
                        ...prev,
                        amenity_ids: checked ? prev.amenity_ids.filter((id) => id !== amenity.id) : [...prev.amenity_ids, amenity.id],
                      }))}
                      className={`px-2.5 py-1 rounded-full border text-[11px] font-bold cursor-pointer transition ${
                        checked ? "bg-[#eef2ff] border-[#476cf3] text-[#3454d1]" : "bg-white border-[#dde4ef] text-[#51627c] hover:border-[#b9c6dd]"
                      }`}
                    >
                      {amenity.name}
                    </button>
                  );
                })}
              </div>
            </div>
            <button type="submit" disabled={busy === "info"} className={PRIMARY}>{busy === "info" ? "Đang lưu..." : "Lưu thông tin"}</button>
          </form>

          <div className="space-y-6">
            <form onSubmit={saveBank} className={CARD}>
              <h3 className="text-sm font-black text-[#17253d] m-0">Tài khoản nhận tiền cọc</h3>
              <div>
                <label className={LABEL}>Ngân hàng</label>
                <select className={INPUT} value={bank.bank} onChange={(e) => setBank({ ...bank, bank: e.target.value })}>
                  <option value="">Chọn ngân hàng</option>
                  {BANKS.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </div>
              <div>
                <label className={LABEL}>Số tài khoản</label>
                <input className={`${INPUT} font-mono`} inputMode="numeric" placeholder="Chưa cấu hình" value={bank.number}
                  onChange={(e) => setBank({ ...bank, number: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Tên chủ tài khoản (in hoa không dấu)</label>
                <input className={`${INPUT} uppercase`} placeholder="Chưa cấu hình" value={bank.holder}
                  onChange={(e) => setBank({ ...bank, holder: e.target.value })} />
              </div>
              <p className="text-[11px] text-[#8a97ab] leading-relaxed">
                Khách quét mã VietQR để chuyển tiền cọc; đơn được xác nhận tự động khi tiền về.
              </p>
              <button type="submit" disabled={busy === "bank"} className={PRIMARY}>{busy === "bank" ? "Đang lưu..." : "Lưu tài khoản"}</button>
            </form>

            <div className={CARD}>
              <h3 className="text-sm font-black text-[#17253d] m-0">Hình ảnh</h3>
              <div className="grid grid-cols-3 gap-2">
                {images.map((url) => (
                  <div key={url} className="relative rounded-xl overflow-hidden border border-[#e8edf3] bg-[#f4f7fb]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={getMediaUrl(url)} alt="Ảnh cụm sân" className="w-full h-24 object-cover" />
                    <div className="flex text-[10px] font-bold">
                      <button
                        type="button"
                        disabled={venue.image_url === url || busy === "image"}
                        onClick={() => run("image", () => put(`/venues/${venue.id}`, { image_url: url }), "Đã đặt làm ảnh bìa.")}
                        className="flex-1 py-1 bg-white hover:bg-[#f1f4fb] text-[#405c94] disabled:text-[#9aa7bb] cursor-pointer"
                      >
                        {venue.image_url === url ? "Ảnh bìa" : "Đặt bìa"}
                      </button>
                      <button
                        type="button"
                        disabled={busy === "image"}
                        onClick={() => window.confirm("Xóa ảnh này?") && run("image", () => deleteVenueImage(venue.id, url), "Đã xóa ảnh.")}
                        className="flex-1 py-1 bg-white hover:bg-rose-50 text-rose-600 cursor-pointer border-l border-[#e8edf3]"
                      >
                        Xóa
                      </button>
                    </div>
                  </div>
                ))}
                {images.length === 0 && <p className="col-span-3 text-xs text-[#718096]">Chưa có ảnh nào.</p>}
              </div>
              <label className={`${SECONDARY} inline-block`}>
                {busy === "upload" ? "Đang tải lên..." : "+ Tải ảnh lên (JPG, PNG, WEBP)"}
                <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={handleUpload} disabled={busy === "upload"} />
              </label>
            </div>

            <div className={CARD}>
              <h3 className="text-sm font-black text-[#17253d] m-0">Trạng thái hoạt động</h3>
              {awaitingAdmin ? (
                <p className="text-xs text-[#51627c]">
                  Cụm sân đang ở trạng thái “{STATUS_LABEL[venue.status]}”. Chỉ quản trị viên mới thay đổi được trạng thái này.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {["ACTIVE", "MAINTENANCE", "INACTIVE"].map((status) => (
                    <button
                      key={status}
                      type="button"
                      disabled={venue.status === status || busy === "status"}
                      onClick={() => setStatus(status)}
                      className={venue.status === status ? `${PRIMARY} cursor-default` : SECONDARY}
                    >
                      {STATUS_LABEL[status]}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-[11px] text-[#8a97ab]">Khi tạm đóng hoặc ngừng hiển thị, người chơi không đặt thêm được; các đơn đã có vẫn giữ nguyên.</p>
            </div>
          </div>
        </div>
      )}

      {activeTab === "courts_pricing" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <div className={CARD}>
            <h3 className="text-sm font-black text-[#17253d] m-0">Sân thuộc cụm ({venue.courts.length})</h3>
            <ul className="space-y-2">
              {venue.courts.map((court) => (
                <li key={court.id} className={ROW}>
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${court.status === "ACTIVE" ? "bg-emerald-500" : "bg-amber-500"}`} />
                    <div className="min-w-0">
                      <p className="text-xs font-black text-[#17253d] truncate">{court.name}</p>
                      <p className="text-[11px] text-[#8a97ab]">
                        {court.status === "ACTIVE" ? "Đang nhận đặt" : "Đang bảo trì"} •{" "}
                        {court.price ? `Giá riêng ${formatVND(court.price)}/giờ` : "Theo bảng giá chung"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center shrink-0">
                    <button type="button" className={ROW_ACTION} disabled={busy === `court-${court.id}`} onClick={() => renameCourt(court)}>Đổi tên</button>
                    <button type="button" className={ROW_ACTION} disabled={busy === `court-${court.id}`} onClick={() => setCourtPrice(court)}>Giá riêng</button>
                    <button
                      type="button"
                      className={ROW_ACTION}
                      disabled={busy === `court-${court.id}`}
                      onClick={() => updateCourt(court, { status: court.status === "ACTIVE" ? "MAINTENANCE" : "ACTIVE" },
                        court.status === "ACTIVE" ? "Đã chuyển sân sang bảo trì." : "Sân đã nhận đặt trở lại.")}
                    >
                      {court.status === "ACTIVE" ? "Bảo trì" : "Mở lại"}
                    </button>
                    <button type="button" className={ROW_DANGER} disabled={busy === `court-${court.id}`} onClick={() => deleteCourt(court)}>Xóa</button>
                  </div>
                </li>
              ))}
              {venue.courts.length === 0 && <li className="text-xs text-[#8a97ab] py-4 text-center">Chưa có sân nào. Thêm sân đầu tiên ở bên dưới.</li>}
            </ul>
            <form onSubmit={addCourt} className="flex flex-wrap items-end gap-2 pt-3 border-t border-[#eef1f6]">
              <div className="flex-1 min-w-36">
                <label className={LABEL}>Tên sân mới</label>
                <input className={INPUT} required maxLength={80} value={newCourt.name} onChange={(e) => setNewCourt({ ...newCourt, name: e.target.value })} />
              </div>
              <div className="w-36">
                <label className={LABEL}>Giá riêng (tùy chọn)</label>
                <input className={INPUT} type="number" min={0} step={10000} value={newCourt.price} onChange={(e) => setNewCourt({ ...newCourt, price: e.target.value })} />
              </div>
              <button type="submit" disabled={busy === "court-add"} className={PRIMARY}>Thêm sân</button>
            </form>
          </div>

          <form onSubmit={savePrices} className={CARD}>
            <h3 className="text-sm font-black text-[#17253d] m-0">Bảng giá mỗi giờ (VNĐ)</h3>
            <div>
              <label className={LABEL}>Giờ thường</label>
              <input className={INPUT} type="number" required min={1000} step={1000} value={prices.base} onChange={(e) => setPrices({ ...prices, base: e.target.value })} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className={LABEL}>Giờ cao điểm</label>
                <input className={INPUT} type="number" min={1000} step={1000} placeholder="Bằng giờ thường" value={prices.peak}
                  onChange={(e) => setPrices({ ...prices, peak: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Cao điểm từ</label>
                <input className={INPUT} type="time" step={3600} value={prices.peak_start} onChange={(e) => setPrices({ ...prices, peak_start: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>đến</label>
                <input className={INPUT} type="time" step={3600} value={prices.peak_end} onChange={(e) => setPrices({ ...prices, peak_end: e.target.value })} />
              </div>
            </div>
            <div>
              <label className={LABEL}>Thứ Bảy, Chủ Nhật</label>
              <input className={INPUT} type="number" min={0} step={1000} placeholder="Bằng giờ thường" value={prices.weekend}
                onChange={(e) => setPrices({ ...prices, weekend: e.target.value })} />
            </div>
            <p className="text-[11px] text-[#8a97ab] leading-relaxed">
              Giá tính theo từng khung 60 phút. Cuối tuần trong giờ cao điểm áp dụng mức cao hơn. Giá mới áp dụng cho các đơn tạo sau khi lưu.
            </p>
            <button type="submit" disabled={busy === "prices"} className={PRIMARY}>{busy === "prices" ? "Đang lưu..." : "Lưu bảng giá"}</button>
          </form>
        </div>
      )}

      {activeTab === "hours" && (
        <form onSubmit={saveHours} className={`${CARD} max-w-2xl`}>
          <h3 className="text-sm font-black text-[#17253d] m-0">Giờ hoạt động trong tuần</h3>
          <ul className="divide-y divide-[#f1f4f9] border border-[#e8edf3] rounded-xl">
            {WEEKDAYS.map((name, day) => (
              <li key={name} className="flex items-center gap-3 px-3.5 py-2 text-xs">
                <label className="flex items-center gap-2.5 w-28 shrink-0 font-bold text-[#17253d] whitespace-nowrap cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 accent-[#476cf3]" checked={hours[day].open}
                    onChange={(e) => setHours((prev) => prev.map((h, i) => (i === day ? { ...h, open: e.target.checked } : h)))} />
                  {name}
                </label>
                {hours[day].open ? (
                  <>
                    <div className="w-32">
                      <input type="time" className={INPUT} value={hours[day].open_time} aria-label={`${name} mở cửa`}
                        onChange={(e) => setHours((prev) => prev.map((h, i) => (i === day ? { ...h, open_time: e.target.value } : h)))} />
                    </div>
                    <span className="text-[#8a97ab]">đến</span>
                    <div className="w-32">
                      <input type="time" className={INPUT} value={hours[day].close_time} aria-label={`${name} đóng cửa`}
                        onChange={(e) => setHours((prev) => prev.map((h, i) => (i === day ? { ...h, close_time: e.target.value } : h)))} />
                    </div>
                  </>
                ) : (
                  <span className="h-10 flex items-center text-[#9aa7bb] font-bold">Nghỉ</span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-[#8a97ab] leading-relaxed">
            Khung giờ đặt sân dài 60 phút, tính từ giờ mở cửa. Thay đổi không ảnh hưởng tới các đơn đã có.
          </p>
          <button type="submit" disabled={busy === "hours"} className={PRIMARY}>{busy === "hours" ? "Đang lưu..." : "Lưu giờ hoạt động"}</button>
        </form>
      )}

      {activeTab === "staff" && (
        <div className={`${CARD} max-w-3xl`}>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-black text-[#17253d] m-0">Nhân viên của cụm sân ({venueStaff.length})</h3>
            <button type="button" className={PRIMARY} onClick={() => { setStaffForm({ id: 0, email: "", password: "", full_name: "", phone: "" }); setShowStaffForm(true); }}>
              + Thêm nhân viên
            </button>
          </div>
          <ul className="space-y-2">
            {venueStaff.map((staff) => (
              <li key={staff.id} className={`${ROW} text-xs`}>
                <div className="flex items-center gap-3 min-w-0">
                  <span className="w-8 h-8 rounded-full bg-[#eef2ff] text-[#3454d1] flex items-center justify-center font-black shrink-0">
                    {(staff.staff_profile?.full_name || staff.email).trim().charAt(0).toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="font-black text-[#17253d] truncate">
                      {staff.staff_profile?.full_name || "(chưa có tên)"}
                      {!staff.is_active && <span className="ml-2 text-[10px] font-bold text-rose-600">Đã khóa</span>}
                    </p>
                    <p className="text-[#8a97ab] truncate">{staff.email} • {staff.staff_profile?.phone || "chưa có số điện thoại"}</p>
                  </div>
                </div>
                <div className="flex items-center shrink-0">
                  <button type="button" className={ROW_ACTION}
                    onClick={() => { setStaffForm({ id: staff.id, email: staff.email, password: "", full_name: staff.staff_profile?.full_name || "", phone: staff.staff_profile?.phone || "" }); setShowStaffForm(true); }}>
                    Sửa
                  </button>
                  <button type="button" className={ROW_DANGER} onClick={() => deleteStaff(staff)}>Xóa</button>
                </div>
              </li>
            ))}
            {venueStaff.length === 0 && <li className="text-xs text-[#8a97ab] py-4 text-center">Chưa có nhân viên nào.</li>}
          </ul>

          {showStaffForm && (
            <form onSubmit={saveStaff} className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-4 border-t border-[#eef1f6]">
              <div>
                <label className={LABEL}>Email đăng nhập</label>
                <input className={INPUT} type="email" required disabled={staffForm.id > 0} value={staffForm.email}
                  onChange={(e) => setStaffForm({ ...staffForm, email: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>{staffForm.id > 0 ? "Mật khẩu mới (để trống nếu giữ nguyên)" : "Mật khẩu (tối thiểu 6 ký tự)"}</label>
                <input className={INPUT} type="password" autoComplete="new-password" minLength={6} required={staffForm.id === 0} value={staffForm.password}
                  onChange={(e) => setStaffForm({ ...staffForm, password: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Họ và tên</label>
                <input className={INPUT} required value={staffForm.full_name} onChange={(e) => setStaffForm({ ...staffForm, full_name: e.target.value })} />
              </div>
              <div>
                <label className={LABEL}>Số điện thoại</label>
                <input className={INPUT} type="tel" value={staffForm.phone} onChange={(e) => setStaffForm({ ...staffForm, phone: e.target.value })} />
              </div>
              <div className="sm:col-span-2 flex gap-2">
                <button type="submit" disabled={busy === "staff"} className={PRIMARY}>{busy === "staff" ? "Đang lưu..." : "Lưu nhân viên"}</button>
                <button type="button" className={SECONDARY} onClick={() => setShowStaffForm(false)}>Hủy</button>
              </div>
            </form>
          )}
          <p className="text-[11px] text-[#8a97ab]">Nhân viên chỉ xem và thao tác được trên đơn của cụm sân này; không xem được tài khoản nhận tiền.</p>
        </div>
      )}
    </div>
  );
}

export default function OwnerVenueManagementPage() {
  return (
    <Suspense fallback={<div className="p-10 text-center text-xs text-[#51627c]">Đang tải...</div>}>
      <OwnerVenueManagementContent />
    </Suspense>
  );
}
