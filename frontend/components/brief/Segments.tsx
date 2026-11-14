import Link from "next/link";
import type { Brief, ContextNote, DiffersBy } from "@/lib/types";
import { DIFFERS_LABELS } from "@/lib/format";
import { parseConflict, parseSegments, parseStudyIntro, type SegmentLine } from "@/lib/segments";
import { SourceList, uniqueByStudy } from "../Citation";
import { useSession } from "../Session";

const capitalise = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** "SI-2026-041, survey of 1,200, Jul 2026" with the study code set as a code. */
function Detail({ text }: { text: string }) {
  if (!text) return null;
  const parts = text.split(/,\s+/);
  return (
    <span className="seg-detail">
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && " · "}
          {/^[A-Z]{2,}-\d{4}-\d{2,4}$/.test(p) ? <span className="mono">{p}</span> : p}
        </span>
      ))}
    </span>
  );
}

/** One population per line: who, where and when on the left; what that group's result was on the right. */
function Lines({ lines, caption }: { lines: { who: React.ReactNode; detail?: string; stance?: string; result: string }[]; caption: string }) {
  return (
    <ul className="segments" aria-label={caption}>
      {lines.map((l, i) => (
        <li key={i}>
          <span className="seg-who">
            {l.who}
            {l.detail && <Detail text={l.detail} />}
          </span>
          <span className="seg-arrow" aria-hidden>→</span>
          <span className="seg-result">
            <span className="visually-hidden">: </span>
            {l.stance && <span className="seg-stance">{capitalise(l.stance)}</span>}
            {l.result && <strong className="nums">{l.result}</strong>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function DiffersChips({ by }: { by: DiffersBy[] }) {
  if (!by.length) return null;
  return (
    <span className="differs">
      <span className="muted small" style={{ fontWeight: 400 }}>differs by</span>
      {by.map((d) => (
        <span key={d} className="chip">{DIFFERS_LABELS[d]}</span>
      ))}
    </span>
  );
}

function labelOf(note: ContextNote, brief: Brief) {
  return brief.topic_labels?.[note.topic] ?? note.topic;
}

const asLines = (lines: SegmentLine[]) => lines.map((l) => ({ who: l.who, detail: l.detail, stance: l.stance, result: l.result }));

/**
 * A context difference as S&I asked for it: the topic as a short label, then each population's
 * result on its own line ("Credit card applicants aged 20–40 in Metro Manila · SI-2026-041 · Jul 2026
 * → A driver of drop-off 37%"), never "the studies disagree".
 */
export function NoteRow({ note, brief }: { note: ContextNote; brief: Brief }) {
  const label = labelOf(note, brief);
  const parsed = parseSegments(note.explanation, label);
  return (
    <div className="row">
      <div className="text">
        <h3 className="note-title">
          {label}
          <DiffersChips by={note.differs_by} />
        </h3>
        {parsed ? (
          <>
            <Lines lines={asLines(parsed.lines)} caption={`${label}, by group`} />
            {(parsed.tail || parsed.area) && (
              <p className="seg-tail">
                {parsed.tail ?? `${capitalise(parsed.area ?? "")}.`}
              </p>
            )}
          </>
        ) : (
          <p>{note.explanation}</p>
        )}
      </div>
      <SourceList items={uniqueByStudy(note.finding_ids.map((id) => brief.sources[id]))} />
    </div>
  );
}

/** Two trends (or patterns) inside one study: who the study asked, then each subgroup's result. */
export function PatternRow({ note, brief }: { note: ContextNote; brief: Brief }) {
  const label = labelOf(note, brief);
  const parsed = parseSegments(note.explanation, label);
  const intro = parseStudyIntro(parsed?.intro ?? null);
  const first = brief.sources[note.finding_ids[0]];
  return (
    <div className="row">
      <div className="text">
        <h3 className="note-title">
          {label}
          <DiffersChips by={note.differs_by} />
        </h3>
        {parsed ? (
          <>
            {intro ? (
              <p className="pattern-who">
                Target respondents: <strong>{intro.who}</strong>
                <Detail text={[first?.study_code, intro.detail].filter(Boolean).join(", ")} />
              </p>
            ) : (
              parsed.intro && <p className="pattern-who">{capitalise(parsed.intro)}</p>
            )}
            <Lines lines={asLines(parsed.lines)} caption={`${label}, by group within the study`} />
            {parsed.area && <p className="seg-tail">{capitalise(parsed.area)}.</p>}
            {parsed.tail && <p className="seg-tail">{parsed.tail}</p>}
          </>
        ) : (
          <p>{note.explanation}</p>
        )}
      </div>
      <SourceList items={uniqueByStudy(note.finding_ids.map((id) => brief.sources[id]))} />
    </div>
  );
}

/** Where an analyst is with this brief's automatic check, said next to the conflict. */
function AnalystStatus({ brief }: { brief: Brief }) {
  const isSi = useSession().profile?.role === "si_analyst";
  const e = brief.escalation;
  if (e?.status === "open") {
    return (
      <p className="analyst-status">
        <span className="status status-wait">{e.existing ? "Joined an existing check" : "An analyst is checking"}</span>
        <span>
          {e.existing && (
            <>
              S&amp;I was already checking these studies from an earlier brief; their reply appears under{" "}
              <Link href="/analyst">Ask an analyst</Link>.{" "}
            </>
          )}
          Don&rsquo;t rely on either figure alone until then.
        </span>
      </p>
    );
  }
  if (e?.status === "answered") {
    return (
      <p className="analyst-status">
        <span className="status status-ok">Analyst replied</span>
        <a href="#analyst">Read the reply</a>
      </p>
    );
  }
  // Business users' conflicts are always routed to S&I. When the same conflict is already open from
  // an earlier brief, the backend links to that escalation instead of opening another one, so this
  // brief carries none of its own.
  if (!e && !isSi) {
    return (
      <p className="analyst-status">
        <span className="status status-wait">Sent to an analyst</span>
        <span>
          S&amp;I was already checking these studies from an earlier brief; their reply appears under{" "}
          <Link href="/analyst">Ask an analyst</Link>. Don&rsquo;t rely on either figure alone until then.
        </span>
      </p>
    );
  }
  return (
    <p className="analyst-status">
      <span className="status">Not checked yet</span>
      <span>Don&rsquo;t rely on either figure alone. <a href="#analyst">Ask an analyst</a> to check both studies.</span>
    </p>
  );
}

/** An unresolved conflict: what each study found, who both asked, and the analyst's status. */
export function ConflictRow({ note, brief }: { note: ContextNote; brief: Brief }) {
  const label = labelOf(note, brief);
  const parsed = parseConflict(note.explanation, label);
  return (
    <div className="row">
      <div className="text conflict">
        <p className="conflict-label">Unresolved conflict</p>
        <h3 className="note-title">{label}</h3>
        {parsed ? (
          <>
            <p className="seg-caption">What each study found</p>
            <Lines
              caption={`${label}: what each study found`}
              lines={parsed.lines.map((l) => ({
                who: <span className="mono">{l.code}</span>,
                detail: l.detail,
                stance: "found",
                result: l.result,
              }))}
            />
            {parsed.context && <p className="seg-tail">{parsed.context}</p>}
          </>
        ) : (
          <p>{note.explanation}</p>
        )}
        <AnalystStatus brief={brief} />
      </div>
      <SourceList items={uniqueByStudy(note.finding_ids.map((id) => brief.sources[id]))} />
    </div>
  );
}
