"use client";

import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { AnswerAlert } from "@/lib/types";

/** Fired when an alert is read, so the header's count follows. */
export const ALERTS_CHANGED = "si-evidence:alerts-changed";

/**
 * Earlier questions of the reader's that a newly approved or newly granted study now answers. The
 * alert only says asking again will find something; the reader decides whether to ask.
 */
export function AnswerAlerts({ onAsk, busy, profileId }: { onAsk: (question: string) => void; busy: boolean; profileId?: string }) {
  const [alerts, setAlerts] = useState<AnswerAlert[]>([]);

  useEffect(() => {
    api<AnswerAlert[]>("/api/alerts").then(setAlerts).catch(() => setAlerts([]));
  }, [profileId]);

  const unread = alerts.filter((a) => !a.read_at);
  if (!unread.length) return null;

  async function markRead(id: string) {
    setAlerts((all) => all.map((a) => (a.id === id ? { ...a, read_at: new Date().toISOString() } : a)));
    await api(`/api/alerts/${id}/read`, { method: "POST" }).catch(() => undefined);
    window.dispatchEvent(new Event(ALERTS_CHANGED));
  }

  return (
    <section className="alerts" aria-labelledby="alerts-title">
      <h2 id="alerts-title">
        <BellRing size={18} strokeWidth={2} aria-hidden />
        {unread.length === 1 ? "A new study answers your earlier question" : `New studies answer ${unread.length} of your earlier questions`}
      </h2>
      <ul>
        {unread.map((a) => (
          <li key={a.id}>
            <div>
              <p className="alert-q">&ldquo;{a.question}&rdquo;</p>
              <p className="hint">
                {a.study_code ? (
                  <>Now covered by <span className="code">{a.study_code}</span> {a.study_title}</>
                ) : (
                  "Now covered by a study S&I approved"
                )}{" "}
                · {dateTime(a.created_at)}
              </p>
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => {
                  markRead(a.id);
                  onAsk(a.question);
                }}
              >
                See the answer
              </button>
              <button type="button" className="btn btn-quiet" onClick={() => markRead(a.id)}>Dismiss</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
