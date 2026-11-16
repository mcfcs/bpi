"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { CiteChip, TierBadge } from "@/components/Citation";
import { LoadError } from "@/components/LoadError";
import { CiteLink, OpenReportButton } from "@/components/ReportLink";
import { useSession } from "@/components/Session";
import { SignedIn } from "@/components/SiteHeader";
import { TierScore } from "@/components/TierScore";
import { useApi } from "@/lib/useApi";
import type { FindingRow, StudyDetail } from "@/lib/types";
import { methodSample, monthYear, n, populationLabel, provenanceLabel } from "@/lib/format";

const FINDING_TYPES = { quant_stat: "Survey figure", qual_theme: "Theme", verbatim: "Quote" } as const;

/** Findings in report order, grouped by the page they were read from; unplaced ones last. */
function byPage(findings: FindingRow[]): [number | null, FindingRow[]][] {
  const groups = new Map<number | null, FindingRow[]>();
  for (const f of [...findings].sort((a, b) => a.ordinal - b.ordinal)) {
    const page = f.page ?? null;
    groups.set(page, [...(groups.get(page) ?? []), f]);
  }
  return [...groups.entries()].sort(([a], [b]) => (a ?? Infinity) - (b ?? Infinity));
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function StudyFacts({ study }: { study: StudyDetail }) {
  const regions = study.population?.regions ?? [];
  const doc = study.document;
  return (
    <section className="side-panel" aria-labelledby="card-title">
      <h2 id="card-title">Study card</h2>
      <dl className="facts">
        <Fact term="Method and sample">{methodSample(study)}</Fact>
        <Fact term="Who was asked">{populationLabel(study.population)}</Fact>
        <Fact term="Regions">{regions.length ? regions.join(", ") : "not stated"}</Fact>
        <Fact term="Fieldwork ended">{monthYear(study.fieldwork_end)}</Fact>
        <Fact term="Robustness tier">
          {study.effective_tier ? (
            <>
              <TierBadge tier={study.effective_tier} />
              {study.tier_override && <span className="muted small"> set by S&amp;I (computed {study.robustness_tier ?? "not set"})</span>}
            </>
          ) : (
            <span className="muted">not computed</span>
          )}
          {study.tier_breakdown && <TierScore breakdown={study.tier_breakdown} />}
          {study.tier_override_reason && <p className="hint">{study.tier_override_reason}</p>}
        </Fact>
        <Fact term="Owner">{study.owner_team} · {study.access_level === "open" ? "open to all teams" : "restricted"}</Fact>
        <Fact term="Source">{provenanceLabel(study) || "not recorded"}</Fact>
        {doc?.license && <Fact term="Licence">{doc.license}</Fact>}
        {doc?.source_url && (
          <Fact term="Original">
            <a href={doc.source_url} target="_blank" rel="noreferrer" className="break">
              {hostOf(doc.source_url)}
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          </Fact>
        )}
      </dl>
    </section>
  );
}

function Finding({ finding }: { finding: FindingRow }) {
  const sub = Object.values(finding.subgroup ?? {}).filter(Boolean).join(", ");
  const details = [
    finding.finding_type ? FINDING_TYPES[finding.finding_type] : "",
    finding.base_n != null ? `base n=${n(finding.base_n)}` : "",
    sub,
  ].filter(Boolean);
  return (
    <li>
      <p className={finding.finding_type === "verbatim" ? "finding-text quote" : "finding-text"}>
        {finding.finding_type === "verbatim" ? `“${finding.text}”` : finding.text}
      </p>
      {details.length > 0 && <p className="study-meta">{details.join(" · ")}</p>}
      {finding.source_excerpt && (
        <blockquote className="excerpt">
          <span className="visually-hidden">Wording in the report: </span>“{finding.source_excerpt}”
        </blockquote>
      )}
    </li>
  );
}

function Study({ id }: { id: string }) {
  const { profile } = useSession();
  const { data: study, error, loading, reload } = useApi<StudyDetail>(`/api/studies/${encodeURIComponent(id)}`, profile?.id);

  if (error && !study) {
    const missing = /not found|access/i.test(error);
    return missing ? (
      <section className="page-head">
        <title>Study not available · ALAMKansya</title>
        <p className="crumbs"><Link href="/studies">Studies</Link></p>
        <h1>This study is not available to you</h1>
        <p>
          It does not exist, or {profile?.team_name ?? "your team"} cannot read it yet. Restricted studies are listed on
          the Studies page, where you can ask the owning team for access.
        </p>
        <div className="actions" style={{ marginTop: 16 }}>
          <Link href="/studies" className="btn btn-primary">Browse studies</Link>
        </div>
      </section>
    ) : (
      <LoadError message={error} onRetry={reload} />
    );
  }
  if (!study || loading && study.id !== id) return <p className="loading" role="status">Loading…</p>;

  const doc = study.document;
  const groups = byPage(study.findings);
  return (
    <>
      <section className="page-head study-head">
        <title>{`${study.title} · ALAMKansya`}</title>
        <p className="crumbs">
          <Link href="/studies">Studies</Link>
          <CiteChip code={study.code} />
          {study.provenance === "public" && <span className="chip">{provenanceLabel(study)}</span>}
        </p>
        <h1>{study.title}</h1>
        {study.summary && <p>{study.summary}</p>}
        <div className="actions study-actions">
          {doc ? (
            <>
              <OpenReportButton studyId={study.id} label="Open full report" className="btn btn-primary" />
              <span className="muted small nums">
                PDF{doc.page_count ? `, ${doc.page_count} pages` : ""}
              </span>
            </>
          ) : (
            <span className="muted small">No report file is stored for this study.</span>
          )}
        </div>
      </section>

      <div className="split">
        <section aria-labelledby="findings-title">
          <div className="section-head">
            <h2 id="findings-title">Findings</h2>
            <span className="tag">{study.findings.length} approved, by report page</span>
          </div>
          {groups.length === 0 ? (
            <p className="empty">No findings were approved from this study.</p>
          ) : (
            groups.map(([page, findings]) => (
              <div className="page-group" key={page ?? "none"}>
                <div className="page-label">
                  {page == null ? (
                    <span className="muted small">Page not recorded</span>
                  ) : doc ? (
                    <CiteLink studyId={study.id} code={null} page={page} title={study.title} />
                  ) : (
                    <span className="small muted">p.{page}</span>
                  )}
                </div>
                <ul className="page-findings">
                  {findings.map((f) => (
                    <Finding key={f.id} finding={f} />
                  ))}
                </ul>
              </div>
            ))
          )}
        </section>
        <StudyFacts study={study} />
      </div>
    </>
  );
}

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return (
    <SignedIn>
      <Study id={id} />
    </SignedIn>
  );
}
