"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError } from "@/lib/api";
import type { Brief, BriefSummary } from "@/lib/types";
import { dateTime } from "@/lib/format";

// What happens while a brief is prepared, in order. Shown as a list, not a fake progress bar:
// the server does not report which step it is on.
const STEPS = [
  "Search approved studies your team can read",
  "Compare who each study asked, and when",
  "Write the brief from those findings only",
  "Check every claim against its sources",
];

function Preparing() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="preparing" role="status" aria-live="polite">
      <p>
        Preparing the brief <span className="mono small muted">{seconds}s</span>
      </p>
      <ol>
        {STEPS.map((s) => (
          <li key={s}>{s}</li>
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

function Ask() {
  const router = useRouter();
  const { profile } = useSession();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<BriefSummary[]>([]);

  useEffect(() => {
    api<BriefSummary[]>("/api/briefs").then(setRecent).catch(() => setRecent([]));
  }, [profile?.id]);

  async function ask(text: string) {
    // The same question asked before: open that brief instead of writing a duplicate.
    const earlier = recent.find((b) => b.question.trim().toLowerCase() === text.trim().toLowerCase());
    if (earlier && EXAMPLES.includes(text)) {
      router.push(`/briefs/${earlier.id}`);
      return;
    }
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

  return (
    <>
      <title>Ask a question · Evidence brief</title>
      <section className="page-head">
        <p className="eyebrow">Strategy &amp; Insights · {profile?.team_name}</p>
        <h1>Ask a question</h1>
        <p>
          Ask a business question in plain language. The brief cites approved S&amp;I studies your team can read,
          weighs survey evidence first, and uses focus groups to explain why.
        </p>
      </section>

      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 5) ask(question.trim());
        }}
      >
        <label htmlFor="question" className="visually-hidden">Your question</label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="For example: why do SME owners drop off during online loan applications?"
          maxLength={500}
        />
        <div className="actions">
          <button className="btn btn-primary" disabled={busy || question.trim().length < 5}>
            {busy ? "Preparing the brief…" : "Ask a question"}
          </button>
        </div>
        {busy && <Preparing />}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="examples" role="group" aria-label="Example questions">
          <span className="muted small">Try one of these</span>
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="btn btn-quiet" disabled={busy} onClick={() => { setQuestion(q); ask(q); }}>
              {q}
            </button>
          ))}
        </div>
      </form>

      {recent.length > 0 && (
        <section className="section" style={{ marginTop: 48 }}>
          <div className="section-head">
            <h2>Your recent briefs</h2>
          </div>
          <ul className="list-plain" style={{ maxWidth: 820 }}>
            {recent.map((b) => (
              <li key={b.id} className="actions" style={{ justifyContent: "space-between" }}>
                <Link href={`/briefs/${b.id}`}>{b.question}</Link>
                <span className="mono small muted">
                  {b.confidence ? `Confidence ${b.confidence}` : ""} · {dateTime(b.created_at)}
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
      <Ask />
    </SignedIn>
  );
}
