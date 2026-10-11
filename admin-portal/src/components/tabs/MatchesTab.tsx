"use client";

import React, { useMemo, useState } from "react";
import { apiDelete, apiPost, apiPut, formatLocalDate } from "@/lib/api";
import { MATCH_STATUS_LABEL, PURPOSE_LABEL, statusTone, userDisplayName } from "@/lib/labels";
import { Match, TabProps } from "@/lib/types";
import { BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, Badge, Chips, DataTable, Field, INPUT, Modal, TD, Toolbar } from "@/components/ui";

const STATUSES: Match["status"][] = ["OPEN", "FULL", "COMPLETED", "CANCELLED"];

interface MatchForm {
  venue_id: string;
  court_id: string;
  creator_id: string;
  date: string;
  start_time: string;
  end_time: string;
  required_skill: string;
  num_players: string;
  purpose: string;
  notes: string;
}

export default function MatchesTab({ data, run }: TabProps) {
  const [status, setStatus] = useState("ALL");
  const [search, setSearch] = useState("");
  const [viewId, setViewId] = useState<number | null>(null);
  const [form, setForm] = useState<MatchForm | null>(null);

  const players = useMemo(() => data.users.filter((u) => u.role === "PLAYER" && u.is_active), [data.users]);
  const activeVenues = useMemo(() => data.venues.filter((v) => v.status === "ACTIVE"), [data.venues]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return data.matches.filter(
      (m) => (status === "ALL" || m.status === status) && (!term || [m.venue_name, m.creator_name, m.court_name, m.date, `#${m.id}`].some((v) => (v || "").toLowerCase().includes(term))),
    );
  }, [data.matches, status, search]);

  const viewing = viewId ? data.matches.find((m) => m.id === viewId) || null : null;
  const formVenue = form ? data.venues.find((v) => v.id === Number(form.venue_id)) : null;

  const openCreate = () =>
    setForm({
      venue_id: activeVenues[0] ? String(activeVenues[0].id) : "", court_id: "", creator_id: players[0] ? String(players[0].id) : "",
      date: formatLocalDate(), start_time: "18:00", end_time: "20:00", required_skill: "", num_players: "4", purpose: "recreational", notes: "",
    });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    const ok = await run(() => apiPost("/matches/admin/create", {
      venue_id: Number(form.venue_id),
      court_id: form.court_id ? Number(form.court_id) : null,
      creator_id: form.creator_id ? Number(form.creator_id) : null,
      date: form.date,
      start_time: form.start_time,
      end_time: form.end_time,
      required_skill: form.required_skill ? Number(form.required_skill) : null,
      num_players: Number(form.num_players),
      purpose: form.purpose,
      notes: form.notes.trim() || null,
    }), "Đã tạo phòng đấu.");
    if (ok) setForm(null);
  };

  const remove = (match: Match) => {
    if (!window.confirm(`Xóa phòng đấu #${match.id}?`)) return;
    run(() => apiDelete(`/matches/admin/${match.id}`), "Đã xóa phòng đấu.");
  };

  return (
    <div className="space-y-4">
      <Toolbar>
        <Chips
          value={status}
          onChange={setStatus}
          options={[{ value: "ALL", label: `Tất cả (${data.matches.length})` },
            ...STATUSES.map((s) => ({ value: s as string, label: `${MATCH_STATUS_LABEL[s]} (${data.matches.filter((m) => m.status === s).length})` }))]}
        />
        <div className="flex gap-2">
          <input className={`${INPUT} w-64`} placeholder="Tìm theo cụm sân, chủ phòng, ngày" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button type="button" className={BTN_PRIMARY} onClick={openCreate} disabled={activeVenues.length === 0}>+ Tạo phòng đấu</button>
        </div>
      </Toolbar>

      <DataTable headers={["Phòng", "Cụm sân / lịch", "Chủ phòng", "Yêu cầu", "Thành viên", "Trạng thái", ""]} empty={filtered.length === 0}>
        {filtered.map((m) => (
          <tr key={m.id}>
            <td className={`${TD} font-mono font-bold text-[#17253d]`}>#{m.id}</td>
            <td className={`${TD} text-xs`}>
              <p className="font-semibold text-[#17253d]">{m.venue_name}</p>
              <p className="text-[#51627c]">{m.court_name ? `${m.court_name} • ` : ""}{m.date} • {m.start_time.slice(0, 5)}-{m.end_time.slice(0, 5)}</p>
              <p className={m.booking_code ? "text-[#9aa7bb]" : "text-amber-700"}>{m.booking_code ? `Đơn ${m.booking_code}` : "Không gắn đơn đặt sân"}</p>
            </td>
            <td className={TD}>{m.creator_name}</td>
            <td className={`${TD} text-xs text-[#51627c]`}>
              {PURPOSE_LABEL[m.purpose || ""] || "—"}
              <br />
              {m.required_skill != null ? `Trình độ ${m.required_skill}` : "Mọi trình độ"}
            </td>
            <td className={TD}>
              <button type="button" className={BTN_SECONDARY} onClick={() => setViewId(m.id)}>{m.participants.length}/{m.num_players} người</button>
            </td>
            <td className={TD}>
              <select
                className={`px-2 py-1 rounded-md border text-xs font-semibold cursor-pointer ${statusTone(m.status)}`}
                value={m.status}
                aria-label={`Trạng thái phòng #${m.id}`}
                onChange={(e) => run(() => apiPut(`/matches/admin/${m.id}/status`, { status: e.target.value }), "Đã đổi trạng thái phòng đấu.")}
              >
                {STATUSES.map((s) => <option key={s} value={s}>{MATCH_STATUS_LABEL[s]}</option>)}
              </select>
            </td>
            <td className={`${TD} text-right`}>
              <button type="button" className={BTN_DANGER} onClick={() => remove(m)}>Xóa</button>
            </td>
          </tr>
        ))}
      </DataTable>

      {viewing && (
        <Modal title={`Thành viên phòng #${viewing.id}`} onClose={() => setViewId(null)}>
          <ul className="space-y-2">
            {viewing.participants.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 p-3 rounded-lg bg-[#f8fafd] border border-[#e8edf3] text-sm">
                <div>
                  <p className="font-semibold text-[#17253d]">
                    {p.user_name} {p.user_id === viewing.creator_id && <Badge tone="bg-amber-50 text-amber-800 border-amber-200">Chủ phòng</Badge>}
                  </p>
                  <p className="text-xs text-[#718096]">{p.skill_level != null ? `Trình độ ${p.skill_level}` : "Chưa khai trình độ"}{p.phone ? ` • ${p.phone}` : ""}</p>
                </div>
                {p.user_id !== viewing.creator_id && (
                  <button
                    type="button"
                    className={BTN_DANGER}
                    onClick={() => window.confirm(`Đưa ${p.user_name} ra khỏi phòng?`) && run(() => apiDelete(`/matches/admin/${viewing.id}/participants/${p.user_id}`), "Đã đưa thành viên ra khỏi phòng.")}
                  >
                    Loại
                  </button>
                )}
              </li>
            ))}
            {viewing.participants.length === 0 && <li className="text-sm text-[#718096]">Phòng chưa có thành viên.</li>}
          </ul>
        </Modal>
      )}

      {form && (
        <Modal title="Tạo phòng đấu" onClose={() => setForm(null)}>
          <form onSubmit={submit} className="space-y-3">
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2.5">
              Phòng do quản trị viên tạo không gắn với đơn đặt sân nên không bảo đảm có sân. Người chơi nên tự mở phòng trên đơn đã thanh toán cọc.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Cụm sân">
                <select className={INPUT} required value={form.venue_id} onChange={(e) => setForm({ ...form, venue_id: e.target.value, court_id: "" })}>
                  {activeVenues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </Field>
              <Field label="Sân (tùy chọn)">
                <select className={INPUT} value={form.court_id} onChange={(e) => setForm({ ...form, court_id: e.target.value })}>
                  <option value="">Chưa chọn</option>
                  {formVenue?.courts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Chủ phòng">
              <select className={INPUT} value={form.creator_id} onChange={(e) => setForm({ ...form, creator_id: e.target.value })}>
                {players.map((p) => <option key={p.id} value={p.id}>{userDisplayName(p)} ({p.email})</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Ngày"><input className={INPUT} type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
              <Field label="Bắt đầu"><input className={INPUT} type="time" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /></Field>
              <Field label="Kết thúc"><input className={INPUT} type="time" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} /></Field>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Số người (2-8)"><input className={INPUT} type="number" required min={2} max={8} value={form.num_players} onChange={(e) => setForm({ ...form, num_players: e.target.value })} /></Field>
              <Field label="Trình độ"><input className={INPUT} type="number" min={1} max={8} step={0.5} placeholder="Mọi trình độ" value={form.required_skill} onChange={(e) => setForm({ ...form, required_skill: e.target.value })} /></Field>
              <Field label="Mục đích">
                <select className={INPUT} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
                  {Object.entries(PURPOSE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Ghi chú"><input className={INPUT} maxLength={300} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className={BTN_SECONDARY} onClick={() => setForm(null)}>Đóng</button>
              <button type="submit" className={BTN_PRIMARY}>Tạo phòng</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
