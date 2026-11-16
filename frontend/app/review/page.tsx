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

// Mirrors the backend's DOCUMENT_CONFIG["max_upload_bytes"], so a large file fails before upload.
const MAX_PDF_MB = 25;
const MAX_PDF_BYTES = MAX_PDF_MB * 1_000_000;

/** Upload a report PDF: its text is extracted, then it waits in the queue like a pasted report. */
function UploadPdf({ teams }: { teams: Team[] }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [team, setTeam] = useState("");
  const [access, setAccess] = useState<"open" | "restricted">("restricted");
  const [sourceUrl, setSourceUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const teamId = team || teams[0]?.id || "";

  function pick(event: React.ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0] ?? null;
    const problem = !chosen ? null
      : chosen.type !== "application/pdf" && !chosen.name.toLowerCase().endsWith(".pdf") ? `${chosen.name} is not a PDF. Choose a .pdf file.`
      : chosen.size > MAX_PDF_BYTES ? `${chosen.name} is larger than ${MAX_PDF_MB} MB.`
      : null;
    setError(problem);
    setFile(problem ? null : chosen);
    if (problem) event.target.value = "";
  }

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);
    body.append("owner_team_id", teamId);
    body.append("access_level", access);
    if (sourceUrl.trim()) body.append("source_url", sourceUrl.trim());
    try {
      const study = await api<StudyDetail>("/api/ingest/pdf", { method: "POST", body });
      router.push(`/review/${study.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The PDF could not be read.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={upload} className="panel" style={{ maxWidth: 860 }} aria-labelledby="upload-title" aria-busy={busy || undefined}>
      <h2 id="upload-title">Upload the report PDF</h2>
      <div className="field">
        <label htmlFor="pdf">Report PDF</label>
        <input id="pdf" type="file" accept="application/pdf,.pdf" onChange={pick} required aria-describedby="pdf-hint" />
        <p className="hint" id="pdf-hint">
          A PDF with selectable text, up to {MAX_PDF_MB} MB. Scanned pages cannot be read yet. The file is kept with the
          study so readers can open it at the cited page.
        </p>
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor="pdf-team">Commissioned by</label>
          <select id="pdf-team" value={teamId} onChange={(e) => setTeam(e.target.value)}>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="pdf-access">Access</label>
          <select id="pdf-access" value={access} onChange={(e) => setAccess(e.target.value as "open" | "restricted")}>
            <option value="restricted">Restricted to the commissioning team</option>
            <option value="open">Open to all teams</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="pdf-source">Where the report was published (optional)</label>
        <input id="pdf-source" type="url" inputMode="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://" />
        <p className="hint">For public research only, so readers can check the original.</p>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="btn btn-primary" disabled={busy || !file || !teamId}>
        {busy ? "Reading the PDF…" : "Upload and extract"}
      </button>
    </form>
  );
}

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
        <title>Review queue · ALAMKansya</title>
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
                  <td>{s.method_type ? ({ quant: "Survey", qual: "Qualitative", mixed: "Mixed method" } as Record<string, string>)[s.method_type] ?? s.method_type : <span className="error">missing</span>}</td>
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
          Upload the PDF, or paste the report text. The study card and findings are extracted for you to check. Use
          synthetic or approved material only.
        </p>
        <UploadPdf teams={teams} />
        <form onSubmit={ingest} className="panel" style={{ maxWidth: 860 }} aria-labelledby="paste-title">
          <h2 id="paste-title">Or paste the report text</h2>
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
          {error && <p className="error" role="alert">{error}</p>}
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
