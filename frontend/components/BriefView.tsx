"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { Info, Lock, Printer } from "lucide-react";
import { useEffect } from "react";
import type { Brief, ChartSpec, Claim, QualContrast, RestrictedMatch, SourceView } from "@/lib/types";
import { dateTime, n, provenanceLabel } from "@/lib/format";
import { CiteChip, Meter, MethodLine, SourceChip, SourceList, TierBadge, type CitationItem } from "./Citation";
import { EmotionTags } from "./Emotion";
import { CiteLink } from "./ReportLink";
import { RequestAccess } from "./RequestAccess";
import { AnalystPanel } from "./brief/AnalystPanel";
import { AudienceAnswer } from "./brief/AudienceAnswer";
import { ConflictRow, NoteRow, PatternRow } from "./brief/Segments";

// recharts is the heaviest dependency; load it only for briefs that have charts.
const MetricChart = dynamic(() => import("./MetricChart").then((m) => m.MetricChart), {
  ssr: false,
  loading: () => <div className="chart-placeholder" aria-hidden />,
});

function Section({ title, tag, intro, id, children }: { title: string; tag?: string; intro?: string; id?: string; children: React.ReactNode }) {
  return (
    <section className="section" aria-label={title} id={id}>
      <div className="section-head">
        <h2>{title}</h2>
        {tag && <span className="tag">{tag}</span>}
      </div>
      {intro && <p className="section-intro">{intro}</p>}
      {children}
    </section>
  );
}

function citations(claim: Claim, sources: Record<string, SourceView>): CitationItem[] {
  const seen = new Set<string>();
  const items: CitationItem[] = [];
  for (const e of claim.evidence) {
    const source = sources[e.finding_id];
    if (source && !seen.has(e.finding_id)) {
      seen.add(e.finding_id);
      items.push({ source, stance: e.stance });
    }
  }
  return items;
}

function Verbatim({ source }: { source: SourceView | undefined }) {
  if (!source) return null;
  const who = [source.subgroup?.segment, source.subgroup?.region].filter(Boolean).join(", ");
  return (
    <blockquote className="verbatim">
      “{source.text}”
      <footer>
        {who && <span>{who}</span>}
        <SourceChip source={source} />
        {source.emotion && <EmotionTags emotions={[source.emotion]} className="emotions inline" />}
      </footer>
    </blockquote>
  );
}

/**
 * A group view that runs against a survey figure on the same topic, shown with who said it and what
 * the survey measured. Different people and a different method, so it is colour, never a conflict.
 */
function SurveyContext({ contrast, sources }: { contrast: QualContrast; sources: Record<string, SourceView> }) {
  const qual = sources[contrast.finding_id];
  // One finding per study, preferring the study-level figure over a subgroup.
  const surveys = new Map<string, SourceView>();
  for (const id of contrast.quant_finding_ids) {
    const s = sources[id];
    if (!s) continue;
    const seen = surveys.get(s.study_id);
    if (!seen || (seen.subgroup && !s.subgroup)) surveys.set(s.study_id, s);
  }
  if (!qual || surveys.size === 0) return null;
  return (
    <div className="survey-context">
      <p className="sc-who">
        <strong>Said by</strong> {qual.population_label}
        <span className="muted"> ({[qual.method_detail ?? qual.method_label, qual.fieldwork_label].filter(Boolean).join(", ")})</span>
      </p>
      <p className="sc-label"><strong>What the survey measured</strong></p>
      <ul>
        {[...surveys.values()].map((s) => (
          <li key={s.finding_id}>
            {s.text}{" "}
            <span className="muted small">
              {s.population_label} · {[s.method_detail, s.fieldwork_label].filter(Boolean).join(" · ")}
            </span>{" "}
            <SourceChip source={s} />
          </li>
        ))}
      </ul>
      <p className="hint">
        Different people, asked a different way: the groups show how some participants see it; the survey
        measures how common it is. Read together, not as a conflict.
      </p>
    </div>
  );
}

/** The contrast sentence the writer appends repeats what SurveyContext shows; leave it to the box. */
const CONTRAST_SENTENCE = /\s*This view comes from [\s\S]*$/;

function ClaimRow({ claim, brief, variant, first = true }: { claim: Claim; brief: Brief; variant: "headline" | "breakdown" | "qual"; first?: boolean }) {
  const { sources } = brief;
  const contrast = variant === "qual"
    ? brief.qual_contrasts?.find((c) => claim.evidence.some((e) => e.finding_id === c.finding_id))
    : undefined;
  const text = contrast ? claim.text.replace(CONTRAST_SENTENCE, "") : claim.text;
  return (
    <div className="row">
      <div className="text">
        <p className={variant === "headline" ? "headline-text" : "claim-text"}>{text}</p>
        {variant === "qual" && <EmotionTags emotions={claim.emotions} />}
        {claim.qual_only && variant !== "qual" && <span className="chip qual-tag">Indicative, qualitative</span>}
        {contrast && <SurveyContext contrast={contrast} sources={sources} />}
        {variant === "qual" && claim.verbatim_ids.map((id) => <Verbatim key={id} source={sources[id]} />)}
      </div>
      <SourceList items={citations(claim, sources)} showLabel={first} />
    </div>
  );
}

/** A matching study the reader's team cannot read: its catalogue line and the request flow. */
function RestrictedRow({ match }: { match: RestrictedMatch }) {
  return (
    <RequestAccess.Provider studyId={match.study_id} ownerTeam={match.owner_team} initialStatus={match.request_status}>
      <li>
        <div className="line">
          <span className="what">
            <Lock size={15} strokeWidth={1.75} aria-label="Restricted" role="img" style={{ color: "var(--muted)" }} />
            <CiteChip code={match.code} />
            <span>{match.title}</span>
            <span className="muted small">Owned by {match.owner_team}</span>
          </span>
          <RequestAccess.Action approved="Approved: ask again to include it" />
        </div>
        <RequestAccess.Form className="request-form" />
      </li>
    </RequestAccess.Provider>
  );
}

/** One entry per study in a chart, with the report pages its bars were read from. */
function chartStudies(chart: ChartSpec, sources: Record<string, SourceView>) {
  const studies = new Map<string, { bar: ChartSpec["bars"][number]; source?: SourceView; pages: Set<number> }>();
  for (const bar of chart.bars) {
    const source = sources[bar.finding_id];
    const entry = studies.get(bar.study_id) ?? { bar, source, pages: new Set<number>() };
    entry.source ??= source;
    if (source?.page != null) entry.pages.add(source.page);
    studies.set(bar.study_id, entry);
  }
  return [...studies.values()].map(({ bar, source, pages }) => {
    const sorted = [...pages].sort((a, b) => a - b);
    return { bar, source, pages: sorted };
  });
}

function ChartSources({ chart, sources }: { chart: ChartSpec; sources: Record<string, SourceView> }) {
  return (
    <aside aria-label="Chart sources">
      <ul className="sources">
        <li className="label">Chart sources</li>
        {chartStudies(chart, sources).map(({ bar: b, source, pages }) => (
          <li key={b.study_id} className="study-card">
            <div className="top">
              {source?.document_url ? (
                <CiteLink studyId={b.study_id} code={b.study_code} page={pages[0] ?? null} title={b.study_title} />
              ) : (
                <CiteChip code={b.study_code} page={pages[0] ?? null} title={b.study_title} />
              )}
              {source?.method_detail ? (
                <TierBadge tier={b.tier} basis={source.tier_basis} />
              ) : (
                <TierBadge tier={b.tier} sample={`n=${n(b.sample_size)}`} when={b.fieldwork_end?.slice(0, 4) ?? "n.d."} />
              )}
            </div>
            <Link className="title" href={`/studies/${b.study_id}`}>{b.study_title}</Link>
            {source?.method_detail && <MethodLine source={source} />}
            <div className="source-meta">
              {[
                source?.provenance === "public" ? provenanceLabel(source) : "",
                source?.method_detail ? "" : b.method_type === "quant" ? "Quantitative" : "Mixed method",
                b.region_label,
                pages.length > 1 ? `pages ${pages.join(", ")}` : "",
              ].filter(Boolean).join(" · ")}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/** "Prepared for Carla Mendoza · Cards & Payments", then how the brief was framed for that team. */
function PreparedFor({ brief }: { brief: Brief }) {
  const p = brief.prepared_for;
  if (!p) return null;
  // The note opens by repeating who it is for; the line above already says so.
  const rest = (p.note ?? "").replace(/^Prepared for [^.]*?\)\.\s*/, "").replace(/^Prepared for [^.]*\.\s*/, "");
  return (
    <div className="prepared-for">
      <p>
        Prepared for <strong>{p.name}</strong> · {p.team}
        {p.role_label && <span className="muted"> · {p.role_label}</span>}
      </p>
      {rest && <p className="hint">{rest}</p>}
    </div>
  );
}

export function BriefView({ brief }: { brief: Brief }) {
  const { sources } = brief;
  const headline = brief.claims.filter((c) => c.kind === "headline");
  const breakdown = brief.claims.filter((c) => c.kind === "breakdown");
  const qual = brief.claims.filter((c) => c.kind === "qualitative_insight");
  const patterns = brief.study_patterns ?? [];
  const level = brief.confidence.level;
  const trends = patterns.length > 0 && patterns.every((p) => /two trends/i.test(p.explanation));

  // The brief loads after navigation, so the browser's own jump to #analyst or #confidence has
  // already happened against an empty page; do it once the content is here.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [brief.id]);

  return (
    <article>
      <title>{`${brief.question} · Evidence brief`}</title>
      <header className="brief-head">
        <p className="crumbs no-print"><Link href="/">Ask another question</Link></p>
        <h1>{brief.question}</h1>
        <div className="brief-meta">
          <span>{dateTime(brief.created_at)}</span>
          <span>{Object.keys(sources).length} findings cited</span>
          {brief.generated_by && <span>Drafted by {brief.generated_by}, checked by rules</span>}
          {brief.dropped_claims > 0 && <span>{brief.dropped_claims} claim(s) removed by the checks</span>}
        </div>
        <PreparedFor brief={brief} />
        {brief.generator_note && <p className="hint">{brief.generator_note}</p>}
        <div className="brief-glance">
          <a href="#confidence" className="glance-confidence">
            <Meter level={level} />
            <span>
              <strong>{level[0].toUpperCase() + level.slice(1)} confidence.</strong>{" "}
              {brief.confidence.reasons[0]}
            </span>
          </a>
          <button type="button" className="btn btn-quiet no-print" onClick={() => window.print()}>
            <Printer size={15} strokeWidth={1.5} aria-hidden /> Print or save as PDF
          </button>
        </div>
      </header>

      <AudienceAnswer brief={brief} />

      <Section title="Headline">
        {headline.length > 0 ? (
          headline.map((c, i) => <ClaimRow key={i} claim={c} brief={brief} variant="headline" first={i === 0} />)
        ) : (
          <p className="headline-text" style={{ maxWidth: "var(--measure)" }}>
            {brief.no_headline_message ?? "No single headline: the quantitative evidence does not support one summary statement."}
          </p>
        )}
        {qual.length === 0 && brief.disclaimer && <p className="disclaimer"><Info size={16} strokeWidth={1.75} aria-hidden />{brief.disclaimer}</p>}
      </Section>

      {(breakdown.length > 0 || brief.charts.length > 0) && (
        <Section title="Breakdown" tag="by segment, age and region">
          {breakdown.map((c, i) => (
            <ClaimRow key={i} claim={c} brief={brief} variant="breakdown" first={i === 0} />
          ))}
          {brief.charts.map((chart) => (
            <div className="row" key={chart.metric_key}>
              <div className="text" style={{ maxWidth: "none" }}>
                <MetricChart chart={chart} />
              </div>
              <ChartSources chart={chart} sources={sources} />
            </div>
          ))}
        </Section>
      )}

      {brief.context_notes.length > 0 && (
        <Section
          title="It depends on who was asked"
          intro="Each line is one group's result, with who was asked, where and when. Survey results come first; group discussions support them below."
        >
          {brief.context_notes.map((note) => (
            <NoteRow key={note.topic} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {patterns.length > 0 && (
        <Section
          title={trends ? "Two trends in the same study" : "Two patterns in the same study"}
          intro="One study found different results for different groups of the people it asked. Each holds for its own group."
        >
          {patterns.map((note) => (
            <PatternRow key={note.topic + note.finding_ids.join()} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {qual.length > 0 && (
        <Section title="What people say" tag="Indicative · qualitative">
          {brief.disclaimer && <p className="disclaimer"><Info size={16} strokeWidth={1.75} aria-hidden />{brief.disclaimer}</p>}
          {qual.some((c) => c.emotions?.length) && (
            <p className="section-intro">Feelings are read from participants&rsquo; own words. They show how people sounded, not how many feel that way.</p>
          )}
          {qual.map((c, i) => (
            <ClaimRow key={i} claim={c} brief={brief} variant="qual" first={i === 0} />
          ))}
        </Section>
      )}

      {brief.unresolved_conflicts.length > 0 && (
        <Section
          title="Unresolved conflicts"
          intro="These studies asked the same kind of people in the same period and still report different results. Treat the related claims with caution."
        >
          {brief.unresolved_conflicts.map((note) => (
            <ConflictRow key={note.topic + note.finding_ids.join()} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {brief.gaps.length > 0 && (
        <Section title="Gaps">
          <ul className="gaps">
            {brief.gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </Section>
      )}

      {brief.restricted_matches.length > 0 && (
        <Section
          title="Restricted matches"
          intro="These studies match your question, but your team cannot read them yet. Nothing from them was used in this brief."
        >
          <ul className="restricted">
            {brief.restricted_matches.map((m) => (
              <RestrictedRow key={m.study_id} match={m} />
            ))}
          </ul>
        </Section>
      )}

      <Section title="Confidence" id="confidence">
        <div className="row">
          <div className="text">
            <p className="confidence-level">
              <Meter level={level} />
              {level[0].toUpperCase() + level.slice(1)}
            </p>
            <ul className="gaps">
              {brief.confidence.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <p className="hint">Computed from study tiers and how the studies relate, not reported by the model.</p>
          </div>
          <AnalystPanel key={brief.id} brief={brief} />
        </div>
      </Section>
    </article>
  );
}
