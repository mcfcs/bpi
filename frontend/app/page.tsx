"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError } from "@/lib/api";
import type { Brief, BriefSummary } from "@/lib/types";
import { dateTime } from "@/lib/format";

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
          {busy && <span className="muted small">Searching approved studies and checking every claim against its sources.</span>}
        </div>
        {error && <p className="error">{error}</p>}
        <div className="examples" aria-label="Example questions">
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
