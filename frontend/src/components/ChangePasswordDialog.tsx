"use client";

import React, { useState } from "react";
import { fetchApi } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { INPUT, LABEL, Modal, PRIMARY, SECONDARY } from "@/components/ManagementUi";

/** Đổi mật khẩu của tài khoản đang đăng nhập, mở từ thanh trên của cổng quản lý. */
export default function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const { success: toastSuccess, error: toastError } = useToast();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.next.length < 6) {
      toastError("Mật khẩu mới phải có ít nhất 6 ký tự.");
      return;
    }
    if (form.next !== form.confirm) {
      toastError("Xác nhận mật khẩu mới không khớp.");
      return;
    }
    setBusy(true);
    try {
      await fetchApi("/users/me/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: form.current, new_password: form.next }),
      });
      toastSuccess("Đã đổi mật khẩu.");
      onClose();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Đổi mật khẩu không thành công.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Đổi mật khẩu" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className={LABEL} htmlFor="password-current">Mật khẩu hiện tại</label>
          <input id="password-current" type="password" required autoComplete="current-password" className={INPUT}
            value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={LABEL} htmlFor="password-next">Mật khẩu mới (tối thiểu 6 ký tự)</label>
            <input id="password-next" type="password" required minLength={6} maxLength={128} autoComplete="new-password" className={INPUT}
              value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="password-confirm">Nhập lại mật khẩu mới</label>
            <input id="password-confirm" type="password" required minLength={6} maxLength={128} autoComplete="new-password" className={INPUT}
              value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className={SECONDARY} onClick={onClose}>Đóng</button>
          <button type="submit" disabled={busy} className={PRIMARY}>{busy ? "Đang lưu..." : "Đổi mật khẩu"}</button>
        </div>
      </form>
    </Modal>
  );
}
