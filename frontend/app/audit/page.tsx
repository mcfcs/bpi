"use client";

import { useEffect, useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { api } from "@/lib/api";
import type { AuditRow } from "@/lib/types";
import { dateTime } from "@/lib/format";

function summarise(details: Record<string, unknown>): string {
  return Object.entries(details)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

function Audit() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [filter, setFilter] = useState("");
  useEffect(() => {
    api<AuditRow[]>("/api/audit?limit=300").then(setRows).catch(() => setRows([]));
  }, []);
  const shown = (rows ?? []).filter((r) => !filter || r.action.includes(filter) || r.actor.toLowerCase().includes(filter.toLowerCase()));

  return (
    <>
      <section className="page-head">
        <p className="eyebrow">Governance</p>
        <h1>Audit log</h1>
        <p>Append-only. Every brief, review edit, tier change, override, access decision, escalation and export.</p>
      </section>
      <div className="field" style={{ maxWidth: 360 }}>
        <label htmlFor="filter">Filter by action or person</label>
        <input id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="tier_override" />
      </div>
      {rows === null ? (
        <p className="loading">Loading…</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Details</th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="small nums" style={{ whiteSpace: "nowrap" }}>{dateTime(r.occurred_at)}</td>
                  <td>{r.actor}</td>
                  <td className="mono small">{r.action}</td>
                  <td className="mono small">{r.entity_type}{r.entity_id ? ` ${r.entity_id.slice(0, 8)}` : ""}</td>
                  <td className="small" style={{ maxWidth: 520 }}>{summarise(r.details)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn siOnly>
      <Audit />
    </SignedIn>
  );
}
