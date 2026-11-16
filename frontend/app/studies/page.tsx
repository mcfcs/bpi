"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Lock } from "lucide-react";
import { Suspense, useDeferredValue, useMemo, useState } from "react";
import { CiteChip, TierBadge } from "@/components/Citation";
import { LoadError } from "@/components/LoadError";
import { OpenReportButton } from "@/components/ReportLink";
import { RequestAccess } from "@/components/RequestAccess";
import { useSession } from "@/components/Session";
import { SignedIn } from "@/components/SiteHeader";
import { useApi } from "@/lib/useApi";
import type { MethodType, Provenance, ReadableStudy, RestrictedStudy, StudyListItem } from "@/lib/types";
import { METHOD_LABELS, methodSample, monthYear, PROVENANCE_LABELS, provenanceLabel } from "@/lib/format";

type FilterKey = "q" | "method" | "team" | "year" | "provenance";

const PROVENANCE_FILTER_LABELS: Record<Provenance, string> = {
  synthetic: "Synthetic S&I studies",
  public: "Public sources",
  internal: "Internal reports",
};

type FilterState = Record<FilterKey, string>;
const NO_FILTERS: FilterState = { q: "", method: "", team: "", year: "", provenance: "" };

/**
 * Filters are read from the address bar once and mirrored back to it on every change, so a filtered
 * list survives opening a study and coming back, and can be shared. State stays local so typing in
 * the search box never waits on the router.
 */
function useFilters() {
  const params = useSearchParams();
  const [state, setState] = useState<FilterState>(() => {
    const initial = { ...NO_FILTERS };
    for (const key of Object.keys(NO_FILTERS) as FilterKey[]) initial[key] = params.get(key) ?? "";
    return initial;
  });
  function write(next: FilterState) {
    setState(next);
    const qs = new URLSearchParams(Object.entries(next).filter(([, v]) => v)).toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }
  return {
    values: state,
    set: (key: FilterKey, value: string) => write({ ...state, [key]: value }),
    clear: () => write(NO_FILTERS),
    active: Object.values(state).some(Boolean),
  };
}

function matches(study: StudyListItem, f: { method: string; team: string; year: string; provenance: string }, query: string) {
  if (f.method && study.method_type !== f.method) return false;
  if (f.team && study.owner_team !== f.team) return false;
  if (f.year && String(study.year ?? "") !== f.year) return false;
  if (f.provenance && study.provenance !== f.provenance) return false;
  if (query) {
    const hay = `${study.code} ${study.title}`.toLowerCase();
    return query.split(/\s+/).every((word) => hay.includes(word));
  }
  return true;
}

function ReadableRow({ study }: { study: ReadableStudy }) {
  const meta = [study.owner_team, methodSample(study), `fieldwork ${monthYear(study.fieldwork_end)}`, provenanceLabel(study)];
  return (
    <li>
      <span className="code"><CiteChip code={study.code} /></span>
      <div className="body">
        <Link className="study-title" href={`/studies/${study.id}`}>{study.title}</Link>
        <p className="study-meta">{meta.filter(Boolean).join(" · ")}</p>
      </div>
      <span className="tier-cell">
        <TierBadge tier={study.effective_tier} />
      </span>
      <span className="act">
        {study.document ? (
          <OpenReportButton studyId={study.id} label="Open report" className="btn btn-quiet" />
        ) : (
          <span className="muted small">No report file</span>
        )}
      </span>
    </li>
  );
}

function RestrictedRow({ study }: { study: RestrictedStudy }) {
  const method = study.method_type ? METHOD_LABELS[study.method_type] : "";
  const meta = [`Owned by ${study.owner_team}`, method, study.year ? String(study.year) : "", provenanceLabel(study)];
  return (
    <RequestAccess.Provider studyId={study.id} ownerTeam={study.owner_team} initialStatus={study.request_status}>
      <li className="locked-row">
        <span className="code"><CiteChip code={study.code} /></span>
        <div className="body">
          <span className="study-title">{study.title}</span>
          <p className="study-meta">{meta.filter(Boolean).join(" · ")}</p>
        </div>
        <span className="tier-cell locked">
          <Lock size={14} strokeWidth={1.75} aria-hidden />
          Restricted
        </span>
        <span className="act">
          <RequestAccess.Action approved="Approved: reload to read it" />
        </span>
        <RequestAccess.Form className="request-form" />
      </li>
    </RequestAccess.Provider>
  );
}

function Select({ id, label, value, onChange, all, options }: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  all: string;
  options: [string, string][];
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map(([v, text]) => (
          <option key={v} value={v}>{text}</option>
        ))}
      </select>
    </div>
  );
}

function Catalogue() {
  const { profile } = useSession();
  const { data: studies, error, reload } = useApi<StudyListItem[]>("/api/studies", profile?.id);
  const filters = useFilters();
  const f = filters.values;
  const search = f.q;
  // Typing stays instant; the list catches up a moment later on slow devices.
  const query = useDeferredValue(search.trim().toLowerCase());

  const options = useMemo(() => {
    const list = studies ?? [];
    const teams = [...new Set(list.map((s) => s.owner_team))].sort();
    const years = [...new Set(list.map((s) => s.year).filter((y): y is number => y != null))].sort((a, b) => b - a);
    const methods = (Object.keys(METHOD_LABELS) as MethodType[]).filter((m) => list.some((s) => s.method_type === m));
    const provenances = (Object.keys(PROVENANCE_LABELS) as Provenance[]).filter((p) => list.some((s) => s.provenance === p));
    return { teams, years, methods, provenances };
  }, [studies]);

  const shown = (studies ?? []).filter((s) => matches(s, f, query));
  const total = studies?.length ?? 0;
  const restricted = shown.filter((s) => !s.can_read).length;

  return (
    <>
      <section className="page-head">
        <title>Studies · ALAMKansya</title>
        <h1>Studies</h1>
        <p>
          Every approved study, including the ones {profile?.team_name ?? "your team"} cannot read yet. Open a report at the
          page a finding came from, or ask the owning team for access to a restricted study.
        </p>
      </section>

      <form className="filters" role="search" aria-label="Filter studies" onSubmit={(e) => e.preventDefault()}>
        <div className="field search">
          <label htmlFor="study-search">Search titles and codes</label>
          <input
            id="study-search"
            type="search"
            value={search}
            onChange={(e) => filters.set("q", e.target.value)}
            placeholder="For example: loan, QR, SI-2026"
            autoComplete="off"
          />
        </div>
        <Select id="f-method" label="Method" value={f.method} onChange={(v) => filters.set("method", v)} all="All methods"
          options={options.methods.map((m) => [m, METHOD_LABELS[m]])} />
        <Select id="f-team" label="Owner" value={f.team} onChange={(v) => filters.set("team", v)} all="All teams"
          options={options.teams.map((t) => [t, t])} />
        <Select id="f-year" label="Year" value={f.year} onChange={(v) => filters.set("year", v)} all="All years"
          options={options.years.map((y) => [String(y), String(y)])} />
        <Select id="f-provenance" label="Source" value={f.provenance} onChange={(v) => filters.set("provenance", v)} all="All sources"
          options={options.provenances.map((p) => [p, PROVENANCE_FILTER_LABELS[p]])} />
      </form>

      {error && <LoadError message={error} onRetry={reload} />}
      {studies === null ? (
        !error && <p className="loading" role="status">Loading…</p>
      ) : (
        <>
          <div className="catalogue-count">
            <p className="muted small nums" role="status" aria-live="polite">
              {shown.length === total ? `${total} studies` : `${shown.length} of ${total} studies`}
              {restricted > 0 && `, ${restricted} restricted`}
            </p>
            {filters.active && (
              <button type="button" className="btn btn-quiet small" onClick={filters.clear}>Clear filters</button>
            )}
          </div>
          {shown.length === 0 ? (
            <p className="empty">No study matches these filters. Try fewer words, or clear the filters.</p>
          ) : (
            <ul className="catalogue">
              {shown.map((s) => (s.can_read ? <ReadableRow key={s.id} study={s} /> : <RestrictedRow key={s.id} study={s} />))}
            </ul>
          )}
        </>
      )}
    </>
  );
}

export default function Page() {
  return (
    <SignedIn>
      <Suspense fallback={<p className="loading" role="status">Loading…</p>}>
        <Catalogue />
      </Suspense>
    </SignedIn>
  );
}
