"use client";

import React, { useCallback, useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { Booking, bookingCode, formatDisplayDate, mergeSlots } from "@/lib/booking";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { PURPOSES, SKILL_LEVELS } from "@/lib/player";

const INPUT = "w-full px-3 py-2 border border-zinc-200 rounded-xl text-sm text-zinc-900 bg-white focus:outline-none focus:border-zinc-900";

function CreateMatchContent() {
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { success: toastSuccess, error: toastError } = useToast();

  const [bookings, setBookings] = useState<Booking[]>([]);
  const [hasConfirmedBooking, setHasConfirmedBooking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ num_players: "4", required_skill: "", purpose: "recreational", notes: "" });

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [user, authLoading, router]);

  const loadData = useCallback(async () => {
    const [bookingData, matchData] = await Promise.all([
      fetchApi("/bookings/me").catch(() => []),
      fetchApi("/matches").catch(() => []),
    ]);
    // Chỉ mở phòng được trên đơn đã cọc (CONFIRMED) và chưa gắn với phòng đang hoạt động nào
    const confirmed: Booking[] = (Array.isArray(bookingData) ? bookingData : []).filter((b: Booking) => b.status === "CONFIRMED");
    const usedBookingIds = new Set(
      (Array.isArray(matchData) ? matchData : []).filter((m: any) => m.status !== "CANCELLED" && m.booking_id).map((m: any) => m.booking_id),
    );
    const available = confirmed.filter((b) => !usedBookingIds.has(b.id));
    setHasConfirmedBooking(confirmed.length > 0);
    setBookings(available);

    const requested = Number(searchParams?.get("booking_id"));
    setSelectedId((prev) => {
      if (requested && available.some((b) => b.id === requested)) return requested;
      if (prev && available.some((b) => b.id === prev)) return prev;
      return available[0]?.id ?? null;
    });
    setLoading(false);
  }, [searchParams]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  // Gợi ý trình độ yêu cầu theo trình độ của chủ phòng (người dùng vẫn chỉnh được)
  useEffect(() => {
    const level = user?.player_profile?.skill_level;
    if (level != null) setForm((prev) => (prev.required_skill ? prev : { ...prev, required_skill: Number(level).toFixed(1) }));
  }, [user]);

  const selected = bookings.find((b) => b.id === selectedId) || null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    setSubmitting(true);
    try {
      await fetchApi("/matches", {
        method: "POST",
        body: JSON.stringify({
          booking_id: selected.id,
          num_players: parseInt(form.num_players, 10),
          required_skill: form.required_skill ? parseFloat(form.required_skill) : null,
          purpose: form.purpose,
          notes: form.notes.trim() || null,
        }),
      });
      toastSuccess("Đã mở phòng đấu trên lịch sân của bạn.");
      router.push("/matches?tab=my_matches");
    } catch (err: any) {
      toastError(err.message || "Không mở được phòng đấu.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || !user) return null;

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900 selection:bg-zinc-950 selection:text-white">
      <Navbar />

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-10 flex-1 w-full">
        <div className="mb-6">
          <Link href="/matches" className="text-xs font-semibold text-zinc-500 hover:text-zinc-950">
            ← Quay lại Ghép Trận
          </Link>
          <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 tracking-tight mt-2">Mở Phòng Đấu</h1>
          <p className="text-xs sm:text-sm text-zinc-500 mt-1">
            Phòng đấu luôn gắn với một lịch sân bạn đã thanh toán cọc, để người tham gia chắc chắn có sân.
          </p>
        </div>

        {loading ? (
          <div className="bg-white rounded-2xl p-6 border border-zinc-200 animate-pulse h-32" />
        ) : bookings.length === 0 ? (
          <div className="bg-white rounded-3xl p-8 sm:p-10 border border-zinc-200/90 shadow-sm text-center space-y-4">
            <h2 className="text-lg font-bold text-zinc-950">
              {hasConfirmedBooking ? "Mọi lịch sân của bạn đều đã có phòng đấu" : "Bạn chưa có lịch sân nào đã thanh toán cọc"}
            </h2>
            <p className="text-sm text-zinc-600">
              {hasConfirmedBooking
                ? "Mỗi lịch sân chỉ mở được một phòng. Hãy đặt thêm sân nếu muốn mở phòng mới."
                : "Hãy đặt sân và thanh toán cọc trước, sau đó quay lại đây để mở phòng tìm bạn chơi."}
            </p>
            <div className="flex justify-center gap-2">
              <Link href="/" className="px-5 py-2.5 bg-zinc-950 hover:bg-zinc-800 text-white rounded-xl text-xs font-bold btn-press shadow-xs">
                Tìm Sân Và Đặt Lịch →
              </Link>
              <Link href="/bookings" className="px-5 py-2.5 bg-zinc-100 hover:bg-zinc-200 text-zinc-800 rounded-xl text-xs font-bold">
                Lịch Đặt Của Tôi
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <section className="bg-white rounded-2xl p-5 border border-zinc-200/90 shadow-xs space-y-3">
              <h2 className="font-bold text-sm text-zinc-900">1. Chọn lịch sân</h2>
              <div className="space-y-2">
                {bookings.map((b) => {
                  const slots = mergeSlots(b.details);
                  const first = slots[0];
                  const checked = b.id === selectedId;
                  return (
                    <label
                      key={b.id}
                      className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition ${
                        checked ? "border-zinc-900 bg-zinc-50 ring-1 ring-zinc-900" : "border-zinc-200 hover:border-zinc-400"
                      }`}
                    >
                      <input type="radio" name="booking" className="mt-1" checked={checked} onChange={() => setSelectedId(b.id)} />
                      <div className="min-w-0 text-xs sm:text-sm">
                        <p className="font-bold text-zinc-950">
                          {b.details[0]?.venue_name || "Cụm sân"} <span className="font-mono text-zinc-500 font-semibold">• {bookingCode(b)}</span>
                        </p>
                        {first && (
                          <p className="text-zinc-600 mt-0.5">
                            {first.court_name} • {formatDisplayDate(first.date)} • {first.start_time} - {first.end_time}
                          </p>
                        )}
                        {slots.length > 1 && (
                          <p className="text-[11px] text-amber-700 mt-0.5">
                            Đơn có nhiều khoảng giờ: phòng đấu dùng khoảng giờ đầu tiên.
                          </p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </section>

            <section className="bg-white rounded-2xl p-5 border border-zinc-200/90 shadow-xs space-y-4">
              <h2 className="font-bold text-sm text-zinc-900">2. Thông tin phòng</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                <label className="block">
                  <span className="block text-xs font-semibold text-zinc-800 mb-1">Số người chơi</span>
                  <select className={INPUT} value={form.num_players} onChange={(e) => setForm({ ...form, num_players: e.target.value })}>
                    <option value="2">2 người (đánh đơn)</option>
                    <option value="4">4 người (đánh đôi)</option>
                    <option value="6">6 người (xoay vòng)</option>
                    <option value="8">8 người (xoay vòng)</option>
                  </select>
                </label>
                <label className="block">
                  <span className="block text-xs font-semibold text-zinc-800 mb-1">Trình độ mong muốn</span>
                  <select className={INPUT} value={form.required_skill} onChange={(e) => setForm({ ...form, required_skill: e.target.value })}>
                    <option value="">Mọi trình độ</option>
                    {SKILL_LEVELS.map((level) => (
                      <option key={level.value} value={level.value}>{level.value}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="block text-xs font-semibold text-zinc-800 mb-1">Mục đích</span>
                  <select className={INPUT} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
                    {PURPOSES.map((purpose) => (
                      <option key={purpose.value} value={purpose.value}>{purpose.label}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block">
                <span className="block text-xs font-semibold text-zinc-800 mb-1">Ghi chú cho người tham gia (không bắt buộc)</span>
                <textarea
                  className={INPUT}
                  rows={3}
                  maxLength={300}
                  placeholder="Ví dụ: chia đều tiền sân, mang theo bóng..."
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </label>
            </section>

            <button
              type="submit"
              disabled={submitting || !selected}
              className="w-full py-3 rounded-2xl bg-zinc-950 hover:bg-zinc-800 text-white font-black text-sm transition btn-press disabled:opacity-60 cursor-pointer shadow-md"
            >
              {submitting ? "Đang mở phòng..." : "Mở Phòng Đấu"}
            </button>
          </form>
        )}
      </main>

      <Footer />
    </div>
  );
}

export default function CreateMatchPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-zinc-50" />}>
      <CreateMatchContent />
    </Suspense>
  );
}
