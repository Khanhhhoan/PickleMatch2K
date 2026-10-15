"use client";

/**
 * Thiết lập hồ sơ ghép trận sau khi đăng ký: trình độ, ngày sinh, khu vực thường chơi, lối đánh và mục đích chơi.
 * Mỗi bước lưu ngay vào hồ sơ (PUT /users/me/profile, chỉ những trường của bước đó) và bỏ qua được; sửa lại sau ở
 * trang Hồ sơ. Thiếu trường nào thì trang Ghép Trận vẫn chạy, chỉ nhắc bổ sung để gợi ý phòng sát hơn.
 */
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { reverseGeocode, type UserLocation } from "@/lib/location";
import { PLAY_STYLES, PURPOSES, SKILL_LEVELS, canonicalPlayStyle } from "@/lib/player";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import LocationPickerModal from "@/components/LocationPickerModal";

const STEPS = ["Trình độ", "Ngày sinh", "Khu vực", "Lối đánh & mục đích"] as const;

type Profile = NonNullable<ReturnType<typeof useAuth>["user"]>["player_profile"];

function initialForm(profile: Profile | null | undefined) {
  return {
    skill_level: profile?.skill_level != null ? Number(profile.skill_level).toFixed(1) : "",
    date_of_birth: profile?.date_of_birth ? String(profile.date_of_birth).split("T")[0] : "",
    location:
      profile?.latitude != null && profile?.longitude != null
        ? ({ name: "Vị trí đã lưu", lat: profile.latitude, lng: profile.longitude } as UserLocation)
        : null,
    play_style: canonicalPlayStyle(profile?.play_style) || "",
    purpose: profile?.purpose || "",
  };
}

const CHOICE = "px-3.5 py-2.5 rounded-xl border text-sm font-semibold text-left transition cursor-pointer";
const CHOSEN = "bg-zinc-950 border-zinc-950 text-white";
const IDLE = "bg-white border-zinc-200 text-zinc-800 hover:border-zinc-400";

function OnboardingForm() {
  const { user, isLoading, refreshUser } = useAuth();
  const router = useRouter();
  const { success: toastSuccess, error: toastError } = useToast();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Điền sẵn những gì hồ sơ đã có (người dùng cũ quay lại bổ sung); trang chỉ hiện sau khi đã có thông tin đăng nhập
  const [form, setForm] = useState(() => initialForm(user?.player_profile));

  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login?next=/onboarding");
    else if (user.role !== "PLAYER") router.replace("/");
  }, [user, isLoading, router]);

  // Tên khu vực của vị trí đã lưu: tra địa chỉ rồi mới điền (bất đồng bộ)
  const savedLat = user?.player_profile?.latitude;
  const savedLng = user?.player_profile?.longitude;
  useEffect(() => {
    if (savedLat == null || savedLng == null) return;
    let alive = true;
    reverseGeocode(savedLat, savedLng)
      .then((name) => {
        if (alive) setForm((prev) => (prev.location ? { ...prev, location: { ...prev.location, name } } : prev));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [savedLat, savedLng]);

  if (isLoading || !user || user.role !== "PLAYER") return null;

  const changesOf = (index: number): Record<string, unknown> | null => {
    if (index === 0) return form.skill_level ? { skill_level: parseFloat(form.skill_level) } : null;
    if (index === 1) return form.date_of_birth ? { date_of_birth: form.date_of_birth } : null;
    if (index === 2) return form.location ? { latitude: form.location.lat, longitude: form.location.lng } : null;
    const changes: Record<string, unknown> = {};
    if (form.play_style) changes.play_style = form.play_style;
    if (form.purpose) changes.purpose = form.purpose;
    return Object.keys(changes).length ? changes : null;
  };

  const finish = async () => {
    await refreshUser().catch(() => {});
    toastSuccess("Đã thiết lập hồ sơ. Đây là các phòng hợp với bạn.");
    router.push("/matches");
  };

  const next = async (save: boolean) => {
    const changes = save ? changesOf(step) : null;
    if (changes) {
      setSaving(true);
      try {
        await fetchApi("/users/me/profile", { method: "PUT", body: JSON.stringify(changes) });
      } catch (err) {
        toastError(err instanceof Error ? err.message : "Không lưu được. Vui lòng thử lại.");
        setSaving(false);
        return;
      }
      setSaving(false);
    }
    if (step < STEPS.length - 1) setStep(step + 1);
    else await finish();
  };

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900">
      <Navbar />
      <main className="max-w-xl mx-auto px-4 sm:px-6 pt-8 pb-28 sm:py-12 flex-1 w-full">
        <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 tracking-tight">Thiết lập hồ sơ ghép trận</h1>
        <p className="text-sm text-zinc-500 mt-1.5">
          Vài thông tin để hệ thống gợi ý phòng đấu hợp với bạn. Bước nào chưa muốn khai thì bấm “Để sau”, sửa lại bất cứ lúc
          nào ở trang Hồ sơ.
        </p>

        {/* Thanh tiến trình */}
        <div className="mt-6" aria-label={`Bước ${step + 1} trên ${STEPS.length}`}>
          <div className="flex gap-1.5">
            {STEPS.map((name, index) => (
              <div key={name} className={`h-1.5 flex-1 rounded-full ${index <= step ? "bg-zinc-950" : "bg-zinc-200"}`} />
            ))}
          </div>
          <p className="text-xs font-bold text-zinc-500 mt-2">
            Bước {step + 1}/{STEPS.length}: {STEPS[step]}
          </p>
        </div>

        <div className="mt-5 bg-white rounded-2xl border border-zinc-200 shadow-xs p-5 sm:p-6 space-y-4">
          {step === 0 && (
            <>
              <p className="text-sm font-bold text-zinc-950">Bạn tự đánh giá trình độ (DUPR) của mình ở mức nào?</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {SKILL_LEVELS.map((level) => (
                  <button key={level.value} type="button" onClick={() => setForm({ ...form, skill_level: level.value })}
                    className={`${CHOICE} ${form.skill_level === level.value ? CHOSEN : IDLE}`}>
                    {level.label}
                  </button>
                ))}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <label className="text-sm font-bold text-zinc-950" htmlFor="onboarding-birthday">Ngày sinh của bạn</label>
              <input id="onboarding-birthday" type="date" max={today} value={form.date_of_birth}
                onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl border border-zinc-200 text-sm" />
              <p className="text-xs text-zinc-500">Dùng để gợi ý bạn chơi cùng lứa tuổi; không hiển thị cho người khác.</p>
            </>
          )}

          {step === 2 && (
            <>
              <p className="text-sm font-bold text-zinc-950">Bạn thường chơi ở khu vực nào?</p>
              <button type="button" onClick={() => setPickerOpen(true)} className={`${CHOICE} w-full ${form.location ? CHOSEN : IDLE}`}>
                {form.location ? form.location.name : "Chọn khu vực trên bản đồ hoặc dùng vị trí hiện tại"}
              </button>
              <p className="text-xs text-zinc-500">Dùng để ưu tiên phòng đấu ở gần bạn.</p>
            </>
          )}

          {step === 3 && (
            <>
              <p className="text-sm font-bold text-zinc-950">Lối đánh quen thuộc</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {PLAY_STYLES.map((style) => (
                  <button key={style.value} type="button" onClick={() => setForm({ ...form, play_style: style.value })}
                    className={`${CHOICE} ${form.play_style === style.value ? CHOSEN : IDLE}`}>
                    {style.label}
                  </button>
                ))}
              </div>
              <p className="text-sm font-bold text-zinc-950 pt-2">Bạn chơi để làm gì?</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {PURPOSES.map((purpose) => (
                  <button key={purpose.value} type="button" onClick={() => setForm({ ...form, purpose: purpose.value })}
                    className={`${CHOICE} ${form.purpose === purpose.value ? CHOSEN : IDLE}`}>
                    {purpose.label}
                  </button>
                ))}
              </div>
            </>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-zinc-100">
            <button type="button" disabled={saving || step === 0} onClick={() => setStep(step - 1)}
              className="px-3.5 py-2 rounded-xl text-sm font-semibold text-zinc-600 hover:bg-zinc-100 disabled:opacity-40 cursor-pointer">
              Quay lại
            </button>
            <div className="flex gap-2">
              <button type="button" disabled={saving} onClick={() => next(false)}
                className="px-3.5 py-2 rounded-xl border border-zinc-200 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 cursor-pointer disabled:opacity-50">
                Để sau
              </button>
              <button type="button" disabled={saving} onClick={() => next(true)}
                className="px-4 py-2 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-sm font-bold cursor-pointer disabled:opacity-50">
                {saving ? "Đang lưu..." : step < STEPS.length - 1 ? "Tiếp tục" : "Hoàn tất"}
              </button>
            </div>
          </div>
        </div>
      </main>

      <LocationPickerModal
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        currentLocation={form.location}
        onSelectLocation={(location) => {
          setForm((prev) => ({ ...prev, location }));
          setPickerOpen(false);
        }}
      />
    </div>
  );
}

/** Chỉ dựng biểu mẫu khi đã biết người đăng nhập, để biểu mẫu khởi tạo đúng một lần từ hồ sơ đã có. */
export default function OnboardingPage() {
  const { user, isLoading } = useAuth();
  if (isLoading || !user) return <OnboardingGuard />;
  return <OnboardingForm />;
}

function OnboardingGuard() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!isLoading && !user) router.replace("/login?next=/onboarding");
  }, [user, isLoading, router]);
  return null;
}
