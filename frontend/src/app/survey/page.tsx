"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { fetchApi, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { playStyleLabel, purposeLabel } from "@/lib/player";

interface SurveyPair {
  candidate: {
    skill_level: number;
    distance_km: number;
    purpose: string;
    play_style: string;
    age_gap: number; // chênh lệch tuổi so với người trả lời (năm)
  };
  features: Record<string, number>;
  signature: string; // chữ ký của máy chủ: câu trả lời chỉ được ghi nhận khi đặc trưng không bị sửa
}

const PAIRS_PER_ROUND = 10;

const ageGapLabel = (gap: number) => (gap <= 0 ? "cùng tuổi với bạn" : `hơn kém bạn ${gap} tuổi`);

/**
 * Khảo sát thu nhãn thật cho mô hình ghép cặp: người chơi xem các hồ sơ giả định và trả lời
 * "có muốn chơi cùng người này không". Câu trả lời là dữ liệu huấn luyện thay cho dữ liệu tổng hợp.
 */
export default function MatchingSurveyPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const { success: toastSuccess, error: toastError } = useToast();
  const [pairs, setPairs] = useState<SurveyPair[]>([]);
  const [answers, setAnswers] = useState<Record<number, boolean>>({});
  const [needsSkill, setNeedsSkill] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [totalSaved, setTotalSaved] = useState(0);

  useEffect(() => {
    if (!isLoading && !user) router.push("/login?next=/survey");
  }, [user, isLoading, router]);

  // Lượt đầu tải khi mở trang (loading ban đầu đã là true); các lượt sau bật loading ở nơi gọi
  const loadPairs = useCallback(
    () =>
      fetchApi(`/ml/survey/pairs?count=${PAIRS_PER_ROUND}`)
        .then((data) => {
          setPairs(data.pairs || []);
          setNeedsSkill((data.missing_profile_fields || []).includes("skill_level"));
          setAnswers({});
        })
        .catch((err) => toastError(errorMessage(err, "Không tải được khảo sát.")))
        .finally(() => setLoading(false)),
    [toastError],
  );

  useEffect(() => {
    if (user) loadPairs();
  }, [user, loadPairs]);

  const answeredCount = Object.keys(answers).length;

  const submit = async () => {
    setSending(true);
    try {
      const payload = Object.entries(answers).map(([index, label]) => ({
        features: pairs[Number(index)].features,
        signature: pairs[Number(index)].signature,
        label,
      }));
      const result = await fetchApi("/ml/survey/answers", { method: "POST", body: JSON.stringify({ answers: payload }) });
      setTotalSaved((prev) => prev + (result.saved || 0));
      toastSuccess(`Đã ghi nhận ${result.saved} câu trả lời. Cảm ơn bạn!`);
      setLoading(true);
      await loadPairs();
    } catch (err) {
      toastError(errorMessage(err, "Chưa gửi được câu trả lời."));
    } finally {
      setSending(false);
    }
  };

  if (isLoading || !user) return null;

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 font-sans text-zinc-900">
      <Navbar />
      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-8 flex-1 w-full">
        <Link href="/matches" className="text-xs font-semibold text-zinc-500 hover:text-zinc-950">
          ← Quay lại Ghép Trận
        </Link>
        <h1 className="text-2xl sm:text-3xl font-black text-zinc-950 tracking-tight mt-2">Khảo Sát Ghép Cặp</h1>
        <p className="text-xs sm:text-sm text-zinc-600 mt-1.5 leading-relaxed">
          Với mỗi người chơi giả định dưới đây, hãy cho biết bạn <strong>có muốn ghép chơi cùng</strong> hay không. Câu trả lời của bạn
          giúp hệ thống gợi ý phòng đấu hợp với bạn hơn. Không có câu trả lời đúng hay sai.
        </p>
        {totalSaved > 0 && (
          <p className="mt-3 text-xs font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-2">
            Bạn đã đóng góp {totalSaved} câu trả lời trong phiên này.
          </p>
        )}

        {loading ? (
          <div className="mt-6 bg-white rounded-2xl p-6 border border-zinc-200 animate-pulse h-32" />
        ) : needsSkill || pairs.length === 0 ? (
          <div className="mt-6 bg-white rounded-2xl p-6 border border-zinc-200 text-center space-y-3">
            <p className="text-sm font-semibold text-zinc-900">Cần khai trình độ trước khi làm khảo sát</p>
            <p className="text-xs text-zinc-600">Các hồ sơ giả định được tạo xoay quanh trình độ của chính bạn.</p>
            <Link href="/profile" className="inline-block px-5 py-2.5 bg-zinc-950 text-white rounded-xl text-xs font-bold">
              Cập Nhật Hồ Sơ →
            </Link>
          </div>
        ) : (
          <>
            <ol className="mt-6 space-y-3">
              {pairs.map((pair, index) => {
                const answer = answers[index];
                const c = pair.candidate;
                return (
                  <li key={pair.signature} className="bg-white rounded-2xl border border-zinc-200/90 shadow-xs p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="text-xs sm:text-sm text-zinc-700 space-y-0.5">
                      <p className="font-bold text-zinc-950">
                        Người chơi {index + 1}: trình độ {c.skill_level.toFixed(1)} • {playStyleLabel(c.play_style, true)}
                      </p>
                      <p>
                        Cách bạn khoảng {c.distance_km} km • {purposeLabel(c.purpose)} • {ageGapLabel(c.age_gap)}
                      </p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button
                        type="button"
                        aria-pressed={answer === true}
                        onClick={() => setAnswers((prev) => ({ ...prev, [index]: true }))}
                        className={`px-4 py-2 rounded-xl text-xs font-bold border cursor-pointer transition ${
                          answer === true ? "bg-emerald-600 border-emerald-600 text-white" : "bg-white border-zinc-200 text-zinc-700 hover:border-emerald-400"
                        }`}
                      >
                        Muốn ghép
                      </button>
                      <button
                        type="button"
                        aria-pressed={answer === false}
                        onClick={() => setAnswers((prev) => ({ ...prev, [index]: false }))}
                        className={`px-4 py-2 rounded-xl text-xs font-bold border cursor-pointer transition ${
                          answer === false ? "bg-zinc-900 border-zinc-900 text-white" : "bg-white border-zinc-200 text-zinc-700 hover:border-zinc-400"
                        }`}
                      >
                        Không
                      </button>
                    </div>
                  </li>
                );
              })}
            </ol>

            <div className="mt-5 flex items-center justify-between gap-3">
              <span className="text-xs text-zinc-500">
                Đã trả lời {answeredCount}/{pairs.length}
              </span>
              <button
                type="button"
                disabled={sending || answeredCount === 0}
                onClick={submit}
                className="px-6 py-2.5 rounded-xl bg-zinc-950 hover:bg-zinc-800 text-white text-xs font-bold disabled:opacity-50 cursor-pointer"
              >
                {sending ? "Đang gửi..." : "Gửi Câu Trả Lời & Xem Lượt Mới"}
              </button>
            </div>
          </>
        )}
      </main>
      <Footer />
    </div>
  );
}
