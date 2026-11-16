"use client";

import Link from "next/link";
import { CircleCheck, CircleDashed, CirclePlus, History } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { SignedIn } from "@/components/SiteHeader";
import { useApi } from "@/lib/useApi";
import { dateTime, monthYear } from "@/lib/format";
import type { CoverageState, GapMap, GapRow } from "@/lib/types";

/** Each state has a word and an icon, so the grid never depends on colour alone. */
const STATE: Record<CoverageState, { short: string; long: string; Icon: typeof CircleCheck }> = {
  covered: { short: "Covered", long: "Recent Tier A or B survey evidence", Icon: CircleCheck },
  covered_stale: { short: "Old", long: "Tier A or B survey evidence, but the fieldwork is old", Icon: History },
  partial: { short: "Partial", long: "Only qualitative or Tier C evidence", Icon: CircleDashed },
  gap: { short: "Gap", long: "No approved study speaks for this place", Icon: CirclePlus },
};
const ORDER: CoverageState[] = ["covered", "covered_stale", "partial", "gap"];

function Cell({ state, area, topic }: { state: CoverageState; area: string; topic: string }) {
  const { short, long, Icon } = STATE[state];
  return (
    <span className={`gap-cell gap-${state}`} title={`${topic}, ${area}: ${long}`}>
      <Icon size={14} strokeWidth={2} aria-hidden />
      {short}
    </span>
  );
}

/** Topics teams ask about that are still weak somewhere: where new research would be used first. */
function CommissionNext({ rows, columns }: { rows: GapRow[]; columns: string[] }) {
  const picks = rows.filter((r) => r.attention).slice(0, 3);
  if (!picks.length) return null;
  return (
    <section className="gap-next" aria-labelledby="next-title">
      <h2 id="next-title">Where new research would be used first</h2>
      <ol>
        {picks.map((r) => {
          const weak = columns.filter((c) => r.cells[c] !== "covered");
          return (
            <li key={r.family}>
              <strong>{r.label}</strong>
              <span className="nums">
                {r.asked} {r.asked === 1 ? "brief" : "briefs"} cited it
                {r.unanswered > 0 && <>, {r.unanswered} unanswered {r.unanswered === 1 ? "question is" : "questions are"} closest to it</>}
                {r.teams.length > 0 && <> · asked by {r.teams.join(", ")}</>}
              </span>
              <span className="muted">
                {r.best === "covered" ? "Covered somewhere, but not for " : "Not well covered anywhere: "}
                {weak.join(", ") || "every place"}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Gaps() {
  const { data, error, reload } = useApi<GapMap>("/api/gaps?days=90");
  return (
    <>
      <section className="page-head">
        <title>Gap map · ALAMKansya</title>
        <h1>Gap map</h1>
        <p>
          What approved research covers, for which places, and what business teams ask about. Coverage is decided in code
          by the same rule as a <Link href="/commission">commissioning check</Link>; demand counts the briefs of the last 90 days.
        </p>
      </section>
      {error && <LoadError message={error} onRetry={reload} />}
      {!data ? (
        !error && <p className="loading" role="status">Loading the map…</p>
      ) : (
        <>
          <CommissionNext rows={data.rows} columns={data.columns} />
          <ul className="gap-key" aria-label="What the cells mean">
            {ORDER.map((s) => (
              <li key={s}><Cell state={s} area="key" topic="Key" /> {STATE[s].long}</li>
            ))}
          </ul>
          <div className="table-wrap gap-table">
            <table>
              <caption className="visually-hidden">Coverage by topic and place, with how often each topic was asked about</caption>
              <thead>
                <tr>
                  <th scope="col">Topic</th>
                  {data.columns.map((c) => <th scope="col" key={c}>{c}</th>)}
                  <th scope="col" className="num">Asked</th>
                  <th scope="col" className="num">Unanswered</th>
                  <th scope="col">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.family} className={r.attention ? "attention" : undefined}>
                    <th scope="row">
                      {r.label}
                      {r.attention && <span className="sub flag-text">Asked about and still weak</span>}
                    </th>
                    {data.columns.map((c) => (
                      <td key={c}><Cell state={r.cells[c]} area={c} topic={r.label} /></td>
                    ))}
                    <td className="num nums">{r.asked || <span className="muted">0</span>}</td>
                    <td className="num nums">{r.unanswered ? <strong className="flag-text">{r.unanswered}</strong> : <span className="muted">0</span>}</td>
                    <td className="small">
                      {r.studies.length} {r.studies.length === 1 ? "study" : "studies"}
                      {r.newest_fieldwork && <span className="sub">newest {monthYear(r.newest_fieldwork)}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Built from the {data.studies_read} approved studies S&amp;I can read. A place counts when a study or subgroup speaks
            for it; a study across Metro Manila and the provinces counts for both.
          </p>

          <section className="section" aria-labelledby="unanswered-title">
            <div className="section-head"><h2 id="unanswered-title">Questions no readable study answered</h2></div>
            <p className="section-intro">
              Each is counted on the topic it is closest to in meaning (the &ldquo;Unanswered&rdquo; column). When S&amp;I
              approves a study that answers one, the person who asked is told.
            </p>
            {data.unanswered.length === 0 ? (
              <p className="empty">Every question in the last {data.days} days found evidence.</p>
            ) : (
              <ul className="stack">
                {data.unanswered.map((u) => (
                  <li key={u.question + u.team}>
                    <div className="item-head">
                      <span className="item-title">{u.question}</span>
                      <span className="muted small nums">{u.times > 1 ? `${u.times}× · ` : ""}{dateTime(u.last_asked)}</span>
                    </div>
                    <p className="item-meta">
                      {u.team}
                      {u.topic && <> · closest topic: <strong>{u.topic}</strong></>}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn siOnly>
      <Gaps />
    </SignedIn>
  );
}
