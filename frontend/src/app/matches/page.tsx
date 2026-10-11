"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState, Suspense } from "react";
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
  const { success: toastSuccess, error: toastError, info: toastInfo } = useToast();

  const [matches, setMatches] = useState<Match[]>([]);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("suggested");
  const [busyMatchId, setBusyMatchId] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<number[]>([]); // phòng đang mở phần chi tiết
  const [confirm, setConfirm] = useState<{ message: string; onConfirm: () => void } | null>(null);

  const { lastMessage } = useWebSocket("/api/v1/ws/live");

  useEffect(() => {
    if (!authLoading && !user) router.push("/login?next=/matches");
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

  // Phòng mình đang ở bị hủy thì thẻ rời khỏi mục Phòng Của Tôi: báo một câu để người chơi biết lý do
  const activeRooms = useRef<Map<number, string>>(new Map());
  useEffect(() => {
    const current = new Map<number, string>();
    for (const m of matches) {
      if (!isMember(m)) continue;
      if (m.status === "OPEN" || m.status === "FULL") {
        current.set(m.id, `${m.venue_name || "cụm sân"} lúc ${m.start_time.slice(0, 5)} ${formatDisplayDate(m.date)}`);
      } else if (m.status === "CANCELLED" && activeRooms.current.has(m.id)) {
        toastInfo(`Phòng tại ${activeRooms.current.get(m.id)} đã bị hủy.`);
      }
    }
    activeRooms.current = current;
  }, [matches, isMember, toastInfo]);

  const toggleExpand = (id: number) =>
    setExpandedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));

  const handleJoin = async (match: Match) => {
    setBusyMatchId(match.id);
    try {
      await fetchApi(`/matches/${match.id}/join`, { method: "POST" });
      toastSuccess("Đã tham gia phòng. Xem số điện thoại các thành viên trong mục “Phòng Của Tôi”.");
      await loadData();
      // Mở sẵn phần chi tiết của phòng vừa vào để thấy ngay số điện thoại các thành viên
      setExpandedIds((prev) => (prev.includes(match.id) ? prev : [...prev, match.id]));
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
        activeRooms.current.delete(match.id); // tự mình rời/hủy thì không cần báo "phòng đã bị hủy" nữa
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
  // Phòng của tôi: chỉ những phòng còn dùng được (đang tuyển hoặc đã đủ người); phòng đã hủy hay đã kết thúc không hiện nữa
  const myMatches = useMemo(
    () => matches.filter((m) => isMember(m) && (m.status === "OPEN" || m.status === "FULL")),
    [matches, isMember],
  );

  if (authLoading || !user) return null;

  // Đã chọn vị trí trên trang chủ thì không coi là thiếu vị trí, dù hồ sơ chưa lưu
  const missing = (model?.missing_profile_fields || []).filter((f) => f !== "location" || !getSavedLocation());
  const listed = activeTab === "suggested" ? suggested : activeTab === "open" ? joinable : myMatches;

  const renderMatch = (m: Match) => {
    const member = isMember(m);
    const isHost = m.creator_id === user.id;
    const freeSeats = Math.max(0, m.num_players - m.participants.length);
    const expanded = expandedIds.includes(m.id);
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
                title="Độ phù hợp giữa bạn và các thành viên hiện có của phòng"
              >
                {m.is_recommended ? "Rất hợp với bạn • " : "Độ phù hợp "}
                {m.compatibility.toFixed(0)}%
              </span>
            )}
            <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${STATUS_TONE[m.status]}`}>{STATUS_LABEL[m.status]}</span>
          </div>
        </div>

        {/* Dòng tóm tắt luôn hiện; ghi chú, danh sách thành viên và các nhãn phụ nằm trong phần chi tiết */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
          <div className="text-xs sm:text-sm text-zinc-600 flex-1 min-w-[15rem] space-y-0.5">
            <p>
              Chủ phòng <span className="font-semibold text-zinc-900">{m.creator_name || `Người chơi #${m.creator_id}`}</span>
              {isHost ? " (bạn)" : ""}
            </p>
            <p>
              {m.required_skill != null ? `Trình độ khoảng ${m.required_skill.toFixed(1)}` : "Mọi trình độ"} • {m.participants.length}/
              {m.num_players} người{m.status === "OPEN" ? `, còn ${freeSeats} chỗ` : ""}
            </p>
          </div>
          <div className="flex gap-2 ml-auto shrink-0">
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => toggleExpand(m.id)}
              className={`px-3.5 py-2 rounded-xl border text-xs font-semibold transition cursor-pointer ${
                expanded ? "bg-zinc-900 border-zinc-900 text-white" : "border-zinc-200 hover:bg-zinc-100 text-zinc-700 bg-white"
              }`}
            >
              {expanded ? "Đóng" : "Chi tiết"}
            </button>
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

        {expanded && (
          <div className="pt-3.5 border-t border-zinc-100 space-y-3 animate-in fade-in duration-150">
            <div className="flex flex-wrap gap-1.5 text-[11px] font-medium">
              <Chip>{purposeLabel(m.purpose)}</Chip>
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
          </div>
        )}
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

        {/* Nhắc hoàn thiện hồ sơ để gợi ý sát hơn */}
        {missing.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl bg-white border border-zinc-200">
            <p className="text-xs sm:text-sm text-zinc-700">
              Thêm <strong className="text-zinc-950">{missing.map((f) => PROFILE_FIELD_LABEL[f] || f).join(", ")}</strong> vào hồ sơ để
              nhận gợi ý phòng sát với bạn hơn.
            </p>
            <Link
              href="/profile"
              className="px-3.5 py-1.5 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs font-bold shrink-0"
            >
              Cập nhật hồ sơ
            </Link>
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

        {!loading && activeTab === "suggested" && suggested.length > 0 && (
          <p className="text-xs text-zinc-500 mb-3">
            Những phòng hợp với bạn nhất, dựa trên trình độ, khu vực, mục đích và phong cách chơi.
          </p>
        )}

        {loading ? (
          <div className="bg-white rounded-2xl p-5 border border-zinc-200 animate-pulse h-28" />
        ) : listed.length === 0 ? (
          <Empty
            title={
              activeTab === "my_matches"
                ? "Hiện bạn chưa ở trong phòng nào"
                : activeTab === "suggested"
                ? "Chưa có phòng nào thật sự hợp với bạn lúc này"
                : "Hiện không có phòng nào đang tuyển người"
            }
            hint={
              activeTab === "suggested"
                ? "Xem tab “Tất Cả Phòng Mở”, hoặc đặt sân rồi mở phòng của riêng bạn."
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
