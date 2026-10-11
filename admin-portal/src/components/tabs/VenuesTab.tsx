"use client";

import React, { useMemo, useState } from "react";
import { apiDelete, apiPost, apiPut, formatVND } from "@/lib/api";
import { VENUE_STATUS_LABEL, statusTone, userDisplayName } from "@/lib/labels";
import { TabProps, Venue } from "@/lib/types";
import { BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, Badge, Chips, DataTable, Field, INPUT, Modal, TD, Toolbar } from "@/components/ui";

type StatusFilter = "ALL" | Venue["status"];

interface VenueForm {
  id: number | null;
  name: string;
  address: string;
  description: string;
  owner_id: string;
  status: Venue["status"];
  courts_count: string;
  base_price: string;
}

const STATUS_OPTIONS: Venue["status"][] = ["ACTIVE", "PENDING", "MAINTENANCE", "INACTIVE", "REJECTED"];

export default function VenuesTab({ data, run }: TabProps) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [form, setForm] = useState<VenueForm | null>(null);

  const owners = useMemo(() => data.users.filter((u) => u.role === "OWNER"), [data.users]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return data.venues.filter(
      (v) =>
        (status === "ALL" || v.status === status) &&
        (!term || [v.name, v.address, v.owner_full_name].some((value) => (value || "").toLowerCase().includes(term))),
    );
  }, [data.venues, search, status]);

  const openCreate = () =>
    setForm({ id: null, name: "", address: "", description: "", owner_id: owners[0] ? String(owners[0].id) : "", status: "ACTIVE", courts_count: "2", base_price: "" });

  const openEdit = (venue: Venue) =>
    setForm({
      id: venue.id, name: venue.name, address: venue.address || "", description: venue.description || "",
      owner_id: String(venue.owner_id), status: venue.status, courts_count: String(venue.courts.length), base_price: "",
    });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    const ok = form.id
      ? await run(() => apiPut(`/venues/admin/${form.id}`, {
          name: form.name, address: form.address, description: form.description || null, status: form.status, owner_id: Number(form.owner_id),
        }), "Đã cập nhật cụm sân.")
      : await run(() => apiPost("/venues/admin", {
          name: form.name, address: form.address, description: form.description || null, owner_id: Number(form.owner_id),
          status: form.status, courts_count: Number(form.courts_count), base_price: Number(form.base_price),
        }), "Đã tạo cụm sân.");
    if (ok) setForm(null);
  };

  const setVenueStatus = (venue: Venue, next: Venue["status"], message: string) =>
    run(() => apiPut(`/venues/admin/${venue.id}`, { status: next }), message);

  const remove = (venue: Venue) => {
    if (!window.confirm(`Xóa cụm sân “${venue.name}”? Chỉ xóa được cụm sân chưa từng có đơn đặt hay phòng đấu.`)) return;
    run(() => apiDelete(`/venues/admin/${venue.id}`), "Đã xóa cụm sân.");
  };

  return (
    <div className="space-y-4">
      <Toolbar>
        <Chips
          value={status}
          onChange={setStatus}
          options={[{ value: "ALL" as StatusFilter, label: `Tất cả (${data.venues.length})` },
            ...STATUS_OPTIONS.map((s) => ({ value: s as StatusFilter, label: `${VENUE_STATUS_LABEL[s]} (${data.venues.filter((v) => v.status === s).length})` }))]}
        />
        <div className="flex gap-2">
          <input className={`${INPUT} w-64`} placeholder="Tìm theo tên, địa chỉ, chủ sân" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button type="button" className={BTN_PRIMARY} onClick={openCreate} disabled={owners.length === 0} title={owners.length === 0 ? "Cần tạo tài khoản Chủ sân trước" : undefined}>
            + Thêm cụm sân
          </button>
        </div>
      </Toolbar>

      <DataTable headers={["Cụm sân", "Chủ sân", "Sân / giá cơ bản", "Tài khoản nhận tiền", "Trạng thái", ""]} empty={filtered.length === 0}>
        {filtered.map((venue) => {
          const base = venue.price_rules.find((r) => r.rule_type === "BASE");
          return (
            <tr key={venue.id}>
              <td className={TD}>
                <p className="font-bold text-[#17253d]">{venue.name}</p>
                <p className="text-xs text-[#718096]">{venue.address}</p>
                {(venue.latitude == null || venue.longitude == null) && <p className="text-xs text-amber-700">Chưa có toạ độ</p>}
              </td>
              <td className={TD}>
                <p className="text-[#17253d]">{venue.owner_full_name || `#${venue.owner_id}`}</p>
              </td>
              <td className={TD}>
                <p>{venue.courts.length} sân</p>
                <p className="text-xs text-[#718096]">{base ? `${formatVND(base.price)}/giờ` : "Chưa có bảng giá"}</p>
              </td>
              <td className={`${TD} text-xs`}>
                {venue.owner_bank_account ? (
                  <>
                    <p className="font-mono text-[#17253d]">{venue.owner_bank_account}</p>
                    <p className="text-[#718096]">{venue.owner_company_name}</p>
                  </>
                ) : (
                  <span className="text-amber-700">Chưa cấu hình</span>
                )}
              </td>
              <td className={TD}><Badge tone={statusTone(venue.status)}>{VENUE_STATUS_LABEL[venue.status] || venue.status}</Badge></td>
              <td className={`${TD} text-right whitespace-nowrap space-x-1.5`}>
                {venue.status === "PENDING" && (
                  <>
                    <button type="button" className={BTN_PRIMARY.replace("px-4 py-2 ", "px-3 py-1.5 ").replace("text-sm", "text-xs")} onClick={() => setVenueStatus(venue, "ACTIVE", "Đã duyệt cụm sân.")}>Duyệt</button>
                    <button type="button" className={BTN_DANGER} onClick={() => setVenueStatus(venue, "REJECTED", "Đã từ chối cụm sân.")}>Từ chối</button>
                  </>
                )}
                <button type="button" className={BTN_SECONDARY} onClick={() => openEdit(venue)}>Sửa</button>
                <button type="button" className={BTN_DANGER} onClick={() => remove(venue)}>Xóa</button>
              </td>
            </tr>
          );
        })}
      </DataTable>

      {form && (
        <Modal title={form.id ? "Sửa cụm sân" : "Thêm cụm sân"} onClose={() => setForm(null)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Tên cụm sân">
              <input className={INPUT} required maxLength={160} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Địa chỉ">
              <input className={INPUT} required maxLength={255} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </Field>
            <Field label="Giới thiệu">
              <textarea className={INPUT} rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Chủ sân">
                <select className={INPUT} required value={form.owner_id} onChange={(e) => setForm({ ...form, owner_id: e.target.value })}>
                  {owners.map((owner) => (
                    <option key={owner.id} value={owner.id}>{userDisplayName(owner)} ({owner.email})</option>
                  ))}
                </select>
              </Field>
              <Field label="Trạng thái">
                <select className={INPUT} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Venue["status"] })}>
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{VENUE_STATUS_LABEL[s]}</option>)}
                </select>
              </Field>
            </div>
            {!form.id && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Số sân tạo sẵn">
                  <input className={INPUT} type="number" required min={1} max={20} value={form.courts_count} onChange={(e) => setForm({ ...form, courts_count: e.target.value })} />
                </Field>
                <Field label="Giá giờ thường (VNĐ)">
                  <input className={INPUT} type="number" required min={1000} step={1000} value={form.base_price} onChange={(e) => setForm({ ...form, base_price: e.target.value })} />
                </Field>
              </div>
            )}
            <p className="text-xs text-[#718096]">Sân con, giờ hoạt động, giá cao điểm, tiện ích và ảnh do chủ sân cấu hình trong cổng Chủ sân.</p>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className={BTN_SECONDARY} onClick={() => setForm(null)}>Đóng</button>
              <button type="submit" className={BTN_PRIMARY}>Lưu</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
