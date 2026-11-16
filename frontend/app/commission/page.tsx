"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CircleCheck, CircleDashed, CirclePlus, Download, History, TriangleAlert } from "lucide-react";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Citation, CiteChip, uniqueByStudy } from "@/components/Citation";
import { RequestAccess } from "@/components/RequestAccess";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError, download } from "@/lib/api";
import type { CoverageCaveat, CoverageCheck, CoverageObjective, CoverageState } from "@/lib/types";
import { ageLabel, dateTime, monthsSince, monthYear } from "@/lib/format";

/** Four states, each with its own word and icon so none depends on colour. */
const COVERAGE: Record<CoverageState, { label: string; note: string; Icon: typeof CircleCheck }> = {
  covered: { label: "Covered", note: "Recent Tier A or B survey evidence exists.", Icon: CircleCheck },
  covered_stale: { label: "Covered, but old", note: "Tier A or B survey evidence exists, but the fieldwork is old.", Icon: History },
  partial: { label: "Partly covered", note: "Only qualitative or Tier C evidence.", Icon: CircleDashed },
  gap: { label: "New problem", note: "No approved study found: not yet researched.", Icon: CirclePlus },
};
const ORDER: CoverageState[] = ["covered", "covered_stale", "partial", "gap"];

function CoverageTag({ coverage }: { coverage: CoverageState }) {
  const { label, Icon } = COVERAGE[coverage] ?? COVERAGE.gap;
  return (
    <span className={`status coverage coverage-${coverage}`}>
      <Icon size={14} strokeWidth={2} aria-hidden />
      {label}
    </span>
  );
}

const isNew = (o: CoverageObjective) => o.new_problem ?? o.coverage === "gap";

/** "2 of 3 objectives already have evidence; 1 is a new problem." */
function NewProblems({ objectives }: { objectives: CoverageObjective[] }) {
  const fresh = objectives.filter(isNew);
  const total = objectives.length;
  const have = total - fresh.length;
  const sentence = fresh.length === 0
    ? total === 1 ? "The objective already has evidence; it is not a new problem."
      : `${total === 2 ? "Both" : `All ${total}`} objectives already have evidence; none is a new problem.`
    : have === 0
      ? `None of the ${total} objective${total === 1 ? "" : "s"} has evidence yet; ${total === 1 ? "it is a new problem" : "all are new problems"}.`
      : `${have} of ${total} objectives already ${have === 1 ? "has" : "have"} evidence; ${fresh.length} ${fresh.length === 1 ? "is a new problem" : "are new problems"}.`;
  return (
    <div className="panel panel-quiet new-problems" role="status">
      <h3>New problems</h3>
      <p className="np-sentence">{sentence}</p>
      {fresh.length > 0 && (
        <ul>
          {fresh.map((o) => (
            <li key={o.text}>{o.text}</li>
          ))}
        </ul>
      )}
      {fresh.length > 0 && <p className="hint">New fieldwork is needed only for these. The others can reuse the studies listed with them.</p>}
    </div>
  );
}

function Caveat({ caveat }: { caveat: CoverageCaveat }) {
  if (caveat.code === "restricted_match") {
    return (
      <div className="caveat">
        <p>{caveat.text}</p>
        {caveat.studies?.length ? (
          <ul className="restricted">
            {caveat.studies.map((s) => (
              <RequestAccess.Provider key={s.study_id} studyId={s.study_id} ownerTeam={s.owner_team} initialStatus={null}>
                <li>
                  <div className="line">
                    <span className="what">
                      <CiteChip code={s.code} />
                      <span>{s.title}</span>
                      <span className="muted small">Owned by {s.owner_team}</span>
                    </span>
                    <span className="actions">
                      <Link className="small" href={`/studies?q=${encodeURIComponent(s.code)}`}>See it in Studies</Link>
                      <RequestAccess.Action />
                    </span>
                  </div>
                  <RequestAccess.Form className="request-form" />
                </li>
              </RequestAccess.Provider>
            ))}
          </ul>
        ) : (
          <p><Link href="/studies">Find it in Studies</Link></p>
        )}
      </div>
    );
  }
  return (
    <p className="caveat caveat-conflict">
      <TriangleAlert size={15} strokeWidth={1.75} aria-hidden />
      <span>{caveat.text}</span>
    </p>
  );
}

function Objective({ o, check }: { o: CoverageObjective; check: CoverageCheck }) {
  const state = COVERAGE[o.coverage] ? o.coverage : "gap";
  // "Partly covered: qualitative or Tier C evidence only": the tag already says the first half.
  const label = o.coverage_label ?? COVERAGE[state].note;
  const detail = label.includes(": ") ? label.slice(label.indexOf(": ") + 2) : label.startsWith("Covered, but") ? "" : label;
  const months = monthsSince(o.newest_fieldwork);
  return (
    <div className="row">
      <div className="text">
        <h3 className="objective-text">{o.text}</h3>
        <p className="coverage-line">
          <CoverageTag coverage={state} />
          {detail && <span>{detail[0].toUpperCase() + detail.slice(1)}</span>}
        </p>
        {o.newest_fieldwork && (
          <p className={state === "covered_stale" ? "hint nums stale" : "hint nums"} style={{ marginTop: 0 }}>
            Newest fieldwork: {monthYear(o.newest_fieldwork)}
            {months != null && ` (${ageLabel(months)})`}
          </p>
        )}
        {o.caveats?.map((c, i) => <Caveat key={c.code + i} caveat={c} />)}
      </div>
      <aside aria-label="Evidence">
        <ul className="sources">
          <li className="label">Evidence</li>
          {o.finding_ids.length === 0 && <li className="empty small">No approved study covers this.</li>}
          {uniqueByStudy(o.finding_ids.map((id) => check.findings?.[id])).map(({ source }) => (
            <li key={source.study_id}><Citation source={source} /></li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

interface SubmitResult {
  adapter?: string;
  status?: string;
  already_submitted?: boolean;
  submitted_at?: string;
}

function Result({ check, canSend }: { check: CoverageCheck; canSend: boolean }) {
  const [submission, setSubmission] = useState<string | null>(
    check.submitted_at ? `Sent to S&I on ${dateTime(check.submitted_at)}.` : null,
  );
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
      const result = await api<SubmitResult>(`/api/commissioning/${check.id}/submit`, { method: "POST" });
      setSubmission(
        result.already_submitted
          ? `Already sent to S&I${result.submitted_at ? ` on ${dateTime(result.submitted_at)}` : ""}. Nothing was sent twice.`
          : result.status === "sent"
            ? "Sent to the S&I commissioning process."
            : "Sent to S&I. It is in their inbox; download the JSON or PDF to attach it to your commissioning request.",
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not hand over the check.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="section" aria-labelledby="result-title" id="coverage-result" style={{ scrollMarginTop: 16 }}>
      <div className="section-head">
        <h2 id="result-title">{check.title}</h2>
        <span className="tag nums">
          {check.requested_by ? `${check.requested_by} · ` : ""}Checked {dateTime(check.created_at)}
        </span>
      </div>
      <NewProblems objectives={check.result.objectives} />
      {check.result.objectives.map((o) => (
        <Objective key={o.text} o={o} check={check} />
      ))}
      <div className="panel panel-quiet" style={{ maxWidth: "var(--measure)", marginTop: 8 }}>
        <h3 style={{ marginBottom: 6 }}>Recommended new scope</h3>
        <p style={{ margin: 0 }}>{check.result.recommended_new_scope}</p>
      </div>
      <div className="actions" style={{ marginTop: 16 }}>
        {canSend && (
          <button className="btn btn-primary" onClick={submit} disabled={sending || !!submission}>
            {submission ? "Sent to S&I" : sending ? "Sending…" : "Send to S&I commissioning"}
          </button>
        )}
        <button className="btn" onClick={() => save(`/api/commissioning/${check.id}/export.json`, `coverage-${check.id.slice(0, 8)}.json`)}>
          <Download size={15} strokeWidth={1.5} aria-hidden /> Download JSON
        </button>
        <button className="btn" onClick={() => save(`/api/commissioning/${check.id}/export.pdf`, `coverage-${check.id.slice(0, 8)}.pdf`)}>
          <Download size={15} strokeWidth={1.5} aria-hidden /> Download PDF
        </button>
      </div>
      {submission && <p className="muted small" role="status" style={{ marginTop: 8 }}>{submission}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Commission() {
  const { profile } = useSession();
  const requested = useSearchParams().get("check");
  const profileId = profile?.id;
  const [title, setTitle] = useState("");
  const [objectives, setObjectives] = useState("");
  const [check, setCheck] = useState<CoverageCheck | null>(null);
  const [previous, setPrevious] = useState<CoverageCheck[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CoverageCheck[]>("/api/commissioning").then(setPrevious).catch(() => setPrevious([]));
  }, [profile?.id, check?.id]);

  const open = useCallback(async (id: string) => {
    setError(null);
    try {
      setCheck(await api<CoverageCheck>(`/api/commissioning/${id}`));
      // Keep the open check in the address bar, so it can be linked to (the S&I inbox does).
      window.history.replaceState(null, "", `?check=${encodeURIComponent(id)}`);
      // The result renders above the list; bring it into view.
      requestAnimationFrame(() => document.getElementById("coverage-result")?.scrollIntoView({ block: "start" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open that check.");
    }
  }, []);

  useEffect(() => {
    if (requested && profileId) open(requested);
  }, [requested, profileId, open]);

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

  // S&I can open any sent check from their inbox; only its requester hands it over.
  const canSend = !!check && (!check.requested_by || check.requested_by === profile?.display_name);

  return (
    <>
      <section className="page-head">
        <title>Before you commission · ALAMKansya</title>
        <h1>Before you commission</h1>
        <p>
          List your research objectives. Each one is checked against approved studies your team can read, so new
          fieldwork covers only the new problems. You decide whether to send the result to S&amp;I.
        </p>
        <p className="checkpoint">Human checkpoint 4 of 4: nothing is commissioned until you send it.</p>
      </section>
      <div className="split">
      <form onSubmit={run} className="panel">
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
      <aside className="side-panel" aria-label="What the result means">
        <h2>What the result means</h2>
        <ul className="coverage-key">
          {ORDER.map((k) => (
            <li key={k}>
              <CoverageTag coverage={k} />
              <span>{COVERAGE[k].note}</span>
            </li>
          ))}
        </ul>
        <p style={{ margin: "14px 0 0" }}>
          Every objective lists the studies behind its result, and flags conflicting studies or a restricted study
          that may also cover it.
        </p>
      </aside>
      </div>

      {check && <Result key={check.id} check={check} canSend={canSend} />}

      {previous.filter((p) => p.id !== check?.id).length > 0 && (
        <section className="section" style={{ marginTop: 56 }}>
          <div className="section-head"><h2>Earlier checks</h2></div>
          <ul className="list-plain" style={{ maxWidth: 920 }}>
            {previous.filter((p) => p.id !== check?.id).map((p) => (
              <li key={p.id} className="actions" style={{ justifyContent: "space-between" }}>
                <button className="btn btn-quiet" onClick={() => open(p.id)}>{p.title.trim() || "Untitled check"}</button>
                <span className="small muted nums">
                  {p.submitted_at ? `Sent · ` : ""}{dateTime(p.created_at)}
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
      <Suspense fallback={<p className="loading" role="status">Loading…</p>}>
        <Commission />
      </Suspense>
    </SignedIn>
  );
}
