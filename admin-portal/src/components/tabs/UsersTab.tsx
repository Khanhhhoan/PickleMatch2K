"use client";

import React, { useMemo, useState } from "react";
import { apiDelete, apiPost, apiPut } from "@/lib/api";
import { PURPOSE_LABEL, ROLE_LABEL, userDisplayName, userPhone } from "@/lib/labels";
import { TabProps, User } from "@/lib/types";
import { BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, Badge, Chips, DataTable, Field, INPUT, Modal, TD, Toolbar } from "@/components/ui";

type Role = User["role"];
type RoleFilter = "ALL" | Role;

interface UserForm {
  id: number | null;
  role: Role;
  email: string;
  password: string;
  full_name: string;
  phone: string;
  skill_level: string;
  company_name: string;
  bank_account: string;
  venue_name: string;
  venue_address: string;
  venue_id: string;
}

const EMPTY: UserForm = {
  id: null, role: "PLAYER", email: "", password: "", full_name: "", phone: "", skill_level: "",
  company_name: "", bank_account: "", venue_name: "", venue_address: "", venue_id: "",
};

const ROLE_TONE: Record<Role, string> = {
  ADMIN: "bg-[#101c31] text-white border-[#17253d]",
  OWNER: "bg-amber-50 text-amber-800 border-amber-200",
  STAFF: "bg-emerald-50 text-emerald-800 border-emerald-200",
  PLAYER: "bg-sky-50 text-sky-800 border-sky-200",
};

export default function UsersTab({ data, run, currentUserId }: TabProps & { currentUserId: number }) {
  const [role, setRole] = useState<RoleFilter>("ALL");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<UserForm | null>(null);
  const [viewId, setViewId] = useState<number | null>(null);

  const viewing = viewId ? data.users.find((u) => u.id === viewId) || null : null;
  // Các dòng của bảng chi tiết: thông tin chung, rồi thông tin riêng của từng vai trò
  const details = useMemo<[string, string][]>(() => {
    if (!viewing) return [];
    const rows: [string, string][] = [
      ["Email đăng nhập", viewing.email],
      ["Số điện thoại", userPhone(viewing) || "Chưa khai"],
    ];
    if (viewing.role === "PLAYER") {
      const profile = viewing.player_profile;
      rows.push(
        ["Trình độ", profile?.skill_level != null ? String(profile.skill_level) : "Chưa khai"],
        ["Lối đánh", profile?.play_style || "Chưa khai"],
        ["Mục đích chơi", PURPOSE_LABEL[profile?.purpose || ""] || "Chưa khai"],
        ["Đơn đã đặt trên web", String(data.bookings.filter((b) => b.user_email === viewing.email).length)],
        ["Phòng đấu đã mở", String(data.matches.filter((m) => m.creator_id === viewing.id).length)],
      );
    }
    if (viewing.role === "OWNER") {
      const venues = data.venues.filter((v) => v.owner_id === viewing.id).map((v) => v.name);
      rows.push(
        ["Đơn vị", viewing.owner_profile?.company_name || "Chưa khai"],
        ["Tài khoản nhận tiền", viewing.owner_profile?.bank_account || "Chưa cấu hình"],
        ["Cụm sân quản lý", venues.length > 0 ? venues.join(", ") : "Chưa có cụm sân"],
      );
    }
    if (viewing.role === "STAFF") {
      rows.push(
        ["Cụm sân trực", viewing.staff_profile?.venue_name || "Chưa gán cụm sân"],
        ["Chủ sân", viewing.staff_profile?.owner_name || "—"],
      );
    }
    return rows;
  }, [viewing, data.bookings, data.matches, data.venues]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return data.users.filter(
      (u) =>
        (role === "ALL" || u.role === role) &&
        (!term || [u.email, userDisplayName(u), userPhone(u), u.staff_profile?.venue_name, u.owner_profile?.company_name]
          .some((value) => (value || "").toLowerCase().includes(term))),
    );
  }, [data.users, role, search]);

  const openEdit = (user: User) =>
    setForm({
      ...EMPTY,
      id: user.id,
      role: user.role,
      email: user.email,
      full_name: userDisplayName(user) === user.email.split("@")[0] ? "" : userDisplayName(user),
      phone: userPhone(user),
      skill_level: user.player_profile?.skill_level != null ? String(user.player_profile.skill_level) : "",
      company_name: user.owner_profile?.company_name || "",
      bank_account: user.owner_profile?.bank_account || "",
      venue_id: user.staff_profile?.venue_id ? String(user.staff_profile.venue_id) : "",
    });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    const common = {
      email: form.email,
      full_name: form.full_name,
      phone: form.phone,
      ...(form.password ? { password: form.password } : {}),
      ...(form.role === "PLAYER" && form.skill_level ? { skill_level: Number(form.skill_level) } : {}),
      ...(form.role === "OWNER" ? { company_name: form.company_name, bank_account: form.bank_account } : {}),
      ...(form.role === "STAFF" ? { venue_id: form.venue_id ? Number(form.venue_id) : null } : {}),
    };
    const ok = form.id
      ? await run(() => apiPut(`/users/admin/users/${form.id}`, common), "Đã cập nhật tài khoản.")
      : await run(() => apiPost("/users/admin/users", {
          ...common,
          role: form.role,
          ...(form.role === "OWNER" ? { venue_name: form.venue_name, venue_address: form.venue_address } : {}),
        }), "Đã tạo tài khoản.");
    if (ok) setForm(null);
  };

  const toggleActive = (user: User) =>
    run(() => apiPut(`/users/admin/users/${user.id}/active`, { is_active: !user.is_active }), user.is_active ? "Đã khóa tài khoản." : "Đã mở khóa tài khoản.");

  const remove = (user: User) => {
    if (!window.confirm(`Xóa tài khoản ${user.email}? Tài khoản đã phát sinh dữ liệu sẽ được KHÓA thay vì xóa để giữ lịch sử.`)) return;
    run(async () => {
      const result = await apiDelete(`/users/admin/users/${user.id}`);
      return result;
    }, "Đã xử lý yêu cầu xóa tài khoản.");
  };

  return (
    <div className="space-y-4">
      <Toolbar>
        <Chips
          value={role}
          onChange={setRole}
          options={[{ value: "ALL" as RoleFilter, label: `Tất cả (${data.users.length})` },
            ...(["PLAYER", "OWNER", "STAFF", "ADMIN"] as Role[]).map((r) => ({ value: r as RoleFilter, label: `${ROLE_LABEL[r]} (${data.users.filter((u) => u.role === r).length})` }))]}
        />
        <div className="flex gap-2">
          <input className={`${INPUT} w-64`} placeholder="Tìm theo tên, email, số điện thoại" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button type="button" className={BTN_PRIMARY} onClick={() => setForm({ ...EMPTY, role: role === "ALL" ? "PLAYER" : role })}>+ Thêm tài khoản</button>
        </div>
      </Toolbar>

      <DataTable headers={["Tài khoản", "Vai trò", "Thông tin", "Trạng thái", ""]} empty={filtered.length === 0}>
        {filtered.map((user) => (
          <tr key={user.id}>
            <td className={TD}>
              <p className="font-bold text-[#17253d]">{userDisplayName(user)}</p>
              <p className="text-xs text-[#718096]">{user.email}{userPhone(user) ? ` • ${userPhone(user)}` : ""}</p>
            </td>
            <td className={TD}><Badge tone={ROLE_TONE[user.role]}>{ROLE_LABEL[user.role]}</Badge></td>
            <td className={`${TD} text-xs text-[#51627c]`}>
              {user.role === "PLAYER" && (user.player_profile?.skill_level != null ? `Trình độ ${user.player_profile.skill_level} • ${user.player_profile.play_style || "chưa khai lối đánh"}` : "Chưa khai trình độ")}
              {user.role === "OWNER" && (user.owner_profile?.company_name || "Chưa khai đơn vị")}
              {user.role === "STAFF" && (user.staff_profile?.venue_name ? `Trực tại ${user.staff_profile.venue_name}` : <span className="text-amber-700">Chưa gán cụm sân</span>)}
            </td>
            <td className={TD}>
              <Badge tone={user.is_active ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-rose-50 text-rose-700 border-rose-200"}>
                {user.is_active ? "Hoạt động" : "Đã khóa"}
              </Badge>
            </td>
            <td className={`${TD} text-right whitespace-nowrap space-x-1.5`}>
              <button type="button" className={BTN_SECONDARY} onClick={() => setViewId(user.id)}>Chi tiết</button>
              <button type="button" className={BTN_SECONDARY} onClick={() => openEdit(user)}>Sửa</button>
              {user.id !== currentUserId && (
                <>
                  <button type="button" className={BTN_SECONDARY} onClick={() => toggleActive(user)}>{user.is_active ? "Khóa" : "Mở khóa"}</button>
                  <button type="button" className={BTN_DANGER} onClick={() => remove(user)}>Xóa</button>
                </>
              )}
            </td>
          </tr>
        ))}
      </DataTable>

      {viewing && (
        <Modal title="Chi tiết tài khoản" onClose={() => setViewId(null)}>
          <div className="flex items-center justify-between gap-3 pb-3 border-b border-[#eef1f6]">
            <p className="text-base font-black text-[#17253d]">{userDisplayName(viewing)}</p>
            <div className="flex gap-1.5 shrink-0">
              <Badge tone={ROLE_TONE[viewing.role]}>{ROLE_LABEL[viewing.role]}</Badge>
              <Badge tone={viewing.is_active ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-rose-50 text-rose-700 border-rose-200"}>
                {viewing.is_active ? "Hoạt động" : "Đã khóa"}
              </Badge>
            </div>
          </div>
          <dl className="divide-y divide-[#f3f5f9] text-xs">
            {details.map(([label, value]) => (
              <div key={label} className="flex items-start justify-between gap-4 py-2.5">
                <dt className="text-[#718096] font-bold shrink-0">{label}</dt>
                <dd className="text-[#17253d] font-semibold text-right break-words min-w-0">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="flex justify-end gap-2 pt-3">
            <button type="button" className={BTN_SECONDARY} onClick={() => setViewId(null)}>Đóng</button>
            <button
              type="button"
              className={BTN_PRIMARY}
              onClick={() => {
                openEdit(viewing);
                setViewId(null);
              }}
            >
              Sửa thông tin
            </button>
          </div>
        </Modal>
      )}

      {form && (
        <Modal title={form.id ? `Sửa tài khoản ${ROLE_LABEL[form.role]}` : "Thêm tài khoản"} onClose={() => setForm(null)}>
          <form onSubmit={submit} className="space-y-3">
            {!form.id && (
              <Field label="Vai trò">
                <select className={INPUT} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                  {(["PLAYER", "OWNER", "STAFF", "ADMIN"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </select>
              </Field>
            )}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Email đăng nhập">
                <input className={INPUT} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </Field>
              <Field label={form.id ? "Mật khẩu mới (để trống nếu giữ nguyên)" : "Mật khẩu (tối thiểu 6 ký tự)"}>
                <input className={INPUT} type="password" autoComplete="new-password" minLength={6} required={!form.id} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </Field>
              <Field label="Họ và tên">
                <input className={INPUT} maxLength={120} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </Field>
              <Field label="Số điện thoại">
                <input className={INPUT} type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </Field>
            </div>

            {form.role === "PLAYER" && (
              <Field label="Trình độ (1.0 - 8.0, để trống nếu chưa biết)">
                <input className={INPUT} type="number" min={1} max={8} step={0.5} value={form.skill_level} onChange={(e) => setForm({ ...form, skill_level: e.target.value })} />
              </Field>
            )}

            {form.role === "OWNER" && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Đơn vị / tên chủ tài khoản">
                    <input className={INPUT} value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
                  </Field>
                  <Field label="Tài khoản nhận tiền" hint="Ví dụ: 0123456789 - MBBank">
                    <input className={INPUT} value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} />
                  </Field>
                </div>
                {!form.id && (
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Tên cụm sân khởi tạo">
                      <input className={INPUT} value={form.venue_name} onChange={(e) => setForm({ ...form, venue_name: e.target.value })} />
                    </Field>
                    <Field label="Địa chỉ cụm sân" hint="Bỏ trống: cụm sân ở trạng thái ẩn cho tới khi chủ sân bổ sung">
                      <input className={INPUT} value={form.venue_address} onChange={(e) => setForm({ ...form, venue_address: e.target.value })} />
                    </Field>
                  </div>
                )}
              </>
            )}

            {form.role === "STAFF" && (
              <Field label="Cụm sân phân công">
                <select className={INPUT} required value={form.venue_id} onChange={(e) => setForm({ ...form, venue_id: e.target.value })}>
                  <option value="">Chọn cụm sân</option>
                  {data.venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
                </select>
              </Field>
            )}

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
