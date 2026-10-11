"use client";

import React, { useCallback, useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { fetchApi, formatVND, parseUtcDate } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import LocationPickerModal from "@/components/LocationPickerModal";
import { UserLocation, getCurrentGpsPosition, reverseGeocode, saveLocation } from "@/lib/location";
import {
  AVAILABILITY_DAYS,
  AVAILABILITY_PERIODS,
  PLAY_STYLES,
  PROFILE_FIELD_LABEL,
  PURPOSES,
  SKILL_LEVELS,
  canonicalPlayStyle,
  playStyleLabel,
} from "@/lib/player";

interface Transaction {
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

interface ProfileForm {
  full_name: string;
  phone: string;
  date_of_birth: string;
  skill_level: string;
  play_style: string;
  matches_played: string;
  matches_won: string;
  purpose: string;
  availability: string[];
  latitude: number | null;
  longitude: number | null;
}

const EMPTY_FORM: ProfileForm = {
  full_name: "",
  phone: "",
  date_of_birth: "",
  skill_level: "",
  play_style: "",
  matches_played: "",
  matches_won: "",
  purpose: "",
  availability: [],
  latitude: null,
  longitude: null,
};

const KIND_LABEL: Record<string, string> = { DEPOSIT: "Tiền cọc", BALANCE: "Thanh toán tại sân", REFUND: "Hoàn tiền" };
const METHOD_LABEL: Record<string, string> = { BANK_TRANSFER: "Chuyển khoản", CASH: "Tiền mặt" };
const INPUT = "w-full px-3 py-1.5 border border-zinc-200 rounded-lg text-xs text-zinc-900 bg-white focus:outline-none focus:border-zinc-900";

function ProfileContent() {
  const { user, isLoading, refreshUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const { success: toastSuccess, error: toastError } = useToast();

  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM);
  const [locationName, setLocationName] = useState("");
  const [saving, setSaving] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false);

  const [showPasswordSection, setShowPasswordSection] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [changingPassword, setChangingPassword] = useState(false);

  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingTxns, setLoadingTxns] = useState(false);

  const activeTab: "profile" | "payments" = tabParam === "payments" ? "payments" : "profile";
  const profile = user?.player_profile;

  useEffect(() => {
    if (!isLoading && !user) router.push("/login");
  }, [user, isLoading, router]);

  // Nạp biểu mẫu từ hồ sơ thật; trường chưa khai để trống, không điền giá trị mặc định thay người dùng
  useEffect(() => {
    if (!profile) return;
    setForm({
      full_name: profile.full_name || "",
      phone: profile.phone || "",
      date_of_birth: profile.date_of_birth ? String(profile.date_of_birth).split("T")[0] : "",
      skill_level: profile.skill_level != null ? Number(profile.skill_level).toFixed(1) : "",
      play_style: canonicalPlayStyle(profile.play_style),
      matches_played: profile.matches_played != null ? String(profile.matches_played) : "",
      matches_won: profile.matches_won != null ? String(profile.matches_won) : "",
      purpose: profile.purpose || "",
      availability: profile.availability || [],
      latitude: profile.latitude ?? null,
      longitude: profile.longitude ?? null,
    });
    if (profile.latitude != null && profile.longitude != null) {
      reverseGeocode(profile.latitude, profile.longitude).then(setLocationName);
    } else {
      setLocationName("");
    }
  }, [profile]);

  const loadTransactions = useCallback(() => {
    setLoadingTxns(true);
    fetchApi("/payments/transactions")
      .then((data) => setTransactions(Array.isArray(data) ? data : []))
      .catch(() => setTransactions([]))
      .finally(() => setLoadingTxns(false));
  }, []);

  useEffect(() => {
    if (user && activeTab === "payments") loadTransactions();
  }, [user, activeTab, loadTransactions]);

  const toggleAvailability = (slot: string) =>
    setForm((prev) => ({
      ...prev,
      availability: prev.availability.includes(slot) ? prev.availability.filter((s) => s !== slot) : [...prev.availability, slot],
    }));

  const applyLocation = (lat: number, lng: number, name: string) => {
    setForm((prev) => ({ ...prev, latitude: lat, longitude: lng }));
    setLocationName(name);
    saveLocation({ name, lat, lng, isGps: true });
  };

  const handleGetGps = async () => {
    setGpsLoading(true);
    try {
      const pos = await getCurrentGpsPosition();
      const name = await reverseGeocode(pos.lat, pos.lng);
      applyLocation(pos.lat, pos.lng, name);
      toastSuccess(`Đã lấy vị trí: ${name}. Bấm “Lưu thông tin” để cập nhật hồ sơ.`);
    } catch {
      toastError("Không lấy được vị trí. Hãy cho phép trình duyệt truy cập vị trí, hoặc chọn khu vực thủ công.");
    } finally {
      setGpsLoading(false);
    }
  };

  const handleSelectLocation = (loc: UserLocation) => applyLocation(loc.lat, loc.lng, loc.name);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const played = form.matches_played === "" ? 0 : parseInt(form.matches_played, 10) || 0;
    const won = form.matches_won === "" ? 0 : parseInt(form.matches_won, 10) || 0;
    if (won > played) {
      toastError("Số trận thắng không thể lớn hơn số trận đã chơi.");
      return;
    }
    setSaving(true);
    try {
      await fetchApi("/users/me/profile", {
        method: "PUT",
        body: JSON.stringify({
          full_name: form.full_name,
          phone: form.phone,
          date_of_birth: form.date_of_birth || null,
          skill_level: form.skill_level ? parseFloat(form.skill_level) : null,
          play_style: form.play_style || null,
          matches_played: played,
          matches_won: won,
          purpose: form.purpose || null,
          availability: form.availability,
          latitude: form.latitude,
          longitude: form.longitude,
        }),
      });
      await refreshUser();
      toastSuccess("Đã lưu hồ sơ.");
    } catch (err: any) {
      toastError(err.message || "Không thể cập nhật hồ sơ. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (passwordForm.new_password.length < 6) {
      toastError("Mật khẩu mới phải có ít nhất 6 ký tự.");
      return;
    }
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      toastError("Xác nhận mật khẩu mới không khớp.");
      return;
    }
    setChangingPassword(true);
    try {
      const res = await fetchApi("/users/me/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: passwordForm.current_password, new_password: passwordForm.new_password }),
      });
      toastSuccess(res?.message || "Đổi mật khẩu thành công.");
      setPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
      setShowPasswordSection(false);
    } catch (err: any) {
      toastError(err.message || "Đổi mật khẩu thất bại.");
    } finally {
      setChangingPassword(false);
    }
  };

  if (isLoading || !user) return null;

  const displayName = form.full_name || user.email.split("@")[0];
  const missingForMatching = [
    !form.skill_level && "skill_level",
    form.latitude == null && "location",
    form.availability.length === 0 && "availability",
    !form.purpose && "purpose",
    !form.play_style && "play_style",
  ].filter(Boolean) as string[];

  const paid = transactions.filter((t) => t.status === "SUCCESS" && t.kind !== "REFUND").reduce((sum, t) => sum + t.amount_in, 0);
  const refunded = transactions.filter((t) => t.status === "SUCCESS" && t.kind === "REFUND").reduce((sum, t) => sum + t.amount_in, 0);

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900 selection:bg-zinc-900 selection:text-white">
      <Navbar />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-7 sm:py-9 flex-1 w-full">
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <h1 className="text-2xl sm:text-3xl font-bold text-zinc-950 tracking-tight">
            {activeTab === "profile" ? "Hồ Sơ Của Tôi" : "Lịch Sử Thanh Toán"}
          </h1>
          <div className="flex gap-1.5">
            <Link
              href="/profile"
              scroll={false}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition ${
                activeTab === "profile" ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-700 border-zinc-200 hover:bg-zinc-100"
              }`}
            >
              Hồ sơ
            </Link>
            <Link
              href="/profile?tab=payments"
              scroll={false}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition ${
                activeTab === "payments" ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-700 border-zinc-200 hover:bg-zinc-100"
              }`}
            >
              Thanh toán
            </Link>
          </div>
        </div>

        {activeTab === "profile" && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="md:col-span-1 space-y-3.5">
              <div className="rounded-2xl p-4 sm:p-5 bg-zinc-900 text-white border border-zinc-800 shadow-sm">
                <div className="flex items-center gap-2.5">
                  <div className="w-11 h-11 rounded-full bg-zinc-800 text-white font-bold text-lg flex items-center justify-center border border-zinc-700">
                    {displayName[0]?.toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-bold text-sm text-white line-clamp-1">{displayName}</h3>
                    <p className="text-[11px] text-zinc-400 truncate">{user.email}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-1.5 mt-3.5 text-center">
                  <Stat label="Trình độ" value={profile?.skill_level != null ? Number(profile.skill_level).toFixed(1) : "—"} />
                  <Stat label="Lối đánh" value={profile?.play_style ? playStyleLabel(profile.play_style, true) : "—"} />
                  <Stat label="Tỷ lệ thắng" value={profile?.win_rate != null ? `${profile.win_rate}%` : "—"} />
                  <Stat label="Tuổi" value={profile?.age != null ? String(profile.age) : "—"} />
                </div>
                <p className="mt-3 text-[10px] text-zinc-400 leading-relaxed">
                  Trình độ và số trận là thông tin bạn tự khai; mô hình ghép cặp dùng trình độ để đề xuất phòng đấu phù hợp.
                </p>
              </div>

              {user.role === "PLAYER" && (
                <div className="p-3.5 rounded-xl bg-white border border-zinc-200/80 text-xs shadow-xs space-y-2">
                  <p className="font-semibold text-zinc-900">Hồ sơ ghép cặp</p>
                  {missingForMatching.length > 0 ? (
                    <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2 leading-relaxed">
                      Hồ sơ còn thiếu: {missingForMatching.map((f) => PROFILE_FIELD_LABEL[f]).join(", ")}. Bổ sung để mô hình
                      đề xuất phòng đấu chính xác hơn.
                    </p>
                  ) : (
                    <p className="text-[11px] text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-2">
                      Hồ sơ đã đủ thông tin để mô hình đề xuất phòng đấu.
                    </p>
                  )}
                  <Link href="/survey" className="block w-full py-1.5 text-center bg-zinc-100 hover:bg-zinc-200 text-zinc-800 rounded-lg font-medium transition">
                    Trả lời khảo sát ghép cặp →
                  </Link>
                </div>
              )}

              {user.role !== "PLAYER" && (
                <div className="p-3.5 rounded-xl bg-white border border-zinc-200/80 text-xs shadow-xs">
                  <p className="font-semibold text-zinc-900 mb-2">Cổng quản lý</p>
                  <Link
                    href={user.role === "ADMIN" ? "/admin" : user.role === "STAFF" ? "/staff/dashboard" : "/owner/dashboard"}
                    className="block w-full py-1.5 text-center bg-zinc-900 hover:bg-zinc-800 text-white rounded-lg font-medium transition btn-press"
                  >
                    Vào cổng quản lý →
                  </Link>
                </div>
              )}
            </div>

            <div className="md:col-span-2 space-y-5">
              {user.role === "PLAYER" && (
                <form onSubmit={handleSave} className="bg-white rounded-xl p-5 sm:p-6 border border-zinc-200/80 shadow-xs space-y-4">
                  <h2 className="font-bold text-sm sm:text-base text-zinc-900">Thông Tin Cá Nhân</h2>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <Field label="Họ và tên">
                      <input type="text" required maxLength={120} className={INPUT} value={form.full_name}
                        onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                    </Field>
                    <Field label="Số điện thoại">
                      <input type="tel" className={INPUT} value={form.phone}
                        onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                    </Field>
                    <Field label="Ngày sinh">
                      <input type="date" className={INPUT} value={form.date_of_birth}
                        onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
                    </Field>
                    <Field label="Trình độ (tự đánh giá theo thang DUPR)">
                      <select className={INPUT} value={form.skill_level} onChange={(e) => setForm({ ...form, skill_level: e.target.value })}>
                        <option value="">Chưa chọn</option>
                        {SKILL_LEVELS.map((level) => (
                          <option key={level.value} value={level.value}>{level.label}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Lối đánh sở trường">
                      <select className={INPUT} value={form.play_style} onChange={(e) => setForm({ ...form, play_style: e.target.value })}>
                        <option value="">Chưa chọn</option>
                        {PLAY_STYLES.map((style) => (
                          <option key={style.value} value={style.value}>{style.label}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Mục đích chơi">
                      <select className={INPUT} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
                        <option value="">Chưa chọn</option>
                        {PURPOSES.map((purpose) => (
                          <option key={purpose.value} value={purpose.value}>{purpose.label}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Số trận đã chơi (tự khai)">
                      <input type="number" min={0} className={INPUT} value={form.matches_played}
                        onChange={(e) => setForm({ ...form, matches_played: e.target.value })} />
                    </Field>
                    <Field label="Số trận thắng (tự khai)">
                      <input type="number" min={0} className={INPUT} value={form.matches_won}
                        onChange={(e) => setForm({ ...form, matches_won: e.target.value })} />
                    </Field>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-zinc-800 mb-1.5">Khung giờ thường rảnh trong tuần</p>
                    <div className="overflow-x-auto">
                      <table className="text-[11px] border-separate border-spacing-1">
                        <thead>
                          <tr>
                            <th />
                            {AVAILABILITY_DAYS.map((day) => (
                              <th key={day.value} className="font-semibold text-zinc-500 w-10">{day.label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {AVAILABILITY_PERIODS.map((period) => (
                            <tr key={period.value}>
                              <td className="pr-2 font-semibold text-zinc-600">{period.label}</td>
                              {AVAILABILITY_DAYS.map((day) => {
                                const slot = `${day.value}_${period.value}`;
                                const checked = form.availability.includes(slot);
                                return (
                                  <td key={slot}>
                                    <button
                                      type="button"
                                      aria-pressed={checked}
                                      aria-label={`${day.label} ${period.label}`}
                                      onClick={() => toggleAvailability(slot)}
                                      className={`w-10 h-7 rounded-md border transition cursor-pointer ${
                                        checked ? "bg-zinc-900 border-zinc-900 text-white" : "bg-white border-zinc-200 hover:border-zinc-400 text-transparent"
                                      }`}
                                    >
                                      ✓
                                    </button>
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div>
                    <Field label="Khu vực thường chơi">
                      <div className="flex gap-2">
                        <input type="text" readOnly className={`${INPUT} bg-zinc-50`}
                          value={form.latitude == null ? "Chưa có vị trí" : locationName || `${form.latitude.toFixed(4)}, ${form.longitude?.toFixed(4)}`} />
                        <button type="button" onClick={handleGetGps} disabled={gpsLoading}
                          className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-white text-xs font-semibold rounded-lg transition disabled:opacity-60 cursor-pointer shrink-0">
                          {gpsLoading ? "..." : "GPS"}
                        </button>
                        <button type="button" onClick={() => setIsLocationModalOpen(true)}
                          className="px-3 py-1.5 border border-zinc-200 hover:bg-zinc-100 text-zinc-800 text-xs font-semibold rounded-lg transition cursor-pointer shrink-0">
                          Chọn
                        </button>
                      </div>
                    </Field>
                  </div>

                  <button type="submit" disabled={saving}
                    className="w-full sm:w-auto px-6 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-white font-semibold text-xs shadow-xs transition-all btn-press disabled:opacity-60 cursor-pointer">
                    {saving ? "Đang lưu..." : "Lưu Thông Tin"}
                  </button>
                </form>
              )}

              <div className="bg-white rounded-xl p-5 sm:p-6 border border-zinc-200/80 shadow-xs">
                <div className="flex items-center justify-between">
                  <h2 className="font-bold text-sm sm:text-base text-zinc-900">Mật Khẩu</h2>
                  <button type="button" onClick={() => setShowPasswordSection(!showPasswordSection)}
                    className="px-3 py-1.5 rounded-lg border border-zinc-200 hover:bg-zinc-100 text-zinc-800 text-xs font-medium transition cursor-pointer btn-press">
                    {showPasswordSection ? "Đóng" : "Đổi Mật Khẩu"}
                  </button>
                </div>

                {showPasswordSection && (
                  <form onSubmit={handleChangePassword} className="mt-4 pt-4 border-t border-zinc-100 space-y-3.5">
                    <Field label="Mật khẩu hiện tại">
                      <input type="password" required autoComplete="current-password" className={INPUT} value={passwordForm.current_password}
                        onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })} />
                    </Field>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                      <Field label="Mật khẩu mới (tối thiểu 6 ký tự)">
                        <input type="password" required minLength={6} autoComplete="new-password" className={INPUT} value={passwordForm.new_password}
                          onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })} />
                      </Field>
                      <Field label="Nhập lại mật khẩu mới">
                        <input type="password" required minLength={6} autoComplete="new-password" className={INPUT} value={passwordForm.confirm_password}
                          onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })} />
                      </Field>
                    </div>
                    <button type="submit" disabled={changingPassword}
                      className="px-5 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-white font-medium text-xs shadow-xs transition-all btn-press disabled:opacity-60 cursor-pointer">
                      {changingPassword ? "Đang xử lý..." : "Cập Nhật Mật Khẩu"}
                    </button>
                  </form>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "payments" && (
          <div className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
              <Summary label="Đã thanh toán" value={formatVND(paid)} tone="text-zinc-950" />
              <Summary label="Đã được hoàn" value={formatVND(refunded)} tone="text-emerald-600" />
              <Summary label="Số giao dịch" value={String(transactions.length)} tone="text-zinc-950" />
            </div>

            {loadingTxns ? (
              <div className="bg-white rounded-xl p-4 border border-zinc-200 animate-pulse h-20" />
            ) : transactions.length === 0 ? (
              <div className="text-center py-14 bg-white rounded-2xl border border-zinc-200 shadow-xs">
                <h3 className="font-bold text-zinc-950 text-base">Chưa có giao dịch nào</h3>
                <p className="text-xs text-zinc-500 mt-1">Các khoản cọc, thanh toán tại sân và hoàn tiền của bạn sẽ hiển thị tại đây.</p>
                <Link href="/bookings" className="mt-4 inline-block px-5 py-2.5 bg-zinc-950 text-white rounded-xl text-xs font-bold btn-press shadow-xs">
                  Xem Lịch Đặt Sân →
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {transactions.map((t) => {
                  const isRefund = t.kind === "REFUND";
                  return (
                    <div key={t.id} className="bg-white rounded-2xl border border-zinc-200/80 p-4 sm:p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-zinc-950 text-sm font-mono">{t.transaction_code || `#${t.id}`}</span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            isRefund ? "bg-emerald-50 text-emerald-700 border-emerald-200/60" : "bg-zinc-100 text-zinc-700 border-zinc-200"
                          }`}>
                            {KIND_LABEL[t.kind || ""] || t.kind}
                          </span>
                          <span className="text-xs text-zinc-500">{METHOD_LABEL[t.method || ""] || t.method}</span>
                        </div>
                        <p className="text-xs text-zinc-500">
                          {t.created_at ? parseUtcDate(t.created_at).toLocaleString("vi-VN") : ""}
                          {t.booking?.booking_code ? ` • Đơn ${t.booking.booking_code}` : ""}
                          {t.reference_number ? ` • Mã tham chiếu ${t.reference_number}` : ""}
                        </p>
                        {t.transaction_content && <p className="text-[11px] text-zinc-500 truncate">{t.transaction_content}</p>}
                      </div>
                      <span className={`text-base sm:text-lg font-black shrink-0 ${isRefund ? "text-emerald-600" : "text-zinc-900"}`}>
                        {isRefund ? "+" : "-"}{formatVND(t.amount_in)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>

      <LocationPickerModal
        isOpen={isLocationModalOpen}
        onClose={() => setIsLocationModalOpen(false)}
        currentLocation={form.latitude != null && form.longitude != null
          ? { name: locationName || "Vị trí đã chọn", lat: form.latitude, lng: form.longitude }
          : null}
        onSelectLocation={handleSelectLocation}
      />

      <Footer />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-zinc-800 mb-1">{label}</span>
      {children}
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-2 rounded-lg bg-zinc-800/80">
      <p className="text-[9px] text-zinc-400 font-medium uppercase">{label}</p>
      <p className="text-sm font-bold text-white mt-0.5 truncate">{value}</p>
    </div>
  );
}

function Summary({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="bg-white p-4 sm:p-5 rounded-2xl border border-zinc-200/80 shadow-xs">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className={`text-xl sm:text-2xl font-black mt-1 ${tone}`}>{value}</p>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-zinc-50 flex items-center justify-center font-sans">
          <div className="w-7 h-7 border-2 border-zinc-300 border-t-zinc-950 rounded-full animate-spin" />
        </div>
      }
    >
      <ProfileContent />
    </Suspense>
  );
}
