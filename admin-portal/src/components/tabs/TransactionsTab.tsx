"use client";

import React, { useEffect, useMemo, useState } from "react";
import { apiGet, formatDateTime, formatVND } from "@/lib/api";
import { KIND_LABEL, METHOD_LABEL, userDisplayName } from "@/lib/labels";
import { TabProps, Transaction } from "@/lib/types";
import { Badge, Card, Chips, DataTable, INPUT, TD, Toolbar } from "@/components/ui";

/** Sổ giao dịch: mọi khoản thu và hoàn đã ghi nhận. Số liệu doanh thu của hệ thống đều tính từ bảng này. */
export default function TransactionsTab({ data }: TabProps) {
  const [ownerId, setOwnerId] = useState("");
  const [kind, setKind] = useState("ALL");
  const [ownerTransactions, setOwnerTransactions] = useState<Transaction[] | null>(null);

  const owners = useMemo(() => data.users.filter((u) => u.role === "OWNER"), [data.users]);

  // Lọc theo chủ sân được thực hiện ở máy chủ (theo các cụm sân của chủ sân đó)
  useEffect(() => {
    if (!ownerId) {
      setOwnerTransactions(null);
      return;
    }
    let cancelled = false;
    apiGet(`/payments/transactions?owner_id=${ownerId}`)
      .then((rows) => !cancelled && setOwnerTransactions(Array.isArray(rows) ? rows : []))
      .catch(() => !cancelled && setOwnerTransactions([]));
    return () => {
      cancelled = true;
    };
  }, [ownerId, data.transactions]);

  const source = ownerTransactions ?? data.transactions;
  const rows = source.filter((t) => kind === "ALL" || t.kind === kind);
  const successful = source.filter((t) => t.status === "SUCCESS");
  const collected = successful.filter((t) => t.kind !== "REFUND").reduce((sum, t) => sum + t.amount_in, 0);
  const refunded = successful.filter((t) => t.kind === "REFUND").reduce((sum, t) => sum + t.amount_in, 0);
  const cash = successful.filter((t) => t.kind !== "REFUND" && t.method === "CASH").reduce((sum, t) => sum + t.amount_in, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          ["Đã thu", formatVND(collected)],
          ["Trong đó tiền mặt", formatVND(cash)],
          ["Đã hoàn", formatVND(refunded)],
          ["Thực thu", formatVND(collected - refunded)],
        ].map(([label, value]) => (
          <Card key={label} className="p-4">
            <div className="text-xs text-slate-500 font-bold uppercase tracking-wider">{label}</div>
            <div className="text-lg font-black text-slate-900 mt-1">{value}</div>
          </Card>
        ))}
      </div>

      <Toolbar>
        <Chips
          value={kind}
          onChange={setKind}
          options={[{ value: "ALL", label: "Tất cả" }, ...Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label }))]}
        />
        <select className={`${INPUT} w-72`} value={ownerId} onChange={(e) => setOwnerId(e.target.value)} aria-label="Lọc theo chủ sân">
          <option value="">Mọi chủ sân</option>
          {owners.map((owner) => <option key={owner.id} value={owner.id}>{userDisplayName(owner)} ({owner.email})</option>)}
        </select>
      </Toolbar>

      <DataTable headers={["Mã giao dịch", "Thời gian", "Đơn", "Loại", "Hình thức", "Nội dung / tham chiếu", "Số tiền"]} empty={rows.length === 0}>
        {rows.map((t) => (
          <tr key={t.id}>
            <td className={`${TD} font-mono font-bold text-slate-900`}>{t.transaction_code || `#${t.id}`}</td>
            <td className={`${TD} text-xs text-slate-600 whitespace-nowrap`}>{formatDateTime(t.created_at)}</td>
            <td className={`${TD} font-mono text-xs`}>{t.booking?.booking_code || `#${t.booking_id}`}</td>
            <td className={TD}>
              <Badge tone={t.kind === "REFUND" ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-emerald-50 text-emerald-800 border-emerald-200"}>
                {KIND_LABEL[t.kind || ""] || t.kind}
              </Badge>
            </td>
            <td className={`${TD} text-xs`}>{METHOD_LABEL[t.method || ""] || t.method} <span className="text-slate-400">• {t.gateway}</span></td>
            <td className={`${TD} text-xs text-slate-600`}>
              <p className="max-w-xs truncate">{t.transaction_content}</p>
              {t.reference_number && <p className="text-slate-400 font-mono">{t.reference_number}</p>}
            </td>
            <td className={`${TD} text-right font-bold whitespace-nowrap ${t.kind === "REFUND" ? "text-rose-600" : "text-emerald-700"}`}>
              {t.kind === "REFUND" ? "-" : "+"}{formatVND(t.amount_in)}
            </td>
          </tr>
        ))}
      </DataTable>
      <p className="text-xs text-slate-500">Hiển thị tối đa 500 giao dịch gần nhất.</p>
    </div>
  );
}
