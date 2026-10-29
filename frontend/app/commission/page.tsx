"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { Citation, uniqueByStudy } from "@/components/Citation";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError, download } from "@/lib/api";
import type { CoverageCheck } from "@/lib/types";
import { dateTime } from "@/lib/format";

const COVERAGE = {
  covered: { mark: "●", label: "Covered", note: "Tier A or B survey evidence exists." },
  partial: { mark: "◐", label: "Partial", note: "Only qualitative or Tier C evidence." },
  gap: { mark: "○", label: "Gap", note: "No approved study found." },
} as const;

function Result({ check }: { check: CoverageCheck }) {
  const [submission, setSubmission] = useState<string | null>(check.submitted_at ? `Sent ${dateTime(check.submitted_at)}.` : null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function save(path: string, filename: string) {
    setError(null);
    try {
      await download(path, filename);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not download the file.");
    }
  }

  async function submit() {
    setError(null);
    setSending(true);
    try {
      const result = await api<{ adapter: string; status: string }>(`/api/commissioning/${check.id}/submit`, { method: "POST" });
      setSubmission(result.status === "sent"
        ? "Sent to the S&I commissioning process."
        : "Saved for S&I. Download the JSON or PDF to attach it to your commissioning request.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not hand over the check.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="section" aria-label="Coverage result" id="coverage-result" style={{ scrollMarginTop: 16 }}>
      <div className="section-head">
        <h2>{check.title}</h2>
        <span className="tag">{dateTime(check.created_at)}</span>
      </div>
      {check.result.objectives.map((o) => (
        <div className="row" key={o.text}>
          <div className="text">
            <p className="note-title">
              <span aria-hidden>{COVERAGE[o.coverage].mark}</span> {COVERAGE[o.coverage].label}
            </p>
            <p className="claim-text">{o.text}</p>
            <p className="hint">{COVERAGE[o.coverage].note}</p>
          </div>
          <aside aria-label="Evidence">
            <ul className="sources">
              <li className="label">Evidence</li>
              {o.finding_ids.length === 0 && <li className="muted">None found.</li>}
              {uniqueByStudy(o.finding_ids.map((id) => check.findings?.[id])).map(({ source }) => (
                <li key={source.study_id}><Citation source={source} /></li>
              ))}
            </ul>
          </aside>
        </div>
      ))}
      <div style={{ maxWidth: "var(--measure)", marginTop: 8 }}>
        <h3 style={{ marginBottom: 6 }}>Recommended new scope</h3>
        <p>{check.result.recommended_new_scope}</p>
      </div>
      <div className="actions" style={{ marginTop: 16 }}>
        <button className="btn btn-primary" onClick={submit} disabled={sending || !!submission}>Send to S&amp;I commissioning</button>
        <button className="btn" onClick={() => save(`/api/commissioning/${check.id}/export.json`, `coverage-${check.id.slice(0, 8)}.json`)}>
          <Download size={15} strokeWidth={1.5} aria-hidden /> Download JSON
        </button>
        <button className="btn" onClick={() => save(`/api/commissioning/${check.id}/export.pdf`, `coverage-${check.id.slice(0, 8)}.pdf`)}>
          <Download size={15} strokeWidth={1.5} aria-hidden /> Download PDF
        </button>
      </div>
      {submission && <p className="muted small" style={{ marginTop: 8 }}>{submission}</p>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function Commission() {
  const { profile } = useSession();
  const [title, setTitle] = useState("");
  const [objectives, setObjectives] = useState("");
  const [check, setCheck] = useState<CoverageCheck | null>(null);
  const [previous, setPrevious] = useState<CoverageCheck[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CoverageCheck[]>("/api/commissioning").then(setPrevious).catch(() => setPrevious([]));
  }, [profile?.id, check?.id]);

  async function open(id: string) {
    setError(null);
    try {
      setCheck(await api<CoverageCheck>(`/api/commissioning/${id}`));
      // The result renders above the list; bring it into view.
      requestAnimationFrame(() => document.getElementById("coverage-result")?.scrollIntoView({ block: "start" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open that check.");
    }
  }

  async function run(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const lines = objectives.split("\n").map((l) => l.trim()).filter(Boolean);
      const created = await api<CoverageCheck>("/api/commissioning/coverage", { method: "POST", json: { title, objectives: lines } });
      await open(created.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The check could not run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="page-head">
        <p className="eyebrow">Checkpoint 4 · commissioning</p>
        <title>Before you commission · Evidence brief</title>
        <h1>Before you commission</h1>
        <p>
          List your research objectives. Each one is checked against approved studies your team can read, so new
          fieldwork covers only what is missing. You decide whether to send the result to S&amp;I.
        </p>
      </section>
      <form onSubmit={run} style={{ maxWidth: 820 }}>
        <div className="field">
          <label htmlFor="title">Request title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3}
                 placeholder="SME digital lending refresh" />
        </div>
        <div className="field">
          <label htmlFor="objectives">Objectives, one per line</label>
          <textarea id="objectives" rows={5} value={objectives} onChange={(e) => setObjectives(e.target.value)} required
                    placeholder={"Understand why SME owners abandon online loan applications\nExplore whether SME owners want a named contact person"} />
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary" disabled={busy || title.trim().length < 3 || !objectives.trim()}>
          {busy ? "Checking existing studies…" : "Check coverage"}
        </button>
      </form>

      {check && <Result key={check.id} check={check} />}

      {previous.length > 0 && (
        <section className="section" style={{ marginTop: 40 }}>
          <div className="section-head"><h2>Earlier checks</h2></div>
          <ul className="list-plain" style={{ maxWidth: 820 }}>
            {previous.map((p) => (
              <li key={p.id} className="actions" style={{ justifyContent: "space-between" }}>
                <button className="btn btn-quiet" onClick={() => open(p.id)}>{p.title}</button>
                <span className="mono small muted">
                  {p.submitted_at ? `sent · ` : ""}{dateTime(p.created_at)}
                </span>
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
      <Commission />
    </SignedIn>
  );
}
