"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { ChevronRight, Info, Lock, Printer } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Brief, ChartSpec, Claim, QualContrast, RestrictedMatch, SourceView, Tier } from "@/lib/types";
import { dateTime, DIFFERS_LABELS, fmtValue, modelLabel, monthYear, n, provenanceLabel } from "@/lib/format";
import { CiteChip, Meter, MethodLine, SourceChip, SourceList, TierBadge, type CitationItem } from "./Citation";
import { EmotionTags } from "./Emotion";
import { CiteLink } from "./ReportLink";
import { RequestAccess } from "./RequestAccess";
import { AnalystPanel } from "./brief/AnalystPanel";
import { AudienceAnswer } from "./brief/AudienceAnswer";
import { FollowUp } from "./brief/FollowUp";
import { ConflictRow, NoteRow, PatternRow } from "./brief/Segments";

// recharts is the heaviest dependency; load it only for briefs that have charts.
const MetricChart = dynamic(() => import("./MetricChart").then((m) => m.MetricChart), {
  ssr: false,
  loading: () => <div className="chart-placeholder" aria-hidden />,
});

interface SectionProps {
  title: string;
  id: string;
  /** One line under the title saying what the section holds, so a closed section still informs. */
  summary?: React.ReactNode;
  tag?: string;
  intro?: string;
  open: boolean;
  onToggle: (id: string) => void;
  children: React.ReactNode;
}

/**
 * A section of the evidence that opens and closes. Closed, it shows its title and a one-line summary
 * computed from the brief (counts, codes, tiers), never new wording from the model. Print opens every
 * section, so the PDF is always the full brief.
 */
function Section({ title, id, summary, tag, intro, open, onToggle, children }: SectionProps) {
  return (
    <section className="section fold" id={id} data-open={open ? "true" : "false"} aria-labelledby={`${id}-title`}>
      <h2 className="fold-head" id={`${id}-title`}>
        <button type="button" aria-expanded={open} aria-controls={`${id}-body`} onClick={() => onToggle(id)}>
          <ChevronRight size={18} strokeWidth={2} aria-hidden className="fold-chev" />
          <span className="fold-text">
            <span className="fold-title">
              {title}
              {tag && <span className="tag">{tag}</span>}
            </span>
            {summary && <span className="fold-summary">{summary}</span>}
          </span>
        </button>
      </h2>
      <div className="fold-body" id={`${id}-body`}>
        {intro && <p className="section-intro">{intro}</p>}
        {children}
      </div>
    </section>
  );
}

function citations(claim: Claim, sources: Record<string, SourceView>): CitationItem[] {
  // One card per study page and place: a claim citing two figures from the same table (cashback and
  // travel, both p.3, both NCR) would otherwise show two identical cards.
  const seen = new Set<string>();
  const items: CitationItem[] = [];
  for (const e of claim.evidence) {
    const source = sources[e.finding_id];
    const key = source && [source.study_code, source.page ?? "", source.region_label, e.stance].join("|");
    if (source && key && !seen.has(key)) {
      seen.add(key);
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
        {claim.disputed?.length ? (
          <span className="chip chip-flag disputed-tag">Studies differ, S&amp;I checking: {claim.disputed.join(", ")}</span>
        ) : null}
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
          <li key={b.study_id} className="ref">
            <div className="ref-top">
              {source?.document_url ? (
                <CiteLink studyId={b.study_id} code={b.study_code} page={pages[0] ?? null} title={b.study_title} />
              ) : (
                <CiteChip code={b.study_code} page={pages[0] ?? null} title={b.study_title} />
              )}
              <TierBadge tier={b.tier} basis={source?.tier_basis} />
            </div>
            <Link className="ref-title" href={`/studies/${b.study_id}`} title={b.study_title}>{b.study_title}</Link>
            <div className="ref-meta">
              {[
                source?.method_detail ?? `${b.method_type === "quant" ? "Survey" : "Mixed method"} · n=${n(b.sample_size)}`,
                source?.fieldwork_label ?? monthYear(b.fieldwork_end),
                source?.provenance === "public" ? provenanceLabel(source) : "",
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

/** "41–52%": the spread of one metric across the groups and studies in its chart. */
function figureRange(chart: ChartSpec): string {
  const values = chart.bars.map((b) => b.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (lo === hi) return fmtValue(hi, chart.unit);
  const bare = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
  if (chart.unit === "%") return `${bare(lo)}–${bare(hi)}%`;
  if (chart.unit === "rank") return `rank ${bare(lo)}–${bare(hi)}`;
  return `${bare(lo)}–${bare(hi)}`;
}

/**
 * The charted metrics as figures to take in at a glance. Every number is a chart value read from the
 * studies in the database; the writer supplies none of them. A spread is shown rather than one bar,
 * so a reader does not take a single group's figure for the whole picture.
 */
function KeyFigures({ charts }: { charts: ChartSpec[] }) {
  const shown = charts.filter((c) => c.bars.length > 0).slice(0, 4);
  if (!shown.length) return null;
  return (
    <section className="key-figures" aria-labelledby="figures-title">
      <h2 id="figures-title" className="visually-hidden">Key figures</h2>
      <ul>
        {shown.map((c) => {
          const studyCount = new Set(c.bars.map((b) => b.study_id)).size;
          const disputed = c.bars.some((b) => b.disputed);
          return (
            <li key={c.metric_key}>
              <a href={`#chart-${c.metric_key}`}>
                <span className="kf-value">{figureRange(c)}</span>
                <span className="kf-label">{c.title}</span>
                <span className="kf-foot">
                  {c.bars.length} {c.bars.length === 1 ? "group" : "groups"} · {studyCount} {studyCount === 1 ? "study" : "studies"}
                  {disputed && <span className="flag-text"> · studies differ</span>}
                </span>
              </a>
            </li>
          );
        })}
      </ul>
      <p className="hint">Ranges across the groups in the charts below. Every figure is read from a study, not written by the model.</p>
    </section>
  );
}

interface StudyUse {
  source: SourceView;
  count: number;
  pages: number[];
}

/** Each study cited anywhere in the brief, once, strongest tier first. */
function studiesUsed(sources: Record<string, SourceView>): StudyUse[] {
  const byStudy = new Map<string, { source: SourceView; count: number; pages: Set<number> }>();
  for (const s of Object.values(sources)) {
    const entry = byStudy.get(s.study_id) ?? { source: s, count: 0, pages: new Set<number>() };
    entry.count += 1;
    if (s.page != null) entry.pages.add(s.page);
    byStudy.set(s.study_id, entry);
  }
  const rank = (t: Tier | null) => (t ? "ABC".indexOf(t) : 3);
  return [...byStudy.values()]
    .map((e) => ({ source: e.source, count: e.count, pages: [...e.pages].sort((a, b) => a - b) }))
    .sort((a, b) => rank(a.source.tier) - rank(b.source.tier) || a.source.study_code.localeCompare(b.source.study_code));
}

/** "1 Tier A, 2 Tier B, 1 Tier C". */
function tierCounts(studies: StudyUse[]): string {
  const counts: Record<string, number> = {};
  for (const { source } of studies) if (source.tier) counts[source.tier] = (counts[source.tier] ?? 0) + 1;
  return ["A", "B", "C"].filter((t) => counts[t]).map((t) => `${counts[t]} Tier ${t}`).join(", ");
}

function StudiesUsed({ sources }: { sources: Record<string, SourceView> }) {
  return (
    <ul className="study-grid">
      {studiesUsed(sources).map(({ source, count, pages }) => (
        <li key={source.study_id} className="study-card">
          <div className="top">
            <CiteChip code={source.study_code} />
            <TierBadge tier={source.tier} basis={source.tier_basis} />
          </div>
          <Link className="title" href={`/studies/${source.study_id}`}>{source.study_title}</Link>
          <MethodLine source={source} />
          <div className="source-meta">
            {[
              source.provenance === "public" ? provenanceLabel(source) : source.owner_team,
              source.area_label ?? "",
              `${count} ${count === 1 ? "finding" : "findings"} cited`,
              pages.length ? `p.${pages.join(", ")}` : "",
            ].filter(Boolean).join(" · ")}
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * The sections of the brief as a bar of chips, pinned while reading. A chip opens its section and
 * jumps to it (the article's link handler does both); the section in view is marked.
 */
function OnThisPage({ items }: { items: { id: string; label: string }[] }) {
  const [active, setActive] = useState(items[0]?.id);
  // After a click, the jump's own scrolling must not move the mark to another section.
  const heldUntil = useRef(0);
  const ids = items.map((i) => i.id).join(",");
  useEffect(() => {
    const els = ids.split(",").map((id) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0] && Date.now() > heldUntil.current) setActive(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -55% 0px" },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [ids]);
  return (
    <nav className="toc no-print" aria-label="Sections of this brief">
      <ul>
        {items.map((i) => (
          <li key={i.id}>
            <a
              href={`#${i.id}`}
              aria-current={active === i.id ? "location" : undefined}
              // Near the end of the page a section can't scroll to the top, so mark the clicked one.
              onClick={() => {
                heldUntil.current = Date.now() + 1000;
                setActive(i.id);
              }}
            >
              {i.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
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
  const studies = studiesUsed(sources);
  const tiers = tierCounts(studies);
  const hasCharts = breakdown.length > 0 || brief.charts.length > 0;
  const quotes = qual.reduce((sum, c) => sum + c.verbatim_ids.length, 0);
  const headlineCodes = [...new Set(headline.flatMap((c) => c.evidence.map((e) => sources[e.finding_id]?.study_code)).filter(Boolean))];
  const levelLabel = level[0].toUpperCase() + level.slice(1);
  const topicLabel = (topic: string) => brief.topic_labels?.[topic] ?? topic;

  // Sections that are warnings or actions start open; the detail starts closed under its summary.
  const sectionIds = [
    "headline",
    hasCharts && "breakdown",
    brief.context_notes.length > 0 && "depends",
    patterns.length > 0 && "patterns",
    qual.length > 0 && "people",
    brief.unresolved_conflicts.length > 0 && "conflicts",
    brief.gaps.length > 0 && "gaps",
    brief.restricted_matches.length > 0 && "restricted",
    "studies",
    "confidence",
  ].filter((x): x is string => Boolean(x));
  const tocLabels: Record<string, string> = {
    headline: "Headline", breakdown: "Breakdown", depends: "Who was asked", patterns: trends ? "Trends" : "Patterns",
    people: "What people say", conflicts: "Conflicts", gaps: "Gaps", restricted: "Restricted", studies: "Studies",
    confidence: "Confidence",
  };
  const toc = [
    ...(Object.values(brief.summaries ?? {}).some((v) => v?.text) ? [{ id: "answer", label: "Answer" }] : []),
    ...sectionIds.map((id) => ({ id, label: tocLabels[id] })),
  ];
  const [open, setOpen] = useState<Set<string>>(() => new Set(["conflicts", "gaps", "restricted"]));
  const toggle = useCallback((id: string) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const allOpen = sectionIds.every((id) => open.has(id));

  /** Opens the section holding `id` (a section, a chart, the analyst panel), then scrolls to it. */
  const reveal = useCallback((id: string) => {
    const target = document.getElementById(id);
    const section = target?.closest<HTMLElement>("section.fold");
    if (!target) return;
    if (section) setOpen((prev) => (prev.has(section.id) ? prev : new Set(prev).add(section.id)));
    requestAnimationFrame(() => requestAnimationFrame(() => target.scrollIntoView({ block: "start" })));
  }, []);

  // The brief loads after navigation, so the browser's own jump to #analyst or #confidence has
  // already happened against an empty page; do it once the content is here.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) reveal(id);
  }, [brief.id, reveal]);

  /** In-page links (#studies, #confidence, a key figure's chart) open their section before jumping. */
  function onClick(e: React.MouseEvent) {
    const link = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]');
    if (!link) return;
    const id = link.getAttribute("href")!.slice(1);
    if (!id || !document.getElementById(id)) return;
    e.preventDefault();
    history.replaceState(null, "", `#${id}`);
    reveal(id);
  }

  const fold = (id: string) => ({ id, open: open.has(id), onToggle: toggle });

  return (
    <article onClick={onClick}>
      <title>{`${brief.question} · ALAMKansya`}</title>
      <p className="print-only print-mast">
        ALAMKansya evidence brief · BPI Strategy &amp; Insights · Synthetic demonstration data
      </p>
      <header className="brief-head">
        <p className="crumbs no-print">
          <Link href="/">Ask another question</Link>
          {brief.follow_up_of && (
            <span>
              Follow-up to <Link href={`/briefs/${brief.follow_up_of.id}`}>{brief.follow_up_of.question}</Link>
            </span>
          )}
        </p>
        <h1>{brief.question}</h1>
        <div className="brief-meta">
          <span>{dateTime(brief.created_at)}</span>
          <span>{Object.keys(sources).length} findings from <a href="#studies">{studies.length} {studies.length === 1 ? "study" : "studies"}</a></span>
          {brief.generated_by && <span>Drafted by {modelLabel(brief.generated_by)}, checked by rules</span>}
          {brief.dropped_claims > 0 && <span>{brief.dropped_claims} claim(s) removed by the checks</span>}
        </div>
        <PreparedFor brief={brief} />
        {brief.generator_note && <p className="hint">{brief.generator_note}</p>}
      </header>

      <OnThisPage items={toc} />

      {/* The brief in one screen: the answer, its figures, and how far to trust it. */}
      <div className="brief-summary">
        <AudienceAnswer brief={brief} />
        <KeyFigures charts={brief.charts} />
        <div className="brief-glance">
          <div className="glance-main">
            <a href="#confidence" className="glance-confidence">
              <Meter level={level} />
              <span>
                <strong>{levelLabel} confidence.</strong> {brief.confidence.reasons[0]}
              </span>
            </a>
            {tiers && (
              <span className="glance-tiers">
                Based on {studies.length} {studies.length === 1 ? "study" : "studies"}: {tiers}
              </span>
            )}
          </div>
          <button type="button" className="btn btn-quiet no-print" onClick={() => window.print()}>
            <Printer size={15} strokeWidth={1.5} aria-hidden /> Print or save as PDF
          </button>
        </div>
      </div>

      <FollowUp brief={brief} />

      <div className="evidence-head">
        <div>
          <h2>The evidence</h2>
          <p className="muted small">Open a section for the findings, charts and sources behind the answer.</p>
        </div>
        <button
          type="button"
          className="btn no-print"
          onClick={() => setOpen(allOpen ? new Set() : new Set(sectionIds))}
          aria-controls={sectionIds.map((id) => `${id}-body`).join(" ")}
        >
          {allOpen ? "Close all" : "Open all"}
        </button>
      </div>

      <Section
        title="Headline"
        summary={headline.length > 0 ? `The main finding · cites ${headlineCodes.join(", ")}` : "No single headline the evidence supports"}
        {...fold("headline")}
      >
        {headline.length > 0 ? (
          headline.map((c, i) => <ClaimRow key={i} claim={c} brief={brief} variant="headline" first={i === 0} />)
        ) : (
          <p className="headline-text" style={{ maxWidth: "var(--measure)" }}>
            {brief.no_headline_message ?? "No single headline: the quantitative evidence does not support one summary statement."}
          </p>
        )}
        {qual.length === 0 && brief.disclaimer && <p className="disclaimer"><Info size={16} strokeWidth={1.75} aria-hidden />{brief.disclaimer}</p>}
      </Section>

      {hasCharts && (
        <Section
          title="Breakdown"
          summary={[
            breakdown.length ? `${breakdown.length} ${breakdown.length === 1 ? "finding" : "findings"} by segment, age and region` : "",
            brief.charts.length ? `${brief.charts.length} ${brief.charts.length === 1 ? "chart" : "charts"}` : "",
          ].filter(Boolean).join(" · ")}
          {...fold("breakdown")}
        >
          {breakdown.map((c, i) => (
            <ClaimRow key={i} claim={c} brief={brief} variant="breakdown" first={i === 0} />
          ))}
          {brief.charts.map((chart) => (
            <div className="row" key={chart.metric_key} id={`chart-${chart.metric_key}`}>
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
          summary={brief.context_notes
            .map((note) => `${topicLabel(note.topic)}: differs by ${note.differs_by.map((d) => DIFFERS_LABELS[d].toLowerCase()).join(", ")}`)
            .join(" · ")}
          intro="Each line is one group's result, with who was asked, where and when. Survey results come first; group discussions support them below."
          {...fold("depends")}
        >
          {brief.context_notes.map((note) => (
            <NoteRow key={note.topic} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {patterns.length > 0 && (
        <Section
          title={trends ? "Two trends in the same study" : "Two patterns in the same study"}
          summary={patterns.map((note) => topicLabel(note.topic)).join(" · ")}
          intro="One study found different results for different groups of the people it asked. Each holds for its own group."
          {...fold("patterns")}
        >
          {patterns.map((note) => (
            <PatternRow key={note.topic + note.finding_ids.join()} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {qual.length > 0 && (
        <Section
          title="What people say"
          tag="Indicative"
          summary={`${qual.length} ${qual.length === 1 ? "insight" : "insights"} from group discussions${quotes ? ` · ${quotes} ${quotes === 1 ? "quote" : "quotes"}` : ""} · how people feel, not how many`}
          {...fold("people")}
        >
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
          summary={<span className="flag-text">{brief.unresolved_conflicts.length} unresolved · treat the related claims with caution</span>}
          intro="These studies asked the same kind of people in the same period and still report different results. Treat the related claims with caution."
          {...fold("conflicts")}
        >
          {brief.unresolved_conflicts.map((note) => (
            <ConflictRow key={note.topic + note.finding_ids.join()} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {brief.gaps.length > 0 && (
        <Section
          title="Gaps"
          summary={`${brief.gaps.length} ${brief.gaps.length === 1 ? "thing" : "things"} the evidence does not cover`}
          {...fold("gaps")}
        >
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
          summary={`${brief.restricted_matches.length} ${brief.restricted_matches.length === 1 ? "study" : "studies"} your team cannot read yet · request access`}
          intro="These studies match your question, but your team cannot read them yet. Nothing from them was used in this brief."
          {...fold("restricted")}
        >
          <ul className="restricted">
            {brief.restricted_matches.map((m) => (
              <RestrictedRow key={m.study_id} match={m} />
            ))}
          </ul>
        </Section>
      )}

      <Section
        title="Studies behind this brief"
        summary={`${studies.length} ${studies.length === 1 ? "study" : "studies"}${tiers ? `: ${tiers}` : ""}`}
        intro="Every study cited above, once. The chips beside each claim open the report at the cited page."
        {...fold("studies")}
      >
        <StudiesUsed sources={sources} />
      </Section>

      <Section title="Confidence" summary={`${levelLabel} · computed from study tiers, not by the model · ask an analyst`} {...fold("confidence")}>
        <div className="row">
          <div className="text">
            <p className="confidence-level">
              <Meter level={level} />
              {levelLabel}
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
