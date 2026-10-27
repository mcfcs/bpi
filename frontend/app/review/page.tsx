"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TierBadge } from "@/components/Citation";
import { SignedIn } from "@/components/SiteHeader";
import { api, ApiError } from "@/lib/api";
import type { StudyDetail, Team } from "@/lib/types";
import { dateTime, monthYear, n } from "@/lib/format";

function Queue() {
  const router = useRouter();
  const [queue, setQueue] = useState<StudyDetail[] | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [text, setText] = useState("");
  const [team, setTeam] = useState("");
  const [access, setAccess] = useState<"open" | "restricted">("restricted");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<StudyDetail[]>("/api/review/queue").then(setQueue).catch(() => setQueue([]));
    api<Team[]>("/api/teams").then((t) => {
      setTeams(t);
      setTeam((current) => current || t[0]?.id || "");
    });
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
        <p className="eyebrow">Checkpoint 1 · S&amp;I review</p>
        <h1>Review queue</h1>
        <p>
          New reports wait here until an analyst checks the study card. Nothing is searchable until it is approved. The
          robustness tier is computed from method, sample size and fieldwork date; you can override it with a reason.
        </p>
      </section>

      {queue === null ? (
        <p className="loading">Loading…</p>
      ) : queue.length === 0 ? (
        <p className="notice">Nothing waiting for review.</p>
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
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((s) => (
                <tr key={s.id}>
                  <td>
                    <span className="mono small">{s.code}</span>{" "}
                    <Link href={`/review/${s.id}`}>{s.title}</Link>
                    <div className="muted small">{s.owner_team} · {s.access_level}</div>
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
                  <td className="small muted">{dateTime(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="section" style={{ marginTop: 40 }}>
        <div className="section-head">
          <h2>Add a report</h2>
        </div>
        <p className="section-intro">
          Paste the report text. The study card and findings are extracted for you to check. Use synthetic or approved
          material only.
        </p>
        <form onSubmit={ingest} style={{ maxWidth: 820 }}>
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
