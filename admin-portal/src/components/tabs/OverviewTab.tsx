"use client";

import React from "react";
import { formatDateTime, formatVND } from "@/lib/api";
import { BOOKING_STATUS_LABEL, VENUE_STATUS_LABEL, statusTone } from "@/lib/labels";
import { TabProps } from "@/lib/types";
import { Badge, Card } from "@/components/ui";

const FEATURE_LABEL: Record<string, string> = {
  level_diff: "Chênh lệch trình độ",
  distance_km: "Khoảng cách",
  availability_overlap: "Độ trùng khung giờ rảnh",
  purpose_match: "Cùng mục đích chơi",
  style_match: "Lối đánh tương thích",
};

const percent = (value: number | undefined) => (value == null ? "—" : `${(value * 100).toFixed(1)}%`);

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

        {/* Thông tin trung thực về mô hình ghép cặp */}
        <Card className="p-5 space-y-3">
          <h3 className="text-sm font-bold text-slate-900">Mô hình ghép cặp người chơi</h3>
          {!model ? (
            <p className="text-xs text-slate-500">Không tải được thông tin mô hình.</p>
          ) : !model.available ? (
            <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">{model.error || "Mô hình chưa sẵn sàng."}</p>
          ) : (
            <>
              <p className="text-xs text-slate-600 leading-relaxed">
                {model.algorithm} • {model.n_samples?.toLocaleString("vi-VN")} mẫu • huấn luyện {formatDateTime(model.trained_at)}
                <br />
                Nguồn dữ liệu:{" "}
                <strong className="text-slate-900">
                  {model.data_source === "survey"
                    ? `khảo sát thật (${model.n_raters} người trả lời)`
                    : model.data_source === "simulated"
                    ? `phiếu ghép cặp mô phỏng lưu trong CSDL (${(model.n_simulated ?? 0).toLocaleString("vi-VN")} phiếu của ${model.n_raters} tài khoản demo${
                        model.n_survey ? `, kèm ${model.n_survey} nhãn khảo sát thật` : ""
                      })`
                    : "dữ liệu tổng hợp khởi tạo theo quy tắc"}
                </strong>
                <br />
                Cách đánh giá: {model.evaluation_protocol}
              </p>
              {model.data_source !== "survey" && (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2.5 leading-relaxed">
                  Nhãn huấn luyện được sinh từ quy tắc viết tay có cộng nhiễu, nên các chỉ số dưới đây chỉ cho biết mô hình học lại quy tắc tốt
                  đến đâu, không chứng minh chất lượng ghép cặp ngoài thực tế. Cần ít nhất 300 nhãn khảo sát để huấn luyện bằng dữ liệu thật.
                </p>
              )}
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-200">
                    <th className="py-1.5">Phương pháp</th>
                    <th className="py-1.5 text-right">Accuracy</th>
                    <th className="py-1.5 text-right">F1</th>
                    <th className="py-1.5 text-right">ROC-AUC</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="font-bold text-slate-900 border-b border-slate-100">
                    <td className="py-1.5">Random Forest (đang dùng)</td>
                    <td className="py-1.5 text-right">{percent(model.metrics?.accuracy)}</td>
                    <td className="py-1.5 text-right">{percent(model.metrics?.f1)}</td>
                    <td className="py-1.5 text-right">{model.metrics?.roc_auc?.toFixed(3) ?? "—"}</td>
                  </tr>
                  {Object.entries(model.baselines || {}).map(([name, m]) => (
                    <tr key={name} className="text-slate-600 border-b border-slate-100">
                      <td className="py-1.5">{name}</td>
                      <td className="py-1.5 text-right">{percent(m.accuracy)}</td>
                      <td className="py-1.5 text-right">{percent(m.f1)}</td>
                      <td className="py-1.5 text-right">{m.roc_auc?.toFixed(3) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div>
                <p className="text-xs font-bold text-slate-500 mb-1.5">Mức đóng góp của đặc trưng</p>
                <ul className="space-y-1">
                  {Object.entries(model.feature_importances || {}).sort((a, b) => b[1] - a[1]).map(([feature, weight]) => (
                    <li key={feature} className="flex items-center gap-2 text-xs text-slate-600">
                      <span className="w-44 shrink-0">{FEATURE_LABEL[feature] || feature}</span>
                      <span className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <span className="block h-full bg-blue-600 rounded-full" style={{ width: `${Math.round(weight * 100)}%` }} />
                      </span>
                      <span className="w-12 text-right">{percent(weight)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
          {model?.survey && (
            <p className="text-xs text-slate-600 pt-2 border-t border-slate-100">
              Bảng <code className="bg-slate-100 px-1 rounded">pair_feedback</code> đang có{" "}
              <strong className="text-slate-900">{(model.survey.simulated ?? 0).toLocaleString("vi-VN")}</strong> phiếu mô phỏng và{" "}
              <strong className="text-slate-900">{model.survey.labels}</strong> nhãn khảo sát thật ({model.survey.positive} “muốn ghép”, từ{" "}
              {model.survey.raters} người chơi). Huấn luyện lại bằng lệnh{" "}
              <code className="bg-slate-100 px-1 rounded">python manage.py train-model</code>.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
