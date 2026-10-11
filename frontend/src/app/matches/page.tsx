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
  is_recommended?: boolean; // độ phù hợp đạt ngưỡng đề xuất của máy chủ
}

interface ModelInfo {
  available: boolean;
  error?: string | null;
  data_source?: string | null;
  n_samples?: number | null;
  n_raters?: number | null;
  metrics?: { accuracy?: number; roc_auc?: number } | null;
  recommend_threshold?: number | null; // độ phù hợp tối thiểu (0-100) để một phòng được đề xuất
  missing_profile_fields?: string[];
}

type Tab = "suggested" | "open" | "my_matches";

const TABS: { key: Tab; label: string }[] = [
  { key: "suggested", label: "Phòng Đề Xuất" },
  { key: "open", label: "Tất Cả Phòng Mở" },
  { key: "my_matches", label: "Phòng Của Tôi" },
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

function MatchesContent() {
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { success: toastSuccess, error: toastError } = useToast();

  const [matches, setMatches] = useState<Match[]>([]);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("suggested");
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
    const [matchData, modelData] = await Promise.all([
      fetchApi(`/matches${position ? `?${position}` : ""}`).catch(() => []),
      fetchApi("/ml/model-info").catch(() => null),
    ]);
    setMatches(Array.isArray(matchData) ? matchData : []);
    setModel(modelData);
    setLoading(false);
  }, []);

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

  // Phòng còn tuyển người mà mình chưa tham gia; phòng mô hình chấm cao hơn xếp trước
  const joinable = useMemo(
    () =>
      matches
        .filter((m) => m.status === "OPEN" && !isMember(m))
        .sort((a, b) => (b.compatibility ?? -1) - (a.compatibility ?? -1)),
    [matches, isMember],
  );
  // Đề xuất của mô hình: chỉ những phòng đạt ngưỡng phù hợp do máy chủ quy định
  const suggested = useMemo(() => joinable.filter((m) => m.is_recommended), [joinable]);
  const myMatches = useMemo(() => matches.filter(isMember), [matches, isMember]);

  if (authLoading || !user) return null;

  const threshold = model?.recommend_threshold ?? null;
  // Đã chọn vị trí trên trang chủ thì không coi là thiếu vị trí, dù hồ sơ chưa lưu
  const missing = (model?.missing_profile_fields || []).filter((f) => f !== "location" || !getSavedLocation());
  const listed = activeTab === "suggested" ? suggested : activeTab === "open" ? joinable : myMatches;

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
                className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                  m.is_recommended ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600 border border-zinc-200"
                }`}
                title="Xác suất phù hợp do mô hình ước lượng giữa bạn và các thành viên hiện có của phòng"
              >
                {m.is_recommended ? "Mô hình đề xuất • " : "Phù hợp "}
                {m.compatibility.toFixed(0)}%
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

        {/* Mô hình đề xuất phòng như thế nào */}
        {model && (
          <div className="mb-4 p-3.5 rounded-2xl bg-white border border-zinc-200 text-[11px] sm:text-xs text-zinc-600 leading-relaxed space-y-1.5">
            {model.available ? (
              <p>
                <strong className="text-zinc-900">Phòng đề xuất</strong> là các phòng đang tuyển người mà mô hình Random Forest ước lượng
                độ phù hợp giữa bạn và các thành viên của phòng {threshold != null ? `từ ${threshold}% trở lên` : "ở mức cao"}, dựa trên
                chênh lệch trình độ, khoảng cách tới sân, khung giờ rảnh, mục đích chơi và lối đánh.{" "}
                {model.data_source === "survey"
                  ? `Mô hình học từ ${model.n_samples} câu trả lời khảo sát của ${model.n_raters} người chơi.`
                  : "Mô hình hiện học từ dữ liệu tổng hợp, chưa phải lựa chọn của người chơi thật."}{" "}
                <Link href="/survey" className="font-semibold text-zinc-900 underline">
                  Trả lời khảo sát để mô hình học từ bạn
                </Link>
              </p>
            ) : (
              <p>Mô hình ghép cặp chưa sẵn sàng nên chưa có phòng đề xuất; các phòng đang mở được liệt kê theo thời gian.</p>
            )}
            {missing.length > 0 && (
              <p className="text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2">
                Hồ sơ của bạn còn thiếu {missing.map((f) => PROFILE_FIELD_LABEL[f] || f).join(", ")}.{" "}
                <Link href="/profile" className="font-semibold underline">
                  Bổ sung hồ sơ
                </Link>{" "}
                để mô hình đề xuất chính xác hơn.
              </p>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 mb-5 border-b border-zinc-200 pb-2 overflow-x-auto scrollbar-none">
          {TABS.map(({ key, label }) => {
            const count = key === "suggested" ? suggested.length : key === "open" ? joinable.length : myMatches.length;
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
        ) : listed.length === 0 ? (
          <Empty
            title={
              activeTab === "my_matches"
                ? "Bạn chưa tham gia phòng nào"
                : activeTab === "suggested"
                ? "Chưa có phòng nào mô hình đánh giá phù hợp cao với bạn"
                : "Hiện không có phòng nào đang tuyển người"
            }
            hint={
              activeTab === "suggested"
                ? "Xem tab “Tất Cả Phòng Mở” để thấy mọi phòng đang tuyển, hoặc đặt sân rồi mở phòng của bạn."
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
