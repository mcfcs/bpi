"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError } from "@/lib/api";
import type { EscalationRow } from "@/lib/types";
import { dateTime } from "@/lib/format";

const REASONS = {
  user_request: "Asked by the user",
  unresolved_conflict: "Unresolved conflict, routed automatically",
  low_confidence: "Low confidence",
} as const;

function Respond({ row, onDone }: { row: EscalationRow; onDone: () => void }) {
  const [response, setResponse] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function send(event: React.FormEvent) {
    event.preventDefault();
    try {
      await api(`/api/escalations/${row.id}/respond`, { method: "POST", json: { response } });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send the reply.");
    }
  }
  return (
    <form onSubmit={send} style={{ marginTop: 10 }}>
      <div className="field">
        <label htmlFor={`reply-${row.id}`}>Reply</label>
        <textarea id={`reply-${row.id}`} rows={3} value={response} onChange={(e) => setResponse(e.target.value)} required />
      </div>
      {error && <p className="error">{error}</p>}
      <button className="btn btn-primary" disabled={response.trim().length < 3}>Send reply</button>
    </form>
  );
}

function Desk() {
  const { profile } = useSession();
  const isSi = profile?.role === "si_analyst";
  const [rows, setRows] = useState<EscalationRow[] | null>(null);
  const load = useCallback(() => {
    api<EscalationRow[]>("/api/escalations").then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(load, [load, profile?.id]);

  return (
    <>
      <section className="page-head">
        <p className="eyebrow">Checkpoint 3 · escalation</p>
        <h1>{isSi ? "Analyst desk" : "Ask an analyst"}</h1>
        <p>
          {isSi
            ? "Questions sent by business teams, and briefs routed here because studies of the same population disagree."
            : "Questions you have sent to S&I, and their replies. To ask about a brief, open it and choose Ask an analyst."}
        </p>
      </section>
      {rows === null ? (
        <p className="loading">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="notice">Nothing here yet.</p>
      ) : (
        <ul className="list-plain" style={{ maxWidth: 900 }}>
          {rows.map((r) => (
            <li key={r.id}>
              <div className="actions" style={{ justifyContent: "space-between" }}>
                <span>
                  {r.brief_id ? <Link href={`/briefs/${r.brief_id}`}>{r.question ?? "Open brief"}</Link> : "General question"}
                </span>
                <span className="chip">{r.status}</span>
              </div>
              <div className="muted small">
                {REASONS[r.reason]} · {r.requested_by}, {r.requester_team} · {dateTime(r.created_at)}
                {r.confidence ? ` · confidence ${r.confidence}` : ""}
              </div>
              {r.note && <p style={{ marginTop: 6 }}>{r.note}</p>}
              {r.response && (
                <blockquote className="verbatim" style={{ fontStyle: "normal", fontFamily: "var(--sans)", fontSize: "1rem" }}>
                  {r.response}
                  <footer>{r.responded_by} · {r.responded_at ? dateTime(r.responded_at) : ""}</footer>
                </blockquote>
              )}
              {isSi && r.status === "open" && <Respond row={r} onDone={load} />}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn>
      <Desk />
    </SignedIn>
  );
}
