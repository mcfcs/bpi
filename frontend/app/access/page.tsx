"use client";

import { useCallback, useEffect, useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError } from "@/lib/api";
import type { AccessRequest } from "@/lib/types";
import { dateTime } from "@/lib/format";

function Decide({ request, onDone }: { request: AccessRequest; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [expires, setExpires] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function decide(approve: boolean) {
    setError(null);
    try {
      await api(`/api/access-requests/${request.id}/decision`, {
        method: "POST",
        json: { approve, note: note || null, expires_at: expires || null },
      });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record the decision.");
    }
  }

  return (
    <div style={{ marginTop: 10 }}>
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
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button className="btn btn-primary" onClick={() => decide(true)}>Approve for {request.requester_team}</button>
        <button className="btn" onClick={() => decide(false)}>Decline</button>
      </div>
    </div>
  );
}

function Access() {
  const { profile } = useSession();
  const [requests, setRequests] = useState<AccessRequest[] | null>(null);
  const load = useCallback(() => {
    api<AccessRequest[]>("/api/access-requests").then(setRequests).catch(() => setRequests([]));
  }, []);
  useEffect(load, [load, profile?.id]);

  if (!requests) return <p className="loading">Loading…</p>;
  const toDecide = requests.filter((r) => r.can_decide);
  const mine = requests.filter((r) => r.mine);
  const decidedByOthers = requests.filter((r) => !r.mine && !r.can_decide);

  return (
    <>
      <section className="page-head">
        <p className="eyebrow">Checkpoint 2 · access</p>
        <h1>Access requests</h1>
        <p>
          Studies paid for by a business unit are shared with other teams only when the owning team or S&amp;I approves.
          Every request and decision is recorded in the audit log.
        </p>
      </section>

      {toDecide.length > 0 && (
        <section className="section">
          <div className="section-head"><h2>Waiting for your decision</h2></div>
          <ul className="list-plain" style={{ maxWidth: 900 }}>
            {toDecide.map((r) => (
              <li key={r.id}>
                <div>
                  <span className="mono small">{r.study_code}</span> {r.study_title}
                </div>
                <div className="muted small">
                  {r.requester} · {r.requester_team} · {dateTime(r.created_at)}
                </div>
                <p style={{ marginTop: 6 }}>{r.purpose}</p>
                <Decide request={r} onDone={load} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="section">
        <div className="section-head"><h2>Your requests</h2></div>
        {mine.length === 0 ? (
          <p className="muted">You have not requested access to any study. Requests start from “Restricted matches” in a brief.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Study</th><th>Purpose</th><th>Status</th><th>Decision note</th><th>Requested</th></tr>
              </thead>
              <tbody>
                {mine.map((r) => (
                  <tr key={r.id}>
                    <td><span className="mono small">{r.study_code}</span> {r.study_title}<div className="muted small">{r.owner_team}</div></td>
                    <td>{r.purpose}</td>
                    <td>{r.status}</td>
                    <td>{r.decision_note ?? ""}</td>
                    <td className="small muted">{dateTime(r.created_at)}</td>
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
          <ul className="list-plain" style={{ maxWidth: 900 }}>
            {decidedByOthers.map((r) => (
              <li key={r.id} className="small">
                <span className="mono">{r.study_code}</span> · {r.requester_team} · {r.status}
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
