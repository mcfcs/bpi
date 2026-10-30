import type { SourceView, Tier } from "@/lib/types";
import { monthYear, sampleLabel, year } from "@/lib/format";

/** Tier letter on its colour, then sample and year: "A | n=1,200 · 2026". */
export function TierBadge({ tier, sample, when }: { tier: Tier | null; sample: string; when: string }) {
  const label = `Tier ${tier ?? "not set"}, ${sample}, ${when}`;
  return (
    <span className={`tier tier-${tier ?? "C"}`} title={`Robustness tier ${tier ?? "not set"}`}>
      {/* A plain span cannot carry an accessible name, so the reading goes in hidden text. */}
      <span className="visually-hidden">{label}</span>
      <b aria-hidden>{tier ?? "–"}</b>
      <span aria-hidden>
        {sample} · {when}
      </span>
    </span>
  );
}

/**
 * The study code a reader quotes back to S&I, with the report page when the backend sends one.
 * `page` is not in the API yet; the chip shows it only once it arrives, and never guesses.
 */
export function CiteChip({ code, page, title }: { code: string | null; page?: number | null; title?: string }) {
  return (
    <span className="cite" title={title}>
      {code ?? "no code"}
      {page != null && <span className="page">· p.{page}</span>}
    </span>
  );
}

export interface CitationItem {
  source: SourceView;
  stance?: string;
}

/** A study card: code and tier, the study's title, then method, region and fieldwork date. */
export function Citation({ source, stance }: CitationItem) {
  const page = (source as SourceView & { page?: number | null }).page;
  const details = [
    source.method_label,
    source.region_label,
    `fieldwork ${monthYear(source.fieldwork_end)}`,
    source.subgroup_label && source.finding_type !== "verbatim" ? source.subgroup_label : "",
    stance && stance !== "supports" ? stance : "",
    source.tier_overridden ? "tier set by S&I" : "",
  ].filter(Boolean);
  return (
    <div className="study-card">
      <div className="top">
        <CiteChip code={source.study_code} page={page} />
        <TierBadge tier={source.tier} sample={sampleLabel(source)} when={year(source.fieldwork_end)} />
      </div>
      <div className="title">{source.study_title}</div>
      <div className="source-meta">{details.join(" · ")}</div>
    </div>
  );
}

export function SourceList({ items, label = "Sources", showLabel = true }: { items: CitationItem[]; label?: string; showLabel?: boolean }) {
  if (!items.length) return <div />;
  return (
    <aside aria-label={label}>
      <ul className="sources">
        {showLabel && <li className="label">{label}</li>}
        {items.map(({ source, stance }) => (
          <li key={source.finding_id}>
            <Citation source={source} stance={stance} />
          </li>
        ))}
      </ul>
    </aside>
  );
}

/** One citation per study, in first-seen order. */
export function uniqueByStudy(sources: (SourceView | undefined)[]): CitationItem[] {
  const seen = new Map<string, CitationItem>();
  for (const source of sources) {
    if (source && !seen.has(source.study_id)) seen.set(source.study_id, { source });
  }
  return [...seen.values()];
}

const LEVELS = { high: 3, medium: 2, low: 1 } as const;
export type ConfidenceLevel = keyof typeof LEVELS;

/** Three bars, filled to the confidence level. Decorative: the level is always written beside it. */
export function Meter({ level }: { level: ConfidenceLevel }) {
  return (
    <span className="meter" aria-hidden>
      {[1, 2, 3].map((i) => (
        <i key={i} className={i <= LEVELS[level] ? "on" : ""} />
      ))}
    </span>
  );
}
