"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { Info, Lock, Printer } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Brief, ChartSpec, Claim, ContextNote, Escalation, RestrictedMatch, SourceView } from "@/lib/types";
import { dateTime, DIFFERS_LABELS, monthYear, n, provenanceLabel } from "@/lib/format";
import { CiteChip, Meter, SourceChip, SourceList, TierBadge, uniqueByStudy, type CitationItem } from "./Citation";
import { CiteLink } from "./ReportLink";
import { RequestAccess } from "./RequestAccess";

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
      </footer>
    </blockquote>
  );
}

function ClaimRow({ claim, sources, variant, first = true }: { claim: Claim; sources: Record<string, SourceView>; variant: "headline" | "breakdown" | "qual"; first?: boolean }) {
  return (
    <div className="row">
      <div className="text">
        <p className={variant === "headline" ? "headline-text" : "claim-text"}>{claim.text}</p>
        {claim.qual_only && variant !== "qual" && <span className="chip qual-tag">Indicative, qualitative</span>}
        {variant === "qual" && claim.verbatim_ids.map((id) => <Verbatim key={id} source={sources[id]} />)}
      </div>
      <SourceList items={citations(claim, sources)} showLabel={first} />
    </div>
  );
}

function NoteRow({ note, brief, conflict }: { note: ContextNote; brief: Brief; conflict?: boolean }) {
  const label = brief.topic_labels?.[note.topic] ?? note.topic;
  return (
    <div className="row">
      <div className={conflict ? "text conflict" : "text"}>
        {conflict && <p className="conflict-label">Unresolved conflict</p>}
        <p className="note-title">
          {label}
          {note.differs_by.length > 0 && (
            <span className="differs" aria-label={`Differs by ${note.differs_by.join(", ")}`}>
              <span className="muted small" style={{ fontWeight: 400 }}>differs by</span>
              {note.differs_by.map((d) => (
                <span key={d} className="chip">{DIFFERS_LABELS[d]}</span>
              ))}
            </span>
          )}
        </p>
        <p>{note.explanation}</p>
      </div>
      <SourceList items={uniqueByStudy(note.finding_ids.map((id) => brief.sources[id]))} />
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
              <TierBadge tier={b.tier} sample={`n=${n(b.sample_size)}`} when={b.fieldwork_end?.slice(0, 4) ?? "n.d."} />
            </div>
            <Link className="title" href={`/studies/${b.study_id}`}>{b.study_title}</Link>
            <div className="source-meta">
              {[
                source?.provenance === "public" ? provenanceLabel(source) : "",
                b.method_type === "quant" ? "Quantitative" : "Mixed method",
                b.region_label,
                `fieldwork ${monthYear(b.fieldwork_end)}`,
                pages.length > 1 ? `pages ${pages.join(", ")}` : "",
              ].filter(Boolean).join(" · ")}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

const ESCALATION_REASONS: Record<string, string> = {
  user_request: "You asked an analyst to check this brief.",
  unresolved_conflict: "Sent to an analyst automatically: studies of the same population disagree.",
  low_confidence: "Sent to an analyst automatically: confidence is low.",
};

/**
 * Ask an analyst about this brief: the question form, then the escalation's status and the analyst's
 * reply, then a follow-up once the reply is in. Shown on every brief, conflict or not.
 */
function AnalystPanel({ brief }: { brief: Brief }) {
  const [escalation, setEscalation] = useState<Escalation | null>(brief.escalation);
  // The reply a follow-up was asked about. A brief carries only its latest escalation, so keep the
  // earlier reply on screen for this visit; every reply stays under Ask an analyst.
  const [earlier, setEarlier] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const waiting = escalation?.status === "open";
  const followUp = escalation != null && !waiting;
  const reply = escalation?.response ?? null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const created = await api<Escalation>("/api/escalations", { method: "POST", json: { brief_id: brief.id, note } });
      setEarlier(reply);
      setEscalation({ ...created, response: null });
      setNote("");
      setOpen(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="side-panel analyst-panel" aria-labelledby="analyst-title">
      <div className="analyst-head">
        <h2 id="analyst-title">Ask an analyst</h2>
        {escalation && (
          <span className={waiting ? "status status-wait" : escalation.status === "answered" ? "status status-ok" : "status"}>
            {waiting ? "Waiting for S&I" : escalation.status === "answered" ? "Answered" : "Closed"}
          </span>
        )}
      </div>
      <p>
        {escalation
          ? ESCALATION_REASONS[escalation.reason] ?? "Sent to S&I."
          : "Not sure the evidence answers your question? An S&I analyst can check the brief and reply here."}
      </p>
      {earlier && (
        <blockquote className="analyst-reply">
          <span className="who">Earlier reply</span>
          {earlier}
        </blockquote>
      )}
      {reply && (
        <blockquote className="analyst-reply">
          <span className="who">Analyst&rsquo;s reply</span>
          {reply}
        </blockquote>
      )}
      {open ? (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="escalation-note">{followUp ? "Your follow-up question" : "What should the analyst check?"}</label>
            <textarea id="escalation-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} required autoFocus />
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions">
            <button className="btn btn-primary" disabled={busy || note.trim().length < 3}>{busy ? "Sending…" : "Send to S&I"}</button>
            <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        !waiting && (
          <button type="button" className="btn" onClick={() => setOpen(true)}>
            {followUp ? "Ask a follow-up" : "Ask an analyst"}
          </button>
        )
      )}
      {escalation && (
        <p className="hint analyst-foot">
          Every question and reply is kept under <Link href="/analyst">Ask an analyst</Link>.
        </p>
      )}
    </section>
  );
}

export function BriefView({ brief }: { brief: Brief }) {
  const { sources } = brief;
  const headline = brief.claims.filter((c) => c.kind === "headline");
  const breakdown = brief.claims.filter((c) => c.kind === "breakdown");
  const qual = brief.claims.filter((c) => c.kind === "qualitative_insight");
  const level = brief.confidence.level;

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

      <Section title="Headline">
        {headline.length > 0 ? (
          headline.map((c, i) => <ClaimRow key={i} claim={c} sources={sources} variant="headline" first={i === 0} />)
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
            <ClaimRow key={i} claim={c} sources={sources} variant="breakdown" first={i === 0} />
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

      {qual.length > 0 && (
        <Section title="What people say" tag="Indicative · qualitative">
          {brief.disclaimer && <p className="disclaimer"><Info size={16} strokeWidth={1.75} aria-hidden />{brief.disclaimer}</p>}
          {qual.map((c, i) => (
            <ClaimRow key={i} claim={c} sources={sources} variant="qual" first={i === 0} />
          ))}
        </Section>
      )}

      {brief.context_notes.length > 0 && (
        <Section
          title="Context differences"
          intro="Where studies point in different directions because they asked different people, at a different time or by a different method."
        >
          {brief.context_notes.map((note) => (
            <NoteRow key={note.topic} note={note} brief={brief} />
          ))}
        </Section>
      )}

      {brief.unresolved_conflicts.length > 0 && (
        <Section
          title="Unresolved conflicts"
          intro="These studies sampled the same population in the same period and still disagree. Treat the related claims with caution."
        >
          {brief.unresolved_conflicts.map((note) => (
            <NoteRow key={note.topic + note.finding_ids.join()} note={note} brief={brief} conflict />
          ))}
          {brief.escalation?.reason === "unresolved_conflict" && (
            <p className="notice small">
              Sent to an S&amp;I analyst automatically. <a href="#confidence">See the status and any reply</a>.
            </p>
          )}
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
