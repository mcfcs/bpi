import Link from "next/link";
import type { SourceView, Tier } from "@/lib/types";
import { ageLabel, monthsSince, monthYear, provenanceLabel, sampleLabel, year } from "@/lib/format";
import { CiteLink } from "./ReportLink";

/**
 * Tier letter on its colour, then sample and year: "A | n=1,200 · 2026". Either may be left out.
 * `basis` says what the tier was scored from ("Recency only" for qualitative work); it goes in the
 * tooltip and the hidden reading.
 */
export function TierBadge({ tier, sample, when, basis }: { tier: Tier | null; sample?: string; when?: string; basis?: string | null }) {
  const rest = [sample, when].filter(Boolean).join(" · ");
  const scored = basis ? `scored from ${basis[0].toLowerCase()}${basis.slice(1)}` : "";
  const label = [`Tier ${tier ?? "not set"}`, sample, when, scored].filter(Boolean).join(", ");
  const title = `Robustness tier ${tier ?? "not set"}${basis ? `. Scored from: ${basis}` : ""}`;
  return (
    <span className={`tier tier-${tier ?? "C"}`} title={title}>
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

/** Survey or group work, from the backend's evidence kind when it is there. */
export function isQualSource(source: Pick<SourceView, "evidence_kind" | "method_type">): boolean {
  return source.evidence_kind ? source.evidence_kind === "qual" : source.method_type === "qual";
}

/**
 * What kind of evidence a source is and when it was gathered: "6 FGDs · 48 participants · Sep 2025".
 * For qualitative work recency is what its tier rests on, so the date is set in bold with its age.
 */
export function MethodLine({ source }: { source: SourceView }) {
  const method = source.method_detail ?? `${source.method_label} · ${sampleLabel(source)}`;
  const when = source.fieldwork_label ?? monthYear(source.fieldwork_end);
  const qual = isQualSource(source);
  const months = qual ? monthsSince(source.fieldwork_end) : null;
  return (
    <div className="method-line">
      {method} · {qual ? <strong>{when}</strong> : when}
      {months != null && <span className="age"> ({ageLabel(months)})</span>}
    </div>
  );
}

/** A study card: code and tier, the study's title, then method, sample and fieldwork, then who and where. */
export function Citation({ source, stance }: CitationItem) {
  const details = [
    source.provenance === "public" ? provenanceLabel(source) : "",
    source.region_label,
    source.subgroup_label && source.finding_type !== "verbatim" ? source.subgroup_label : "",
    stance && stance !== "supports" ? stance : "",
    source.tier_overridden ? "tier set by S&I" : "",
  ].filter(Boolean);
  // Older stored briefs carry no method_detail: fall back to the sample and year in the badge.
  const legacy = !source.method_detail;
  return (
    <div className="study-card">
      <div className="top">
        <SourceChip source={source} />
        <TierBadge
          tier={source.tier}
          sample={legacy ? sampleLabel(source) : undefined}
          when={legacy ? year(source.fieldwork_end) : undefined}
          basis={source.tier_basis}
        />
      </div>
      <Link className="title" href={`/studies/${source.study_id}`}>{source.study_title}</Link>
      <MethodLine source={source} />
      {details.length > 0 && <div className="source-meta">{details.join(" · ")}</div>}
    </div>
  );
}

/**
 * A compact reference beside a claim: the chip and tier, the study's title on one line, then method,
 * date and who the figure is about. The full study card appears once, under "Studies behind this
 * brief", so a study cited six times no longer repeats its whole card six times.
 */
export function SourceRef({ source, stance }: CitationItem) {
  const method = source.method_detail ?? `${source.method_label} · ${sampleLabel(source)}`;
  const when = source.fieldwork_label ?? monthYear(source.fieldwork_end);
  const about = [
    source.provenance === "public" ? provenanceLabel(source) : "",
    source.region_label,
    source.subgroup_label && source.finding_type !== "verbatim" ? source.subgroup_label : "",
    source.tier_overridden ? "tier set by S&I" : "",
  ].filter(Boolean);
  return (
    <div className="ref">
      <div className="ref-top">
        <SourceChip source={source} />
        <TierBadge tier={source.tier} basis={source.tier_basis} />
        {stance && stance !== "supports" && <span className="ref-stance">{stance}</span>}
      </div>
      <Link className="ref-title" href={`/studies/${source.study_id}`} title={source.study_title}>{source.study_title}</Link>
      <div className="ref-meta">{[method, when, ...about].join(" · ")}</div>
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
            <SourceRef source={source} stance={stance} />
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
