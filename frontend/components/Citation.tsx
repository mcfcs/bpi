import Link from "next/link";
import type { SourceView, Tier } from "@/lib/types";
import { monthYear, provenanceLabel, sampleLabel, year } from "@/lib/format";
import { CiteLink } from "./ReportLink";

/** Tier letter on its colour, then sample and year: "A | n=1,200 · 2026". Either may be left out. */
export function TierBadge({ tier, sample, when }: { tier: Tier | null; sample?: string; when?: string }) {
  const rest = [sample, when].filter(Boolean).join(" · ");
  const label = [`Tier ${tier ?? "not set"}`, sample, when].filter(Boolean).join(", ");
  return (
    <span className={`tier tier-${tier ?? "C"}`} title={`Robustness tier ${tier ?? "not set"}`}>
      {/* A plain span cannot carry an accessible name, so the reading goes in hidden text. */}
      <span className="visually-hidden">{label}</span>
      <b aria-hidden>{tier ?? "–"}</b>
      {rest && <span aria-hidden>{rest}</span>}
    </span>
  );
}

/** The study code a reader quotes back to S&I, with the report page when there is one. */
export function CiteChip({ code, page, title }: { code: string | null; page?: number | null; title?: string }) {
  return (
    <span className="cite" title={title}>
      {code ?? "no code"}
      {page != null && <span className="page">· p.{page}</span>}
    </span>
  );
}

/**
 * The chip for one cited finding: a link into the report at the finding's page when the study has a
 * document (page 1 if the page is unknown), the plain code otherwise.
 */
export function SourceChip({ source }: { source: Pick<SourceView, "study_id" | "study_code" | "study_title" | "page" | "document_url"> }) {
  return source.document_url ? (
    <CiteLink studyId={source.study_id} code={source.study_code} page={source.page} title={source.study_title} />
  ) : (
    <CiteChip code={source.study_code} page={source.page} title={source.study_title} />
  );
}

export interface CitationItem {
  source: SourceView;
  stance?: string;
}

/** A study card: code and tier, the study's title, then method, region and fieldwork date. */
export function Citation({ source, stance }: CitationItem) {
  const details = [
    source.provenance === "public" ? provenanceLabel(source) : "",
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
        <SourceChip source={source} />
        <TierBadge tier={source.tier} sample={sampleLabel(source)} when={year(source.fieldwork_end)} />
      </div>
      <Link className="title" href={`/studies/${source.study_id}`}>{source.study_title}</Link>
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
