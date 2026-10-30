"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CiteChip, TierBadge } from "@/components/Citation";
import { SignedIn } from "@/components/SiteHeader";
import { LoadError } from "@/components/LoadError";
import { useApi } from "@/lib/useApi";
import { api, ApiError } from "@/lib/api";
import type { StudyDetail, Team } from "@/lib/types";
import { dateTime, monthYear, n } from "@/lib/format";

function Queue() {
  const router = useRouter();
  const { data: queue, error: loadError, reload } = useApi<StudyDetail[]>("/api/review/queue");
  const [teams, setTeams] = useState<Team[]>([]);
  const [text, setText] = useState("");
  const [team, setTeam] = useState("");
  const [access, setAccess] = useState<"open" | "restricted">("restricted");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Team[]>("/api/teams")
      .then((t) => {
        setTeams(t);
        setTeam((current) => current || t[0]?.id || "");
      })
      .catch(() => setTeams([]));
  }, []);

  async function ingest(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const study = await api<StudyDetail>("/api/ingest", {
        method: "POST",
        json: { report_text: text, owner_team_id: team, access_level: access, source_name: "pasted report" },
      });
      router.push(`/review/${study.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The report could not be read.");
      setBusy(false);
    }
  }

  return (
    <>
      <section className="page-head">
        <title>Review queue · Evidence brief</title>
        <h1>Review queue</h1>
        <p>
          New reports wait here until an analyst checks the study card. Nothing is searchable until it is approved. The
          robustness tier is computed from method, sample size and fieldwork date; you can override it with a reason.
        </p>
        <p className="checkpoint">Human checkpoint 1 of 4: an analyst approves every study.</p>
      </section>

      {loadError && <LoadError message={loadError} onRetry={reload} />}
      {queue === null ? (
        !loadError && <p className="loading" role="status">Loading…</p>
      ) : queue.length === 0 ? (
        <p className="empty">Nothing waiting for review. New reports appear here when you add one below.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Study</th>
                <th>Method</th>
                <th className="num">Sample</th>
                <th>Fieldwork ended</th>
                <th>Computed tier</th>
                <th className="num">Findings</th>
                <th className="num">Added</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link className="cell-title" href={`/review/${s.id}`}>{s.title}</Link>
                    <span className="sub"><CiteChip code={s.code} /> {s.owner_team} · {s.access_level}</span>
                  </td>
                  <td>{s.method_type ?? <span className="error">missing</span>}</td>
                  <td className="num">{n(s.sample_size)}</td>
                  <td>{s.fieldwork_end ? monthYear(s.fieldwork_end) : <span className="error">missing</span>}</td>
                  <td>
                    {s.effective_tier ? (
                      <TierBadge tier={s.effective_tier} sample={`n=${n(s.sample_size)}`} when={s.fieldwork_end?.slice(0, 4) ?? "n.d."} />
                    ) : (
                      <span className="muted">not yet</span>
                    )}
                  </td>
                  <td className="num">{s.finding_count}</td>
                  <td className="num muted" style={{ whiteSpace: "nowrap" }}>{dateTime(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="section" style={{ marginTop: 56 }}>
        <div className="section-head">
          <h2>Add a report</h2>
        </div>
        <p className="section-intro">
          Paste the report text. The study card and findings are extracted for you to check. Use synthetic or approved
          material only.
        </p>
        <form onSubmit={ingest} className="panel" style={{ maxWidth: 860 }}>
          <div className="field">
            <label htmlFor="report">Report text</label>
            <textarea id="report" rows={10} value={text} onChange={(e) => setText(e.target.value)} required minLength={40} />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="team">Commissioned by</label>
              <select id="team" value={team} onChange={(e) => setTeam(e.target.value)}>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="access">Access</label>
              <select id="access" value={access} onChange={(e) => setAccess(e.target.value as "open" | "restricted")}>
                <option value="restricted">Restricted to the commissioning team</option>
                <option value="open">Open to all teams</option>
              </select>
            </div>
          </div>
          {error && <p className="error">{error}</p>}
          <button className="btn btn-primary" disabled={busy || text.trim().length < 40}>
            {busy ? "Reading the report…" : "Extract study card"}
          </button>
        </form>
      </section>
    </>
  );
}

export default function Page() {
  return (
    <SignedIn siOnly>
      <Queue />
    </SignedIn>
  );
}
