"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Brief, Escalation } from "@/lib/types";
import { dateTime } from "@/lib/format";

const REASONS: Record<string, string> = {
  user_request: "You asked",
  unresolved_conflict: "Sent automatically: studies of the same people disagree",
  low_confidence: "Sent automatically: low confidence",
};

/**
 * What the reader typed, without the context the Ask-an-analyst page adds around it: the question
 * they chose for the analyst, or a follow-up's own words. The drafted context ("Question: ...
 * What the assistant found: ...") is the brief itself, already on this page.
 */
function askedText(e: Escalation): string | null {
  const note = e.note?.trim();
  if (!note || e.reason !== "user_request") return null;
  const chosen = note.match(/Question for the analyst: ([\s\S]*?)(?:\n\n|$)/);
  if (chosen) return chosen[1].trim();
  return note.startsWith("Question:") ? null : note;
}

function statusOf(e: Escalation) {
  if (e.status === "open") return { label: "Waiting for S&I", className: "status status-wait" };
  if (e.status === "answered") return { label: "Answered", className: "status status-ok" };
  return { label: "Closed", className: "status" };
}

/**
 * Ask an analyst about this brief. The first question is written on its own page, prefilled from the
 * brief (/analyst/new); here the reader sees every question on the brief with its status and the
 * analyst's reply, and can ask a follow-up once a reply is in.
 */
export function AnalystPanel({ brief }: { brief: Brief }) {
  const [thread, setThread] = useState<Escalation[]>(
    () => brief.escalations ?? (brief.escalation ? [brief.escalation] : []),
  );
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const latest = thread.at(-1) ?? null;
  const waiting = thread.some((e) => e.status === "open");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const created = await api<Escalation>("/api/escalations", { method: "POST", json: { brief_id: brief.id, note } });
      if (!created.duplicate) {
        setThread((t) => [...t, { ...created, note: note.trim(), response: null }]);
      }
      setNote("");
      setOpen(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="side-panel analyst-panel" aria-labelledby="analyst-title" id="analyst">
      <div className="analyst-head">
        <h2 id="analyst-title">Ask an analyst</h2>
        {latest && <span className={statusOf(latest).className}>{statusOf(latest).label}</span>}
      </div>
      {thread.length === 0 ? (
        <>
          <p>Not sure the evidence answers your question? An S&amp;I analyst can check the brief and reply here.</p>
          <Link className="btn" href={`/analyst/new?brief=${encodeURIComponent(brief.id)}`}>Ask an analyst</Link>
        </>
      ) : (
        <ol className="thread" aria-label="Questions about this brief">
          {thread.map((e, i) => {
            const asked = askedText(e);
            return (
              <li key={e.id}>
                <p className="thread-meta">
                  {e.reason === "user_request" && thread.slice(0, i).some((x) => x.reason === "user_request")
                    ? "Your follow-up"
                    : REASONS[e.reason] ?? "Sent to S&I"}
                  {e.created_at && <span className="nums"> · {dateTime(e.created_at)}</span>}
                </p>
                {asked && <p className="thread-asked">{asked}</p>}
                {e.response ? (
                  <blockquote className="analyst-reply">
                    <span className="who">
                      {e.responded_by ? `${e.responded_by} replied` : "Analyst’s reply"}
                      {e.responded_at && <span className="nums"> · {dateTime(e.responded_at)}</span>}
                    </span>
                    {e.response}
                  </blockquote>
                ) : (
                  e.status === "open" && <p className="hint thread-wait">An analyst will reply here.</p>
                )}
              </li>
            );
          })}
        </ol>
      )}
      {thread.length > 0 && !waiting && (
        open ? (
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="escalation-note">Your follow-up question</label>
              <textarea id="escalation-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} required autoFocus />
            </div>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="actions">
              <button className="btn btn-primary" disabled={busy || note.trim().length < 3}>{busy ? "Sending…" : "Send to S&I"}</button>
              <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>Cancel</button>
            </div>
          </form>
        ) : (
          <button type="button" className="btn" onClick={() => setOpen(true)}>Ask a follow-up</button>
        )
      )}
      {thread.length > 0 && (
        <p className="hint analyst-foot">
          Every question and reply is kept under <Link href="/analyst">Ask an analyst</Link>.
        </p>
      )}
    </section>
  );
}
