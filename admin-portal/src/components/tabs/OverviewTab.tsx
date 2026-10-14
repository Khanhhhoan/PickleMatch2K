"use client";

import React, { useMemo, useState } from "react";
import { formatLocalDate, formatVND } from "@/lib/api";
import { StatsBucket, StatsUnit, availableYears, buildBuckets } from "@/lib/stats";
import { DailyActivity, TabProps, VenueActivity } from "@/lib/types";
import { Card, Chips } from "@/components/ui";

function countBy<T>(items: T[], key: (item: T) => string): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[key(item)] = (acc[key(item)] || 0) + 1;
    return acc;
  }, {});
}

const UNIT_OPTIONS: { value: StatsUnit; label: string }[] = [
  { value: "day", label: "Theo ngày" },
  { value: "month", label: "Theo tháng" },
  { value: "year", label: "Theo năm" },
];

const SELECT =
  "min-h-9 px-3 py-1.5 bg-white border border-[#dde4ef] rounded-xl text-xs font-bold text-[#263b53] outline-none focus:border-[#476cf3] cursor-pointer";

/** Biểu đồ cột cùng kiểu với "Doanh thu 7 ngày" của khu vực chủ sân. */
function BarChart({
  buckets,
  value,
  format,
  short,
  tone,
  empty,
}: {
  buckets: StatsBucket[];
  value: (bucket: StatsBucket) => number;
  format: (amount: number) => string;
  short: (amount: number) => string;
  tone: { current: string; other: string };
  empty: string;
}) {
  const max = Math.max(1, ...buckets.map((bucket) => Math.abs(value(bucket))));
  const hasData = buckets.some((bucket) => value(bucket) !== 0);
  const dense = buckets.length > 12;
  const gap = dense ? "gap-1" : "gap-3";

  return (
    <div className="relative mt-3">
      <div className={`flex items-end ${gap} h-40 border-b border-[#e8edf3]`}>
        {buckets.map((bucket) => {
          const amount = value(bucket);
          return (
            <div key={bucket.key} className="flex-1 min-w-0 flex flex-col items-center justify-end h-full gap-1.5" title={`${bucket.title}: ${format(amount)}`}>
              {!dense && <span className="text-[10px] font-bold text-[#51627c] whitespace-nowrap">{amount !== 0 ? short(amount) : ""}</span>}
              <div
                className={`w-full ${dense ? "" : "max-w-14"} rounded-t-md ${amount < 0 ? "bg-rose-300" : bucket.current ? tone.current : tone.other}`}
                style={{ height: amount === 0 ? "3px" : `${Math.max(6, (Math.abs(amount) / max) * 100)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className={`flex ${gap} mt-1.5`}>
        {buckets.map((bucket) => (
          <span
            key={bucket.key}
            className={`flex-1 min-w-0 text-center font-bold ${dense ? "text-[9px]" : "text-[10px]"} ${bucket.current ? "text-[#476cf3]" : "text-[#718096]"}`}
          >
            {bucket.label}
          </span>
        ))}
      </div>
      {!hasData && <p className="absolute inset-x-0 top-14 text-center text-xs text-[#8a97ab]">{empty}</p>}
    </div>
  );
}

/**
 * Thực thu và số đơn của từng cụm sân trong đúng khoảng thời gian đang chọn, cao nhất trước.
 * Cụm sân chưa hoạt động (chờ duyệt, tạm ngưng...) chỉ hiện khi có phát sinh trong khoảng đó.
 */
function VenueBreakdown({
  byVenue,
  activeVenueIds,
  unit,
  year,
  month,
  today,
  period,
}: {
  byVenue: VenueActivity[];
  activeVenueIds: Set<number>;
  unit: StatsUnit;
  year: number;
  month: number;
  today: string;
  period: string;
}) {
  const rows = byVenue
    .map((venue) => {
      const buckets = buildBuckets(venue.daily, unit, year, month, today);
      return {
        id: venue.venue_id,
        name: venue.venue_name,
        revenue: buckets.reduce((sum, bucket) => sum + bucket.revenue, 0),
        bookings: buckets.reduce((sum, bucket) => sum + bucket.bookings, 0),
      };
    })
    .filter((row) => row.revenue !== 0 || row.bookings !== 0 || activeVenueIds.has(row.id))
    .sort((a, b) => b.revenue - a.revenue || b.bookings - a.bookings || a.name.localeCompare(b.name, "vi"));
  const max = Math.max(1, ...rows.map((row) => Math.abs(row.revenue)));
  const hasData = rows.some((row) => row.revenue !== 0 || row.bookings !== 0);

  return (
    <div className="mt-6 pt-5 border-t border-[#e8edf3]">
      <p className="text-xs font-black text-[#17253d]">
        Theo cụm sân <span className="font-bold text-[#718096]">· {period}</span>
      </p>
      {hasData ? (
        <ul className="mt-4 space-y-3.5">
          {rows.map((row) => (
            <li
              key={row.id}
              className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_11rem] items-center gap-x-4 gap-y-1.5"
            >
              <span className="truncate text-xs font-bold text-[#263b53]" title={row.name}>
                {row.name}
              </span>
              <span className="sm:order-last text-right text-xs whitespace-nowrap">
                <span className="font-black text-[#17253d]">{formatVND(row.revenue)}</span>
                <span className="font-bold text-[#8a97ab]"> · {row.bookings} đơn</span>
              </span>
              <div className="col-span-2 sm:col-span-1 h-2.5 rounded-full bg-[#eef2f8] overflow-hidden">
                <div
                  className={`h-full rounded-full ${row.revenue < 0 ? "bg-rose-300" : "bg-[#476cf3]"}`}
                  style={{ width: `${(Math.abs(row.revenue) / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-[#8a97ab]">Chưa có cụm sân nào phát sinh khoản thu hay đơn đặt sân trong thời gian này.</p>
      )}
    </div>
  );
}

/** Thực thu và số đơn đặt sân theo từng ngày của một tháng, từng tháng của một năm, hoặc từng năm; bên dưới là phần tách theo cụm sân. */
function Statistics({
  daily,
  byVenue,
  activeVenueIds,
}: {
  daily: DailyActivity[];
  byVenue: VenueActivity[];
  activeVenueIds: Set<number>;
}) {
  const today = formatLocalDate();
  const [unit, setUnit] = useState<StatsUnit>("day");
  const [year, setYear] = useState(Number(today.slice(0, 4)));
  const [month, setMonth] = useState(Number(today.slice(5, 7)));

  const years = useMemo(() => availableYears(daily, today), [daily, today]);
  const buckets = useMemo(() => buildBuckets(daily, unit, year, month, today), [daily, unit, year, month, today]);
  const revenue = buckets.reduce((sum, bucket) => sum + bucket.revenue, 0);
  const bookings = buckets.reduce((sum, bucket) => sum + bucket.bookings, 0);

  const period =
    unit === "day" ? `Tháng ${month}/${year}` : unit === "month" ? `Năm ${year}` : years.length > 1 ? `Từ ${years[years.length - 1]} đến ${years[0]}` : `Năm ${years[0]}`;

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-black text-[#17253d]">Thống kê doanh thu và đơn đặt sân</h3>
          <p className="text-xs text-[#718096] mt-1">{period}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Chips value={unit} onChange={setUnit} options={UNIT_OPTIONS} />
          {unit === "day" && (
            <select className={SELECT} value={month} onChange={(e) => setMonth(Number(e.target.value))} aria-label="Tháng thống kê">
              {Array.from({ length: 12 }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  Tháng {index + 1}
                </option>
              ))}
            </select>
          )}
          {unit !== "year" && (
            <select className={SELECT} value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Năm thống kê">
              {years.map((value) => (
                <option key={value} value={value}>
                  Năm {value}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-8 gap-y-6 mt-5">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-bold text-[#718096]">
            <span className="w-2 h-2 rounded-full bg-[#476cf3]" />
            Thực thu
          </p>
          <p className="text-xl font-black text-[#17253d] mt-1">{formatVND(revenue)}</p>
          <BarChart
            buckets={buckets}
            value={(bucket) => bucket.revenue}
            format={formatVND}
            short={(amount) => `${Math.round(amount / 1000).toLocaleString("vi-VN")}k`}
            tone={{ current: "bg-[#476cf3]", other: "bg-[#c7d3f6]" }}
            empty="Chưa có khoản thu nào trong thời gian này."
          />
        </div>
        <div>
          <p className="flex items-center gap-2 text-[11px] font-bold text-[#718096]">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            Đơn đặt sân
          </p>
          <p className="text-xl font-black text-[#17253d] mt-1">{bookings} đơn</p>
          <BarChart
            buckets={buckets}
            value={(bucket) => bucket.bookings}
            format={(amount) => `${amount} đơn`}
            short={(amount) => String(amount)}
            tone={{ current: "bg-emerald-500", other: "bg-emerald-200" }}
            empty="Chưa có đơn đặt sân nào trong thời gian này."
          />
        </div>
      </div>

      <VenueBreakdown
        byVenue={byVenue}
        activeVenueIds={activeVenueIds}
        unit={unit}
        year={year}
        month={month}
        today={today}
        period={period}
      />
    </Card>
  );
}

export default function OverviewTab({ data }: TabProps) {
  const { users, venues, bookings, matches, stats } = data;
  const roles = countBy(users, (u) => u.role);
  const venueStatus = countBy(venues, (v) => v.status);
  const matchStatus = countBy(matches, (m) => m.status);
  const pendingVenues = venues.filter((v) => v.status === "PENDING");
  const activeVenueIds = new Set(venues.filter((v) => v.status === "ACTIVE").map((v) => v.id));

  const kpis = [
    { dot: "bg-[#476cf3]", label: "Thực thu toàn hệ thống", value: formatVND(stats?.total_revenue), hint: `Đã thu ${formatVND(stats?.collected_amount)} • đã hoàn ${formatVND(stats?.refunded_amount)}` },
    { dot: "bg-emerald-500", label: "Đơn đặt sân", value: String(bookings.length), hint: `${stats?.completed_bookings ?? 0} hoàn tất • ${stats?.pending_refunds ?? 0} chờ hoàn tiền` },
    { dot: "bg-sky-500", label: "Cụm sân", value: String(venues.length), hint: `${venueStatus.ACTIVE || 0} đang hoạt động • ${stats?.total_courts ?? 0} sân` },
    { dot: "bg-violet-500", label: "Tài khoản", value: String(users.length), hint: `${roles.PLAYER || 0} người chơi • ${roles.OWNER || 0} chủ sân • ${roles.STAFF || 0} nhân viên` },
    { dot: "bg-amber-500", label: "Phòng đấu", value: String(matches.length), hint: `${matchStatus.OPEN || 0} đang tuyển người` },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className="p-5">
            <p className="flex items-center gap-2 text-[11px] font-bold text-[#718096]">
              <span className={`w-2 h-2 rounded-full ${kpi.dot}`} />
              {kpi.label}
            </p>
            <p className="text-2xl sm:text-[28px] font-black text-[#17253d] mt-2 leading-none">{kpi.value}</p>
            <p className="text-[11px] text-[#8a97ab] mt-2">{kpi.hint}</p>
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

      <Statistics daily={stats?.daily || []} byVenue={stats?.by_venue || []} activeVenueIds={activeVenueIds} />
    </div>
  );
}
