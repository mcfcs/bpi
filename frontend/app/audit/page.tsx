"use client";

import { useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { LoadError } from "@/components/LoadError";
import { useApi } from "@/lib/useApi";

import type { AuditRow, UsageSummary } from "@/lib/types";
import { dateTime } from "@/lib/format";

function summarise(details: Record<string, unknown>): string {
  return Object.entries(details)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

function Tile({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p className="stat-value nums">{value.toLocaleString()}</p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  );
}

/** The last 30 days at a glance: what teams asked and what happened next. */
function Usage() {
  const { data: u, error, reload } = useApi<UsageSummary>("/api/audit/summary?days=30");
  if (error) return <LoadError message={error} onRetry={reload} />;
  if (!u) return <p className="loading" role="status">Loading the summary…</p>;
  const b = u.briefs;
  const share = (n: number) => (b.total ? `${Math.round((100 * n) / b.total)}% of briefs` : undefined);
  return (
    <section className="section usage" aria-labelledby="usage-title">
      <div className="section-head">
        <h2 id="usage-title">Last {u.days} days</h2>
      </div>
      <div className="stats">
        <Tile label="Briefs" value={b.total}
              note={`${b.confidence.high} high, ${b.confidence.medium} medium, ${b.confidence.low} low confidence`} />
        <Tile label="No readable study answered" value={u.unanswered_total} note={share(u.unanswered_total)} />
        <Tile label="A restricted study also matched" value={b.restricted_also_matched} note={share(b.restricted_also_matched)} />
        <Tile label="Sent to an analyst" value={u.escalations.automatic + u.escalations.from_users}
              note={`${u.escalations.automatic} automatic, ${u.escalations.open} still open`} />
        <Tile label="Access requests" value={u.access_requests.pending + u.access_requests.approved + u.access_requests.denied}
              note={`${u.access_requests.pending} waiting, ${u.access_requests.approved} approved, ${u.access_requests.denied} denied`} />
        <Tile label="Drafts rewritten after checks" value={b.regenerated}
              note={b.written_from_templates ? `${b.written_from_templates} written from templates` : "None written from templates"} />
      </div>
      <div className="usage-lists">
        <div>
          <h3>Asked most</h3>
          {u.most_asked.length === 0 ? <p className="empty">No briefs yet.</p> : (
            <ol className="usage-list">
              {u.most_asked.map((q) => (
                <li key={q.question}><span>{q.question}</span> <span className="muted nums">{q.count}×</span></li>
              ))}
            </ol>
          )}
        </div>
        <div>
          <h3>No readable study answered</h3>
          <p className="hint">Demand to weigh before commissioning new research.</p>
          {u.unanswered.length === 0 ? <p className="empty">Every question found evidence.</p> : (
            <ul className="usage-list">
              {u.unanswered.map((q) => (
                <li key={q.asked_at + q.question}>
                  <span>{q.question}</span> <span className="muted small">{q.team} · {dateTime(q.asked_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3>Briefs by team</h3>
          <ul className="usage-list">
            {b.by_team.map((t) => (
              <li key={t.team}><span>{t.team}</span> <span className="muted nums">{t.count}</span></li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function Audit() {
  const { data: rows, error, reload } = useApi<AuditRow[]>("/api/audit?limit=300");
  const [filter, setFilter] = useState("");
  const shown = (rows ?? []).filter((r) => !filter || r.action.includes(filter) || r.actor.toLowerCase().includes(filter.toLowerCase()));

  return (
    <>
      <section className="page-head">
        <title>Audit log · Evidence brief</title>
        <h1>Audit log</h1>
        <p>Every brief, review edit, tier change, override, access decision, escalation and export. Entries are append-only: nobody can change or delete them.</p>
      </section>
      <Usage />
      <h2 className="log-title">Every entry</h2>
      <div className="field" style={{ maxWidth: 360, marginBottom: 20 }}>
        <label htmlFor="filter">Filter by action or person</label>
        <input id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="tier_override" />
      </div>
      {error && <LoadError message={error} onRetry={reload} />}
      {rows === null ? (
        !error && <p className="loading" role="status">Loading…</p>
      ) : (
        <div className="table-wrap">
          <table className="audit">
            <thead>
              <tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Details</th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="nums muted" style={{ whiteSpace: "nowrap" }}>{dateTime(r.occurred_at)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{r.actor}</td>
                  <td><span className="code">{r.action}</span></td>
                  <td className="muted">{r.entity_type}{r.entity_id ? <span className="code"> {r.entity_id.slice(0, 8)}</span> : ""}</td>
                  <td className="small" style={{ minWidth: 320, overflowWrap: "anywhere" }}>{summarise(r.details)}</td>
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
