"use client";

import React from "react";
import { formatVND } from "@/lib/api";
import { BOOKING_STATUS_LABEL, MATCH_STATUS_LABEL, VENUE_STATUS_LABEL, statusTone } from "@/lib/labels";
import { TabProps } from "@/lib/types";
import { Badge, Card } from "@/components/ui";

function countBy<T>(items: T[], key: (item: T) => string): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[key(item)] = (acc[key(item)] || 0) + 1;
    return acc;
  }, {});
}

export default function OverviewTab({ data }: TabProps) {
  const { users, venues, bookings, matches, stats } = data;
  const roles = countBy(users, (u) => u.role);
  const venueStatus = countBy(venues, (v) => v.status);
  const bookingStatus = countBy(bookings, (b) => b.status);
  const matchStatus = countBy(matches, (m) => m.status);
  const pendingVenues = venues.filter((v) => v.status === "PENDING");

  const kpis = [
    { label: "Thực thu toàn hệ thống", value: formatVND(stats?.total_revenue), hint: `Đã thu ${formatVND(stats?.collected_amount)} • đã hoàn ${formatVND(stats?.refunded_amount)}` },
    { label: "Đơn đặt sân", value: String(bookings.length), hint: `${stats?.completed_bookings ?? 0} hoàn tất • ${stats?.pending_refunds ?? 0} chờ hoàn tiền` },
    { label: "Cụm sân", value: String(venues.length), hint: `${venueStatus.ACTIVE || 0} đang hoạt động • ${stats?.total_courts ?? 0} sân` },
    { label: "Tài khoản", value: String(users.length), hint: `${roles.PLAYER || 0} người chơi • ${roles.OWNER || 0} chủ sân • ${roles.STAFF || 0} nhân viên` },
    { label: "Phòng đấu", value: String(matches.length), hint: `${matchStatus.OPEN || 0} đang tuyển người` },
  ];

  const statusGroups = [
    { title: "Đơn đặt sân", counts: bookingStatus, labels: BOOKING_STATUS_LABEL, empty: "Chưa có đơn nào." },
    { title: "Cụm sân", counts: venueStatus, labels: VENUE_STATUS_LABEL, empty: "Chưa có cụm sân nào." },
    { title: "Phòng đấu", counts: matchStatus, labels: MATCH_STATUS_LABEL, empty: "Chưa có phòng đấu nào." },
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

      <Card className="p-5">
        <h3 className="text-sm font-bold text-slate-900">Phân bố trạng thái</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-3">
          {statusGroups.map((group) => (
            <div key={group.title}>
              <p className="text-xs font-bold text-slate-500 mb-1.5">{group.title}</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(group.counts).map(([status, count]) => (
                  <Badge key={status} tone={statusTone(status)}>{group.labels[status] || status}: {count}</Badge>
                ))}
                {Object.keys(group.counts).length === 0 && <span className="text-xs text-slate-500">{group.empty}</span>}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
