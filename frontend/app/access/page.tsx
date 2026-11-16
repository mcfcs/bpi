"use client";

import { useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { LoadError } from "@/components/LoadError";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { AccessRequest } from "@/lib/types";
import { dateTime, stateLabel } from "@/lib/format";
import { CiteChip } from "@/components/Citation";

const STATUS_CLASS: Record<string, string> = {
  pending: "status status-wait",
  approved: "status status-ok",
  denied: "status status-bad",
};

function Decide({ request, onDone }: { request: AccessRequest; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [expires, setExpires] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(approve: boolean) {
    setError(null);
    setBusy(true);
    try {
      await api(`/api/access-requests/${request.id}/decision`, {
        method: "POST",
        json: { approve, note: note || null, expires_at: expires || null },
      });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record the decision.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="decide">
      <div className="field-row">
        <div className="field">
          <label htmlFor={`note-${request.id}`}>Note to the requester</label>
          <input id={`note-${request.id}`} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`exp-${request.id}`}>Access ends (optional)</label>
          <input id={`exp-${request.id}`} type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => decide(true)}>Approve for {request.requester_team}</button>
        <button className="btn" disabled={busy} onClick={() => decide(false)}>Decline</button>
      </div>
    </div>
  );
}

function Access() {
  const { profile } = useSession();
  const { data: requests, error, reload: load } = useApi<AccessRequest[]>("/api/access-requests", profile?.id);

  if (!requests) return error ? <LoadError message={error} onRetry={load} /> : <p className="loading" role="status">Loading…</p>;
  const toDecide = requests.filter((r) => r.can_decide);
  const mine = requests.filter((r) => r.mine);
  const decidedByOthers = requests.filter((r) => !r.mine && !r.can_decide);

  return (
    <>
      <section className="page-head">
        <title>Access requests · ALAMKansya</title>
        <h1>Access requests</h1>
        <p>
          Studies paid for by a business unit are shared with other teams only when the owning team or S&amp;I approves.
          Every request and decision is recorded in the audit log.
        </p>
        <p className="checkpoint">Human checkpoint 2 of 4: a person decides every request.</p>
      </section>

      {toDecide.length > 0 && (
        <section className="section">
          <div className="section-head"><h2>Waiting for your decision</h2></div>
          <ul className="stack">
            {toDecide.map((r) => (
              <li key={r.id}>
                <div className="item-head">
                  <span className="item-title">
                    <CiteChip code={r.study_code} /> {r.study_title}
                  </span>
                  <span className="muted small nums">{dateTime(r.created_at)}</span>
                </div>
                <div className="item-meta">Requested by {r.requester}, {r.requester_team}</div>
                <p className="item-body">{r.purpose}</p>
                <Decide request={r} onDone={load} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="section">
        <div className="section-head"><h2>Your requests</h2></div>
        {mine.length === 0 ? (
          <p className="empty">You have not requested access to any study. Requests start from “Restricted matches” in a brief.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Study</th><th>Purpose</th><th>Status</th><th>Decision note</th><th className="num">Requested</th></tr>
              </thead>
              <tbody>
                {mine.map((r) => (
                  <tr key={r.id}>
                    <td><span className="cell-title">{r.study_title}</span><span className="sub"><CiteChip code={r.study_code} /> {r.owner_team}</span></td>
                    <td>{r.purpose}</td>
                    <td><span className={STATUS_CLASS[r.status] ?? "status"}>{stateLabel(r.status)}</span></td>
                    <td>{r.decision_note ?? <span className="muted">–</span>}</td>
                    <td className="num muted" style={{ whiteSpace: "nowrap" }}>{dateTime(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {decidedByOthers.length > 0 && (
        <section className="section">
          <div className="section-head"><h2>Other requests you can see</h2></div>
          <ul className="list-plain" style={{ maxWidth: 920 }}>
            {decidedByOthers.map((r) => (
              <li key={r.id} className="actions" style={{ justifyContent: "space-between" }}>
                <span><CiteChip code={r.study_code} /> <span className="muted">requested by</span> {r.requester_team}</span>
                <span className={STATUS_CLASS[r.status] ?? "status"}>{stateLabel(r.status)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn>
      <Access />
    </SignedIn>
  );
}
