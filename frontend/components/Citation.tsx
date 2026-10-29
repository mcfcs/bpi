import type { SourceView, Tier } from "@/lib/types";
import { monthYear, sampleLabel, year } from "@/lib/format";

/** Square-cornered monospace label: "A · n=1,200 · 2026". */
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

export interface CitationItem {
  source: SourceView;
  stance?: string;
}

/** Two lines per citation: badge and study code, then method, region and fieldwork date. */
export function Citation({ source, stance }: CitationItem) {
  const details = [
    source.method_label,
    source.region_label,
    `fieldwork ${monthYear(source.fieldwork_end)}`,
    source.subgroup_label && source.finding_type !== "verbatim" ? source.subgroup_label : "",
    stance && stance !== "supports" ? stance : "",
    source.tier_overridden ? "tier set by S&I" : "",
  ].filter(Boolean);
  return (
    <>
      <TierBadge tier={source.tier} sample={sampleLabel(source)} when={year(source.fieldwork_end)} />{" "}
      <span className="mono small" title={source.study_title}>{source.study_code}</span>
      <div className="source-meta">{details.join(" · ")}</div>
    </>
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
