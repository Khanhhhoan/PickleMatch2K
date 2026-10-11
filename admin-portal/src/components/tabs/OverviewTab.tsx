"use client";

import React from "react";
import { formatVND } from "@/lib/api";
import { BOOKING_STATUS_LABEL, VENUE_STATUS_LABEL, statusTone } from "@/lib/labels";
import { TabProps } from "@/lib/types";
import { Badge, Card } from "@/components/ui";

const FEATURE_LABEL: Record<string, string> = {
  level_diff: "Chênh lệch trình độ",
  distance_km: "Khoảng cách tới sân",
  availability_overlap: "Trùng khung giờ rảnh",
  purpose_match: "Cùng mục đích chơi",
  style_match: "Hợp lối đánh",
};

// Các cách làm đơn giản hơn dùng để so sánh, theo tên dễ hiểu
const BASELINE_LABEL: Record<string, string> = {
  "Hồi quy logistic": "Hồi quy logistic",
  "Luật: chênh trình độ <= 0.5": "Chỉ xét chênh lệch trình độ",
  "Đoán theo lớp đa số": "Đoán theo số đông",
};

const DATA_SOURCE_LABEL: Record<string, string> = {
  survey: "Khảo sát người chơi",
  simulated: "Dữ liệu mô phỏng",
  synthetic_prior: "Dữ liệu mô phỏng",
};

const percent = (value: number | undefined) =>
  value == null ? "—" : `${(value * 100).toLocaleString("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

function ModelFact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-sm font-black text-slate-900 mt-0.5">{value}</div>
      {hint && <div className="text-[11px] text-slate-500">{hint}</div>}
    </div>
  );
}

function countBy<T>(items: T[], key: (item: T) => string): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[key(item)] = (acc[key(item)] || 0) + 1;
    return acc;
  }, {});
}

export default function OverviewTab({ data }: TabProps) {
  const { users, venues, bookings, matches, stats, model } = data;
  const roles = countBy(users, (u) => u.role);
  const venueStatus = countBy(venues, (v) => v.status);
  const bookingStatus = countBy(bookings, (b) => b.status);
  const pendingVenues = venues.filter((v) => v.status === "PENDING");

  const kpis = [
    { label: "Thực thu toàn hệ thống", value: formatVND(stats?.total_revenue), hint: `Đã thu ${formatVND(stats?.collected_amount)} • đã hoàn ${formatVND(stats?.refunded_amount)}` },
    { label: "Đơn đặt sân", value: String(bookings.length), hint: `${stats?.completed_bookings ?? 0} hoàn tất • ${stats?.pending_refunds ?? 0} chờ hoàn tiền` },
    { label: "Cụm sân", value: String(venues.length), hint: `${venueStatus.ACTIVE || 0} đang hoạt động • ${stats?.total_courts ?? 0} sân` },
    { label: "Tài khoản", value: String(users.length), hint: `${roles.PLAYER || 0} người chơi • ${roles.OWNER || 0} chủ sân • ${roles.STAFF || 0} nhân viên` },
    { label: "Phòng đấu", value: String(matches.length), hint: `${matches.filter((m) => m.status === "OPEN").length} đang tuyển người` },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className="p-5">
            <div className="text-xs text-slate-500 font-bold uppercase tracking-wider">{kpi.label}</div>
            <div className="text-xl font-black text-slate-900 mt-2">{kpi.value}</div>
            <div className="text-xs text-slate-500 mt-1">{kpi.hint}</div>
          </Card>
        ))}
      </div>

      {pendingVenues.length > 0 && (
        <Card className="p-4 border-amber-300 bg-amber-50">
          <p className="text-sm font-bold text-amber-900">
            {pendingVenues.length} cụm sân đang chờ duyệt: {pendingVenues.map((v) => v.name).join(", ")}
          </p>
          <p className="text-xs text-amber-800 mt-1">Mở tab “Cụm sân” để duyệt hoặc từ chối. Cụm sân chưa duyệt không hiển thị cho người chơi.</p>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-5 space-y-3">
          <h3 className="text-sm font-bold text-slate-900">Phân bố trạng thái</h3>
          <div>
            <p className="text-xs font-bold text-slate-500 mb-1.5">Đơn đặt sân</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(bookingStatus).map(([status, count]) => (
                <Badge key={status} tone={statusTone(status)}>{BOOKING_STATUS_LABEL[status] || status}: {count}</Badge>
              ))}
              {bookings.length === 0 && <span className="text-xs text-slate-500">Chưa có đơn nào.</span>}
            </div>
          </div>
          <div>
            <p className="text-xs font-bold text-slate-500 mb-1.5">Cụm sân</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(venueStatus).map(([status, count]) => (
                <Badge key={status} tone={statusTone(status)}>{VENUE_STATUS_LABEL[status] || status}: {count}</Badge>
              ))}
            </div>
          </div>
        </Card>

        {/* Mô hình ghép trận */}
        <Card className="p-5 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Mô hình ghép trận</h3>
              <p className="text-xs text-slate-500 mt-0.5">Chấm độ phù hợp giữa người chơi và từng phòng đấu để đề xuất phòng.</p>
            </div>
            {model && (
              <Badge tone={model.available ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-rose-50 text-rose-700 border-rose-200"}>
                {model.available ? "Đang hoạt động" : "Chưa sẵn sàng"}
              </Badge>
            )}
          </div>

          {!model ? (
            <p className="text-xs text-slate-500">Không tải được thông tin mô hình.</p>
          ) : !model.available ? (
            <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">{model.error || "Mô hình chưa sẵn sàng."}</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <ModelFact label="Thuật toán" value={model.algorithm === "RandomForestClassifier" ? "Random Forest" : model.algorithm || "—"} />
                <ModelFact label="Độ chính xác" value={percent(model.metrics?.accuracy)} />
                <ModelFact
                  label="Dữ liệu huấn luyện"
                  value={`${(model.n_samples ?? 0).toLocaleString("vi-VN")} phiếu ghép cặp`}
                  hint={DATA_SOURCE_LABEL[model.data_source || ""]}
                />
                <ModelFact
                  label="Cập nhật lần cuối"
                  value={model.trained_at ? new Date(model.trained_at).toLocaleDateString("vi-VN") : "—"}
                />
              </div>

              <div>
                <p className="text-xs font-bold text-slate-500 mb-1.5">So với cách làm đơn giản hơn</p>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-slate-500 border-b border-slate-200">
                      <th className="py-1.5">Cách làm</th>
                      <th className="py-1.5 text-right">Độ chính xác</th>
                      <th className="py-1.5 text-right">F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="font-bold text-slate-900 border-b border-slate-100">
                      <td className="py-1.5">Random Forest (đang dùng)</td>
                      <td className="py-1.5 text-right">{percent(model.metrics?.accuracy)}</td>
                      <td className="py-1.5 text-right">{percent(model.metrics?.f1)}</td>
                    </tr>
                    {Object.entries(BASELINE_LABEL).map(([key, label]) => {
                      const baseline = model.baselines?.[key];
                      if (!baseline) return null;
                      return (
                        <tr key={key} className="text-slate-600 border-b border-slate-100">
                          <td className="py-1.5">{label}</td>
                          <td className="py-1.5 text-right">{percent(baseline.accuracy)}</td>
                          <td className="py-1.5 text-right">{percent(baseline.f1)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div>
                <p className="text-xs font-bold text-slate-500 mb-1.5">Yếu tố ảnh hưởng tới đề xuất</p>
                <ul className="space-y-1">
                  {Object.entries(model.feature_importances || {}).sort((a, b) => b[1] - a[1]).map(([feature, weight]) => (
                    <li key={feature} className="flex items-center gap-2 text-xs text-slate-600">
                      <span className="w-40 shrink-0">{FEATURE_LABEL[feature] || feature}</span>
                      <span className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <span className="block h-full bg-blue-600 rounded-full" style={{ width: `${Math.round(weight * 100)}%` }} />
                      </span>
                      <span className="w-12 text-right">{percent(weight)}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {(model.survey?.labels ?? 0) > 0 && (
                <p className="text-xs text-slate-500 pt-2 border-t border-slate-100">
                  Người chơi đã gửi {model.survey?.labels} phiếu khảo sát ghép cặp.
                </p>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
