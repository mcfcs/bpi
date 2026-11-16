"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { CiteChip } from "@/components/Citation";
import { LoadError } from "@/components/LoadError";
import { useSession } from "@/components/Session";
import { SignedIn } from "@/components/SiteHeader";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { Brief, Escalation, EscalationDraft } from "@/lib/types";
import { dayMonthYear, DIFFERS_LABELS } from "@/lib/format";

const AUDIENCES = ["BU leadership deck", "Campaign team", "Personal reference"] as const;

const DIFFERENCE_KIND = {
  unresolved_conflict: "Unresolved conflict",
  context_difference: "Differs by",
  within_study: "Two trends in one study",
} as const;

/** "Differs by age and region: Fees", "Unresolved conflict: Prefers cashback rewards". */
function differenceLabel(d: EscalationDraft["differences"][number]): string {
  if (d.kind === "context_difference" && d.differs_by.length) {
    const by = d.differs_by.map((x) => DIFFERS_LABELS[x].toLowerCase());
    const joined = by.length > 1 ? `${by.slice(0, -1).join(", ")} and ${by.at(-1)}` : by[0];
    return `${d.label}: differs by ${joined}`;
  }
  return `${DIFFERENCE_KIND[d.kind] ?? "Difference"}: ${d.label}`;
}

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** What happens after Send, as in S&I's mock: the second step is the human checkpoint. */
function NextSteps() {
  return (
    <aside className="side-panel" aria-labelledby="next-title">
      <h2 id="next-title">What happens next</h2>
      <ol className="steps next-steps">
        <li>
          <span>
            <strong>Joins the S&amp;I queue</strong>
            <span className="step-note">Your question and this brief arrive on the analyst desk.</span>
          </span>
        </li>
        <li className="checkpoint-step">
          <span>
            <strong>An analyst reviews it</strong> <span className="chip checkpoint-chip">Human checkpoint</span>
            <span className="step-note">A person checks the studies and the gaps you ticked. The system does not answer for them.</span>
          </span>
        </li>
        <li>
          <span>
            <strong>Endorsed answer</strong>
            <span className="step-note">The analyst&rsquo;s reply appears on your brief, with its status.</span>
          </span>
        </li>
        <li>
          <span>
            <strong>Kept for reuse</strong>
            <span className="step-note">The reply stays with the brief and under Ask an analyst, so you can come back to it and share it.</span>
          </span>
        </li>
      </ol>
    </aside>
  );
}

function DraftForm({ draft, waiting }: { draft: EscalationDraft; waiting: boolean }) {
  const router = useRouter();
  const [checked, setChecked] = useState<Set<string>>(() => new Set(draft.gaps.filter((g) => g.checked).map((g) => g.id)));
  const [question, setQuestion] = useState(draft.suggested_question);
  const [audience, setAudience] = useState("");
  const [neededBy, setNeededBy] = useState("");
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const briefHref = `/briefs/${draft.brief_id}`;

  function toggle(id: string) {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function send(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    // "Who is it for?" and "Needed by" travel in the note the analyst reads, after the drafted context.
    const framing = [audience && `Who it is for: ${audience}`, neededBy && `Needed by: ${dayMonthYear(neededBy)}`].filter(Boolean).join("\n");
    const note = [draft.note, framing, extra.trim() && `From the requester: ${extra.trim()}`].filter(Boolean).join("\n\n");
    try {
      await api<Escalation>("/api/escalations", {
        method: "POST",
        json: {
          brief_id: draft.brief_id,
          note,
          gaps: draft.gaps.filter((g) => checked.has(g.id)).map((g) => g.text),
          suggested_question: question.trim() || null,
        },
      });
      // A repeat of an open question returns the open one; either way its status is on the brief.
      router.push(`${briefHref}#analyst`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send the question.");
      setBusy(false);
    }
  }

  return (
    <form className="panel analyst-form" onSubmit={send} aria-describedby="draft-note">
      <p id="draft-note" className="hint" style={{ marginTop: 0 }}>
        Filled in from your brief. Change anything before you send it.
      </p>

      <div className="form-block">
        <h2>Your question</h2>
        <p className="asked">{draft.question}</p>
      </div>

      <div className="form-block">
        <h2>What the assistant found</h2>
        <p className="found">{draft.found}</p>
        {(draft.study_codes.length > 0 || draft.differences.length > 0) && (
          <ul className="found-chips" aria-label="Studies cited and differences">
            {draft.study_codes.map((code) => (
              <li key={code}><CiteChip code={code} /></li>
            ))}
            {draft.differences.map((d) => (
              <li key={d.kind + d.topic}>
                <span className={d.kind === "unresolved_conflict" ? "chip chip-flag" : "chip"} title={d.explanation}>
                  {differenceLabel(d)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {draft.confidence && <p className="hint">Confidence in the brief: {draft.confidence}.</p>}
      </div>

      {draft.gaps.length > 0 && (
        <fieldset className="form-block">
          <legend>Gaps to check</legend>
          <p className="hint" style={{ marginTop: 0 }}>Untick any the analyst can skip.</p>
          <ul className="checks">
            {draft.gaps.map((g) => (
              <li key={g.id}>
                <input type="checkbox" id={g.id} checked={checked.has(g.id)} onChange={() => toggle(g.id)} />
                <label htmlFor={g.id}>
                  {g.text}
                  {g.ask && <span className="check-ask">{g.ask}</span>}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      )}

      <div className="field form-block">
        <label htmlFor="suggested">Question for the analyst</label>
        <textarea id="suggested" name="suggested_question" autoComplete="off" rows={5} value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} />
        <p className="hint">Suggested from the brief. Make it as specific as you can.</p>
      </div>

      <div className="field-row">
        <fieldset className="form-block">
          <legend>Who is it for?</legend>
          <ul className="checks">
            {AUDIENCES.map((a, i) => (
              <li key={a}>
                <input type="radio" name="audience" id={`for-${i}`} value={a} checked={audience === a} onChange={() => setAudience(a)} />
                <label htmlFor={`for-${i}`}>{a}</label>
              </li>
            ))}
          </ul>
        </fieldset>
        <div className="field form-block">
          <label htmlFor="needed-by">Needed by</label>
          <input id="needed-by" name="needed_by" autoComplete="off" type="date" min={todayIso()} value={neededBy} onChange={(e) => setNeededBy(e.target.value)} />
          <p className="hint">Optional. Helps S&amp;I order the queue.</p>
        </div>
      </div>

      <div className="field form-block">
        <label htmlFor="extra">Anything else the analyst should know? <span className="muted" style={{ fontWeight: 400 }}>(optional)</span></label>
        <textarea id="extra" name="note" autoComplete="off" rows={3} value={extra} onChange={(e) => setExtra(e.target.value)} maxLength={600} />
      </div>

      {waiting && (
        <p className="notice small">An analyst is already looking at this brief. Sending adds your question to it.</p>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button className="btn btn-primary" disabled={busy}>{busy ? "Sending…" : "Send to S&I"}</button>
        <Link className="btn btn-quiet" href={briefHref}>Back to the brief</Link>
      </div>
    </form>
  );
}

function NewQuestion() {
  const { profile } = useSession();
  const briefId = useSearchParams().get("brief");
  const path = briefId ? `/api/briefs/${encodeURIComponent(briefId)}` : null;
  // Independent requests: the draft, and the brief for its current escalation status.
  const draft = useApi<EscalationDraft>(path && `${path}/escalation-draft`, profile?.id);
  const brief = useApi<Brief>(path, profile?.id);

  return (
    <>
      <title>Ask an analyst · ALAMKansya</title>
      <section className="page-head">
        {briefId && <p className="crumbs"><Link href={`/briefs/${briefId}`}>Back to the brief</Link></p>}
        <h1>Ask an analyst</h1>
        <p>An S&amp;I analyst checks what the assistant found and replies on your brief.</p>
        <p className="checkpoint">Human checkpoint 3 of 4: an analyst answers, not the system.</p>
      </section>
      {!briefId ? (
        <p className="notice">Open a brief and choose Ask an analyst to start a question. <Link href="/">Ask a question</Link></p>
      ) : draft.error ? (
        <LoadError message={/not found/i.test(draft.error) ? "This brief belongs to someone else, or it does not exist." : draft.error} onRetry={draft.reload} />
      ) : !draft.data ? (
        <p className="loading" role="status">Preparing your question from the brief…</p>
      ) : (
        <div className="split">
          <DraftForm key={draft.data.brief_id} draft={draft.data} waiting={brief.data?.escalation?.status === "open"} />
          <NextSteps />
        </div>
      )}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn>
      <Suspense fallback={<p className="loading" role="status">Loading…</p>}>
        <NewQuestion />
      </Suspense>
    </SignedIn>
  );
}
