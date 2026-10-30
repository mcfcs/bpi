"use client";

import Link from "next/link";
import { useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { LoadError } from "@/components/LoadError";
import { useApi } from "@/lib/useApi";
import { api, ApiError } from "@/lib/api";
import type { EscalationRow, SubmittedCheck } from "@/lib/types";
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
          {isSi && (
            <>
              {" "}
              <a href="#inbox-title">Coverage checks sent to S&amp;I</a> are listed below the questions.
            </>
          )}
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
              {r.note && <p className="item-body" style={{ whiteSpace: "pre-line" }}>{r.note}</p>}
              {r.response && (
                <blockquote className="verbatim" style={{ fontStyle: "normal", fontSize: "1rem", whiteSpace: "pre-line" }}>
                  {r.response}
                  <footer>{r.responded_by} · {r.responded_at ? dateTime(r.responded_at) : ""}</footer>
                </blockquote>
              )}
              {isSi && r.status === "open" && <Respond row={r} onDone={load} />}
            </li>
          ))}
        </ul>
      )}
      {isSi && <CoverageInbox profileId={profile?.id} />}
    </>
  );
}

/** S&I's inbox of coverage checks business teams chose to send before commissioning. */
function CoverageInbox({ profileId }: { profileId?: string }) {
  const { data: checks, error, reload } = useApi<SubmittedCheck[]>("/api/commissioning/submitted", profileId);
  return (
    <section className="section inbox" aria-labelledby="inbox-title" style={{ marginTop: 56 }}>
      <div className="section-head">
        <h2 id="inbox-title">Coverage checks sent to S&amp;I</h2>
        {checks && <span className="tag nums">{checks.length} sent</span>}
      </div>
      <p className="section-intro">
        Sent from Before you commission. Each lists which objectives existing studies already cover and which are new problems.
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {checks === null ? (
        !error && <p className="loading" role="status">Loading…</p>
      ) : checks.length === 0 ? (
        <p className="empty">No coverage checks sent yet. They arrive here when a team sends one before commissioning.</p>
      ) : (
        <ul className="stack">
          {checks.map((c) => (
            <li key={c.id}>
              <div className="item-head">
                <Link className="item-title" href={`/commission?check=${encodeURIComponent(c.id)}`}>{c.title.trim() || "Untitled check"}</Link>
                <span className={c.new_problems > 0 ? "status coverage coverage-gap" : "status coverage coverage-covered"}>
                  {c.new_problems > 0
                    ? `${c.new_problems} new problem${c.new_problems === 1 ? "" : "s"}`
                    : "No new problems"}
                </span>
              </div>
              <div className="item-meta">
                {c.requested_by}, {c.requester_team} · sent <span className="nums">{dateTime(c.submitted_at)}</span> ·{" "}
                <span className="nums">{c.objectives}</span> objective{c.objectives === 1 ? "" : "s"}
                {c.new_problems > 0 && c.new_problems < c.objectives
                  ? `, ${c.objectives - c.new_problems} already with evidence`
                  : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Page() {
  return (
    <SignedIn>
      <Desk />
    </SignedIn>
  );
}
