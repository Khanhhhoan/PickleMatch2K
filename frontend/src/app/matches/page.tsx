"use client";

import React, { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { formatDisplayDate } from "@/lib/booking";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";
import { useWebSocket } from "@/lib/use-websocket";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { getSavedLocation } from "@/lib/location";
import { PROFILE_FIELD_LABEL, playStyleLabel, purposeLabel } from "@/lib/player";

interface Participant {
  id: number;
  user_id: number;
  user_name?: string | null;
  skill_level?: number | null;
  play_style?: string | null;
  phone?: string | null; // chỉ có khi mình là thành viên của phòng
}

interface Match {
  id: number;
  creator_id: number;
  venue_id: number;
  venue_name?: string | null;
  court_name?: string | null;
  booking_code?: string | null;
  date: string;
  start_time: string;
  end_time: string;
  required_skill?: number | null;
  num_players: number;
  purpose?: string | null;
  notes?: string | null;
  status: "OPEN" | "FULL" | "CANCELLED" | "COMPLETED";
  creator_name?: string | null;
  creator_skill_level?: number | null;
  creator_play_style?: string | null;
  participants: Participant[];
  compatibility?: number | null; // 0-100, do mô hình ở máy chủ ước lượng
}

interface ModelInfo {
  available: boolean;
  error?: string | null;
  data_source?: string | null;
  n_samples?: number | null;
  n_raters?: number | null;
  metrics?: { accuracy?: number; roc_auc?: number } | null;
}

interface Partner {
  user_id: number;
  full_name: string;
  skill_level?: number | null;
  play_style?: string | null;
  purpose?: string | null;
  distance_km?: number | null;
  shared_slots: number;
  probability: number;
}

interface PartnerResponse {
  model: ModelInfo;
  missing_profile_fields: string[];
  items: Partner[];
}

type Tab = "suggested" | "open" | "my_matches" | "partners";

const TABS: { key: Tab; label: string }[] = [
  { key: "suggested", label: "Phòng Phù Hợp" },
  { key: "open", label: "Tất Cả Phòng Mở" },
  { key: "my_matches", label: "Phòng Của Tôi" },
  { key: "partners", label: "Bạn Chơi Gợi Ý" },
];

const STATUS_LABEL: Record<Match["status"], string> = {
  OPEN: "Đang tuyển",
  FULL: "Đã đủ người",
  CANCELLED: "Đã hủy",
  COMPLETED: "Đã kết thúc",
};

const STATUS_TONE: Record<Match["status"], string> = {
  OPEN: "bg-emerald-50 text-emerald-800 border-emerald-200",
  FULL: "bg-sky-50 text-sky-800 border-sky-200",
  CANCELLED: "bg-zinc-100 text-zinc-600 border-zinc-200",
  COMPLETED: "bg-purple-50 text-purple-700 border-purple-200",
};

const RADIUS_OPTIONS = [5, 10, 20, 0]; // 0 = không giới hạn

function MatchesContent() {
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { success: toastSuccess, error: toastError } = useToast();

  const [matches, setMatches] = useState<Match[]>([]);
  const [partners, setPartners] = useState<PartnerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("suggested");
  const [radius, setRadius] = useState(10);
  const [busyMatchId, setBusyMatchId] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<{ message: string; onConfirm: () => void } | null>(null);

  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [user, authLoading, router]);

  useEffect(() => {
    const tab = searchParams?.get("tab");
    if (tab === "my" || tab === "my_matches") setActiveTab("my_matches");
    else if (tab && TABS.some((t) => t.key === tab)) setActiveTab(tab as Tab);
  }, [searchParams]);

  const loadData = useCallback(async () => {
    // Vị trí hiện tại (nếu người dùng đã chọn) cho kết quả sát thực tế hơn vị trí lưu trong hồ sơ
    const here = getSavedLocation();
    const position = here ? `latitude=${here.lat}&longitude=${here.lng}` : "";
    const partnerQuery = [`limit=12`, radius > 0 ? `radius_km=${radius}` : "", position].filter(Boolean).join("&");
    const [matchData, partnerData] = await Promise.all([
      fetchApi(`/matches${position ? `?${position}` : ""}`).catch(() => []),
      fetchApi(`/ml/recommend-partners?${partnerQuery}`).catch(() => null),
    ]);
    setMatches(Array.isArray(matchData) ? matchData : []);
    setPartners(partnerData);
    setLoading(false);
  }, [radius]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  useEffect(() => {
    if (lastMessage && (lastMessage.type === "MATCH_CREATED" || lastMessage.type === "MATCH_UPDATED")) loadData();
  }, [lastMessage, loadData]);

  const isMember = useCallback(
    (m: Match) => !!user && (m.creator_id === user.id || m.participants.some((p) => p.user_id === user.id)),
    [user],
  );

  const handleJoin = async (match: Match) => {
    setBusyMatchId(match.id);
    try {
      await fetchApi(`/matches/${match.id}/join`, { method: "POST" });
      toastSuccess("Đã tham gia phòng. Xem số điện thoại các thành viên trong mục “Phòng Của Tôi”.");
      await loadData();
      setActiveTab("my_matches");
    } catch (err: any) {
      toastError(err.message || "Không tham gia được phòng.");
    } finally {
      setBusyMatchId(null);
    }
  };

  const handleLeave = (match: Match) => {
    const isHost = match.creator_id === user?.id;
    setConfirm({
      message: isHost
        ? "Bạn là chủ phòng: rời phòng sẽ HỦY phòng đấu này với tất cả thành viên. Tiếp tục?"
        : "Bạn chắc chắn muốn rời khỏi phòng đấu này?",
      onConfirm: async () => {
        setConfirm(null);
        setBusyMatchId(match.id);
        try {
          await fetchApi(`/matches/${match.id}/leave`, { method: "POST" });
          toastSuccess(isHost ? "Đã hủy phòng." : "Đã rời phòng.");
          await loadData();
        } catch (err: any) {
          toastError(err.message || "Không thực hiện được.");
        } finally {
          setBusyMatchId(null);
        }
      },
    });
  };

  const joinable = useMemo(() => matches.filter((m) => m.status === "OPEN" && !isMember(m)), [matches, isMember]);
  const suggested = useMemo(
    () => joinable.filter((m) => m.compatibility != null).sort((a, b) => (b.compatibility || 0) - (a.compatibility || 0)),
    [joinable],
  );
  const myMatches = useMemo(() => matches.filter(isMember), [matches, isMember]);

  const model = partners?.model;
  const missing = partners?.missing_profile_fields || [];
  const listed = activeTab === "suggested" ? suggested : activeTab === "open" ? joinable : activeTab === "my_matches" ? myMatches : [];

  if (authLoading || !user) return null;

  const renderMatch = (m: Match) => {
    const member = isMember(m);
    const isHost = m.creator_id === user.id;
    const freeSeats = Math.max(0, m.num_players - m.participants.length);
    return (
      <div key={m.id} className="bg-white rounded-2xl border border-zinc-200/90 shadow-xs p-5 space-y-3.5">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h3 className="font-black text-zinc-950 text-base sm:text-lg leading-snug">{m.venue_name || "Cụm sân"}</h3>
            <p className="text-xs sm:text-sm text-zinc-600 mt-0.5">
              {m.court_name ? `${m.court_name} • ` : ""}
              {formatDisplayDate(m.date)} • {m.start_time.slice(0, 5)} - {m.end_time.slice(0, 5)}
            </p>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {m.compatibility != null && !member && (
              <span
                className="px-2.5 py-1 rounded-full text-xs font-bold bg-zinc-900 text-white"
                title="Xác suất phù hợp do mô hình ước lượng giữa bạn và các thành viên hiện có của phòng"
              >
                Phù hợp {m.compatibility.toFixed(0)}%
              </span>
            )}
            <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${STATUS_TONE[m.status]}`}>{STATUS_LABEL[m.status]}</span>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 text-[11px] font-medium">
          <Chip>{purposeLabel(m.purpose)}</Chip>
          <Chip>{m.required_skill != null ? `Trình độ khoảng ${m.required_skill.toFixed(1)}` : "Mọi trình độ"}</Chip>
          <Chip>
            {m.participants.length}/{m.num_players} người{m.status === "OPEN" ? ` • còn ${freeSeats} chỗ` : ""}
          </Chip>
          {m.booking_code && <Chip>Đã có sân ({m.booking_code})</Chip>}
        </div>

        {m.notes && <p className="text-xs text-zinc-600 leading-relaxed">{m.notes}</p>}

        <ul className="space-y-1">
          {m.participants.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 text-xs bg-zinc-50 border border-zinc-100 rounded-lg px-3 py-1.5">
              <span className="font-semibold text-zinc-900 truncate">
                {p.user_name || `Người chơi #${p.user_id}`}
                {p.user_id === m.creator_id && <span className="ml-1.5 text-[10px] font-bold text-amber-700">Chủ phòng</span>}
              </span>
              <span className="text-zinc-500 shrink-0">
                {p.skill_level != null ? `${p.skill_level.toFixed(1)} • ` : ""}
                {playStyleLabel(p.play_style, true)}
                {p.phone ? ` • ${p.phone}` : ""}
              </span>
            </li>
          ))}
        </ul>

        <div className="flex justify-end gap-2 pt-1">
          {member && (m.status === "OPEN" || m.status === "FULL") && (
            <button
              type="button"
              disabled={busyMatchId === m.id}
              onClick={() => handleLeave(m)}
              className="px-3.5 py-2 rounded-xl border border-zinc-200 hover:border-rose-200 hover:bg-rose-50 text-zinc-600 hover:text-rose-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
            >
              {isHost ? "Hủy Phòng" : "Rời Phòng"}
            </button>
          )}
          {!member && m.status === "OPEN" && (
            <button
              type="button"
              disabled={busyMatchId === m.id}
              onClick={() => handleJoin(m)}
              className="px-4 py-2 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs font-bold btn-press cursor-pointer shadow-xs transition disabled:opacity-50"
            >
              {busyMatchId === m.id ? "Đang xử lý..." : "Tham Gia Phòng"}
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900 selection:bg-zinc-900 selection:text-white">
      <Navbar />

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-7 sm:py-9 flex-1 w-full">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 tracking-tight">Ghép Trận</h1>
            <p className="text-xs sm:text-sm text-zinc-500 mt-1">Tham gia phòng đang tuyển người, hoặc mở phòng trên lịch sân bạn đã đặt.</p>
          </div>
          <Link
            href="/matches/create"
            className="px-4 py-2 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white font-bold text-xs shadow-xs transition-all btn-press self-start sm:self-auto"
          >
            + Mở Phòng Đấu
          </Link>
        </div>

        {/* Thông tin trung thực về mô hình gợi ý */}
        {model && (
          <div className="mb-4 p-3.5 rounded-2xl bg-white border border-zinc-200 text-[11px] sm:text-xs text-zinc-600 leading-relaxed space-y-1.5">
            {model.available ? (
              <>
                <p>
                  <strong className="text-zinc-900">Độ phù hợp</strong> do mô hình Random Forest ước lượng từ 5 yếu tố: chênh lệch
                  trình độ, khoảng cách, độ trùng khung giờ rảnh, mục đích chơi và lối đánh.
                </p>
                <p>
                  {model.data_source === "survey"
                    ? `Mô hình được huấn luyện từ ${model.n_samples} câu trả lời khảo sát của ${model.n_raters} người chơi.`
                    : "Mô hình hiện được khởi tạo từ dữ liệu tổng hợp theo quy tắc chuyên môn, chưa phải hành vi người chơi thật - hãy coi con số là tham khảo."}{" "}
                  <Link href="/survey" className="font-semibold text-zinc-900 underline">
                    Trả lời khảo sát để cải thiện gợi ý
                  </Link>
                </p>
              </>
            ) : (
              <p>Mô hình gợi ý chưa sẵn sàng nên các phòng được liệt kê theo thời gian, không kèm độ phù hợp.</p>
            )}
            {missing.length > 0 && (
              <p className="text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2">
                Hồ sơ của bạn còn thiếu {missing.map((f) => PROFILE_FIELD_LABEL[f] || f).join(", ")}.{" "}
                <Link href="/profile" className="font-semibold underline">
                  Bổ sung hồ sơ
                </Link>{" "}
                để gợi ý chính xác hơn.
              </p>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 mb-5 border-b border-zinc-200 pb-2 overflow-x-auto scrollbar-none">
          {TABS.map(({ key, label }) => {
            const count = key === "suggested" ? suggested.length : key === "open" ? joinable.length : key === "my_matches" ? myMatches.length : partners?.items.length || 0;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setActiveTab(key)}
                className={`px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition cursor-pointer shrink-0 ${
                  activeTab === key ? "bg-zinc-900 text-white shadow-xs" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 hover:text-zinc-900"
                }`}
              >
                {label} ({count})
              </button>
            );
          })}
        </div>

        {loading ? (
          <div className="bg-white rounded-2xl p-5 border border-zinc-200 animate-pulse h-28" />
        ) : activeTab === "partners" ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs text-zinc-600">
              <span>Bán kính:</span>
              {RADIUS_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setRadius(option)}
                  className={`px-2.5 py-1 rounded-lg border font-semibold cursor-pointer ${
                    radius === option ? "bg-zinc-900 text-white border-zinc-900" : "bg-white border-zinc-200 hover:bg-zinc-100"
                  }`}
                >
                  {option === 0 ? "Tất cả" : `${option} km`}
                </button>
              ))}
            </div>
            {(partners?.items.length || 0) === 0 ? (
              <Empty title="Chưa có gợi ý bạn chơi" hint="Hãy khai trình độ và vị trí trong hồ sơ, hoặc mở rộng bán kính tìm kiếm." />
            ) : (
              partners!.items.map((p) => (
                <div key={p.user_id} className="bg-white rounded-2xl border border-zinc-200/90 shadow-xs p-4 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-bold text-zinc-950 text-sm truncate">{p.full_name}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      {p.skill_level != null ? `Trình độ ${p.skill_level.toFixed(1)}` : "Chưa khai trình độ"} • {playStyleLabel(p.play_style, true)} •{" "}
                      {purposeLabel(p.purpose)}
                    </p>
                    <p className="text-[11px] text-zinc-500 mt-0.5">
                      {p.distance_km != null ? `Cách khoảng ${p.distance_km.toFixed(1)} km` : "Chưa rõ khoảng cách"} • Trùng {p.shared_slots} khung
                      giờ rảnh
                    </p>
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-zinc-900 text-white shrink-0">{p.probability.toFixed(0)}%</span>
                </div>
              ))
            )}
            <p className="text-[11px] text-zinc-500">
              Để bảo vệ quyền riêng tư, thông tin liên hệ chỉ hiển thị giữa các thành viên cùng phòng. Hãy mở phòng và chờ bạn chơi tham gia.
            </p>
          </div>
        ) : listed.length === 0 ? (
          <Empty
            title={
              activeTab === "my_matches"
                ? "Bạn chưa tham gia phòng nào"
                : activeTab === "suggested"
                ? "Chưa có phòng nào được chấm độ phù hợp"
                : "Hiện không có phòng nào đang tuyển người"
            }
            hint={
              activeTab === "suggested"
                ? "Xem tab “Tất Cả Phòng Mở”, hoặc bổ sung trình độ trong hồ sơ để mô hình chấm điểm."
                : "Bạn có thể đặt sân rồi mở phòng để tìm người chơi cùng."
            }
          />
        ) : (
          <div className="space-y-3">{listed.map(renderMatch)}</div>
        )}
      </main>

      {confirm && (
        <div className="fixed inset-0 z-50 bg-zinc-950/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-sm w-full p-5 shadow-xl border border-zinc-200">
            <p className="text-sm text-zinc-800 leading-relaxed">{confirm.message}</p>
            <div className="flex gap-2 mt-4">
              <button type="button" onClick={() => setConfirm(null)} className="flex-1 py-2 rounded-xl bg-zinc-100 hover:bg-zinc-200 text-zinc-700 text-xs font-semibold cursor-pointer">
                Không
              </button>
              <button type="button" onClick={confirm.onConfirm} className="flex-1 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold cursor-pointer">
                Đồng Ý
              </button>
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="px-2.5 py-1 rounded-full bg-zinc-100 border border-zinc-200 text-zinc-700">{children}</span>;
}

function Empty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="text-center py-12 bg-white rounded-2xl border border-zinc-200 p-6">
      <h3 className="font-semibold text-zinc-900 text-sm">{title}</h3>
      <p className="text-xs text-zinc-500 mt-1 max-w-sm mx-auto">{hint}</p>
    </div>
  );
}

export default function MatchesPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-zinc-50" />}>
      <MatchesContent />
    </Suspense>
  );
}
