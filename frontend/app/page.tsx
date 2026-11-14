"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Meter, type ConfidenceLevel } from "@/components/Citation";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError } from "@/lib/api";
import type { Brief, BriefSummary } from "@/lib/types";
import { dateTime } from "@/lib/format";

// What happens while a brief is prepared, in order. The server reports which step it is on
// (GET /api/briefs/progress, indexes as in backend/app/progress.py), including a second writing pass
// when the checks send the first draft back.
const STEPS = [
  "Search approved studies your team can read",
  "Compare who each study asked, and when",
  "Write the brief from those findings only",
  "Check every claim against its sources",
];

const MAX_LENGTH = 500;
const RECENT_SHOWN = 6;

interface Health {
  llm_ready?: boolean;
  llm_problem?: string | null;
  search_ready?: boolean;
  search_problem?: string | null;
}

interface Progress {
  step: number;
  detail: string | null;
}

function Preparing() {
  const [seconds, setSeconds] = useState(0);
  const [progress, setProgress] = useState<Progress | null>(null);
  useEffect(() => {
    const started = Date.now();
    let live = true;
    const timer = window.setInterval(() => {
      setSeconds(Math.floor((Date.now() - started) / 1000));
      api<Progress | null>("/api/briefs/progress")
        .then((p) => { if (live && p) setProgress(p); })
        .catch(() => {});   // progress is a display aid; the brief request itself reports errors
    }, 1000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);
  const current = progress?.step ?? 0;
  return (
    <div className="preparing">
      <p role="status">
        <span className="pulse" aria-hidden />
        Preparing the brief <span className="muted nums" style={{ fontWeight: 400 }}>{seconds}s</span>
      </p>
      <ol aria-live="polite">
        {STEPS.map((s, i) => (
          <li key={s} className={i < current ? "done" : i === current ? "current" : undefined} aria-current={i === current ? "step" : undefined}>
            {s}
            {i === current && progress?.detail && <span className="step-detail">{progress.detail}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

const EXAMPLES = [
  "Why do SME owners drop off during online loan applications?",
  "How do market vendors feel about accepting QR payments?",
  "Do young professionals prefer cashback or travel rewards on credit cards?",
];

const LEVELS: ConfidenceLevel[] = ["high", "medium", "low"];

function RecentBriefs({ briefs }: { briefs: BriefSummary[] }) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? briefs : briefs.slice(0, RECENT_SHOWN);
  return (
    <section className="recent" aria-labelledby="recent-title">
      <div className="recent-head">
        <h2 id="recent-title">Your recent briefs</h2>
        <span className="muted small nums">{briefs.length} in total</span>
      </div>
      <ul className="recent-list">
        {shown.map((b) => {
          const level = LEVELS.find((l) => l === b.confidence);
          return (
            <li key={b.id}>
              <Link href={`/briefs/${b.id}`}>
                <span className="q">{b.question}</span>
                <span className="conf">
                  {level ? (
                    <>
                      <Meter level={level} />
                      {level[0].toUpperCase() + level.slice(1)} confidence
                    </>
                  ) : (
                    "No confidence set"
                  )}
                </span>
                <span className="when">{dateTime(b.created_at)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      {briefs.length > RECENT_SHOWN && (
        <button type="button" className="btn btn-quiet" style={{ marginTop: 10 }} onClick={() => setShowAll((s) => !s)} aria-expanded={showAll}>
          {showAll ? "Show fewer" : `Show all ${briefs.length}`}
        </button>
      )}
    </section>
  );
}

function Ask() {
  const router = useRouter();
  const { profile } = useSession();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<BriefSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api<BriefSummary[]>("/api/briefs").then(setRecent).catch(() => setRecent([]));
  }, [profile?.id]);

  // Warn before anyone asks: a hosted search model that can't be reached stops briefs altogether; a
  // writer that can't be reached means briefs come from templates.
  useEffect(() => {
    api<Health>("/api/health").then(setHealth).catch(() => setHealth(null));
  }, []);

  async function ask(text: string) {
    // Always a fresh brief, examples included: reopening an earlier one would hide studies the team
    // has been granted since, and show stale access-request states.
    setBusy(true);
    setError(null);
    try {
      const brief = await api<Brief>("/api/briefs", { method: "POST", json: { question: text } });
      router.push(`/briefs/${brief.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The brief could not be prepared.");
      setBusy(false);
    }
  }

  const ready = question.trim().length >= 5;

  return (
    <>
      <title>Ask a question · Evidence brief</title>
      <div className="ask-layout">
        <section className="ask-intro" aria-labelledby="ask-title">
          <h1 id="ask-title">What does our research already say?</h1>
          <p>
            Ask a business question in plain English or Filipino. The brief draws only on approved S&amp;I studies that{" "}
            {profile?.team_name ?? "your team"} can read, puts survey evidence first, and cites every claim.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (ready) ask(question.trim());
            }}
          >
            <div className="composer">
              <label htmlFor="question" className="visually-hidden">Your question</label>
              <textarea
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  // Enter asks; Shift+Enter adds a line, as in a chat box.
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (ready && !busy) ask(question.trim());
                  }
                }}
                placeholder="For example: what stops small business owners finishing a loan application?"
                maxLength={MAX_LENGTH}
                aria-describedby="question-hint"
              />
              <div className="composer-foot">
                <p className="hint nums" id="question-hint">
                  {question.length > 0 ? `${question.length} of ${MAX_LENGTH} characters` : "Press Enter to ask"}
                </p>
                <button className="btn btn-primary" disabled={busy || !ready}>
                  {busy ? "Preparing…" : "Ask"}
                </button>
              </div>
            </div>
            {health?.search_ready === false ? (
              <p className="disclaimer writer-down" role="status">
                <span>
                  Search can&rsquo;t reach its hosted model right now, so questions can&rsquo;t be answered until it is back.
                  {health.search_problem && <span className="muted small"> {health.search_problem}</span>}
                </span>
              </p>
            ) : health?.llm_ready === false ? (
              <p className="disclaimer writer-down" role="status">
                <span>
                  The AI writer can&rsquo;t be reached right now, so briefs will be written from templates and will say
                  so. Every claim is still checked against its sources.
                  {health.llm_problem && <span className="muted small"> {health.llm_problem}</span>}
                </span>
              </p>
            ) : null}
            {busy && <Preparing />}
            {error && <p className="error" role="alert" style={{ marginTop: 12 }}>{error}</p>}
          </form>

          <div className="examples">
            <h2 id="examples-title">Or try one of these</h2>
            <ul aria-labelledby="examples-title">
              {EXAMPLES.map((q) => (
                <li key={q}>
                  <button type="button" className="example" disabled={busy} onClick={() => { setQuestion(q); ask(q); }}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <aside aria-label="About the brief">
          <div className="side-panel">
            <h2>How a brief is made</h2>
            <ol className="steps">
              {STEPS.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
          </div>
          <div className="side-panel">
            <h2>Reading the tier badges</h2>
            <ul className="tier-key">
              <li><span className="tier tier-A"><b>A</b></span><span>Carries the most weight in a brief.</span></li>
              <li><span className="tier tier-B"><b>B</b></span><span>Good evidence with a limit on method, sample size or age.</span></li>
              <li><span className="tier tier-C"><b>C</b></span><span>Indicative. A headline never rests on it alone.</span></li>
            </ul>
            <p style={{ margin: "14px 0 0" }}>
              Scored in code from method, sample size and how recent the fieldwork is, never by the model.
            </p>
          </div>
        </aside>
      </div>

      {recent.length > 0 && <RecentBriefs briefs={recent} />}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn>
      <Ask />
    </SignedIn>
  );
}
