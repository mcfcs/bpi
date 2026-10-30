"use client";

import Link from "next/link";
import { useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { LoadError } from "@/components/LoadError";
import { useApi } from "@/lib/useApi";
import { api, ApiError } from "@/lib/api";
import type { EscalationRow } from "@/lib/types";
import { dateTime, stateLabel } from "@/lib/format";

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
    <form onSubmit={send}>
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
  const { data: rows, error, reload: load } = useApi<EscalationRow[]>("/api/escalations", profile?.id);

  return (
    <>
      <section className="page-head">
        <title>{`${isSi ? "Analyst desk" : "Ask an analyst"} · Evidence brief`}</title>
        <h1>{isSi ? "Analyst desk" : "Ask an analyst"}</h1>
        <p>
          {isSi
            ? "Questions sent by business teams, and briefs routed here because studies of the same population disagree."
            : "Questions you have sent to S&I, and their replies. To ask about a brief, open it and choose Ask an analyst."}
        </p>
        <p className="checkpoint">Human checkpoint 3 of 4: an analyst answers, not the system.</p>
      </section>
      {error && <LoadError message={error} onRetry={load} />}
      {rows === null ? (
        !error && <p className="loading" role="status">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="empty">{isSi ? "No questions waiting. Briefs with unresolved conflicts arrive here on their own." : "You have not asked an analyst anything yet."}</p>
      ) : (
        <ul className="stack">
          {rows.map((r) => (
            <li key={r.id}>
              <div className="item-head">
                <span className="item-title">
                  {r.brief_id ? <Link href={`/briefs/${r.brief_id}`}>{r.question ?? "Open brief"}</Link> : "General question"}
                </span>
                <span className={r.status === "open" ? "status status-wait" : r.status === "answered" ? "status status-ok" : "status"}>{stateLabel(r.status)}</span>
              </div>
              <div className="item-meta">
                {REASONS[r.reason]} · {r.requested_by}, {r.requester_team} · <span className="nums">{dateTime(r.created_at)}</span>
                {r.confidence ? ` · ${r.confidence} confidence` : ""}
              </div>
              {r.note && <p className="item-body">{r.note}</p>}
              {r.response && (
                <blockquote className="verbatim" style={{ fontStyle: "normal", fontSize: "1rem" }}>
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
