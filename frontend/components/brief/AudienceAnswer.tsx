"use client";

import { useState } from "react";
import type { Audience, Brief } from "@/lib/types";
import { SourceChip, TierBadge, uniqueByStudy } from "../Citation";

const AUDIENCES: { key: Audience; label: string }[] = [
  { key: "executive", label: "Executive" },
  { key: "analyst", label: "Analyst" },
  { key: "plain", label: "Plain language" },
];

const STORAGE_KEY = "si-evidence:audience";
const isAudience = (v: unknown): v is Audience => v === "executive" || v === "analyst" || v === "plain";

function storedAudience(): Audience {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (isAudience(v)) return v;
  } catch {
    // Storage blocked (private windows): fall back to the default for this visit.
  }
  return "executive";
}

/**
 * The answer in three registers: the same facts and citations, worded for an executive, an analyst
 * or a general reader. Executive is the default; the reader's choice is kept in this browser.
 * Only rendered on the client (the brief loads after the page), so reading storage up front is safe.
 */
export function AudienceAnswer({ brief }: { brief: Brief }) {
  const summaries = brief.summaries ?? {};
  const available = AUDIENCES.filter((a) => summaries[a.key]?.text);
  const [chosen, setChosen] = useState<Audience>(storedAudience);
  if (!available.length) return null;
  const audience = available.some((a) => a.key === chosen) ? chosen : available[0].key;
  const summary = summaries[audience]!;
  const cited = uniqueByStudy(summary.finding_ids.map((id) => brief.sources[id]));

  function choose(next: Audience) {
    setChosen(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not saved; the choice still applies to this page.
    }
  }

  return (
    <section className="section answer" id="answer" aria-labelledby="answer-title">
      <div className="answer-head">
        <h2 id="answer-title">Answer</h2>
        <div className="segmented no-print" role="group" aria-label="Write the answer for">
          {available.map((a) => (
            <button key={a.key} type="button" aria-pressed={audience === a.key} onClick={() => choose(a.key)}>
              {a.label}
            </button>
          ))}
        </div>
      </div>
      <p className="answer-text" aria-live="polite">{summary.text}</p>
      {cited.length > 0 && (
        <div className="answer-sources">
          <span className="muted small">Cites</span>
          <ul>
            {cited.map(({ source }) => (
              <li key={source.study_id}>
                <SourceChip source={source} />
                <TierBadge tier={source.tier} basis={source.tier_basis} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="hint">Same evidence in each version; only the wording changes. Details and every source follow below.</p>
    </section>
  );
}
