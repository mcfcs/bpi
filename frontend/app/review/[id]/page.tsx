"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CiteChip, TierBadge } from "@/components/Citation";
import { CiteLink, OpenReportButton } from "@/components/ReportLink";
import { SignedIn } from "@/components/SiteHeader";
import { TierScore } from "@/components/TierScore";
import { api, ApiError } from "@/lib/api";
import type { FindingRow, StudyDetail, Tier } from "@/lib/types";
import { monthYear, n, stateLabel } from "@/lib/format";

type Status = { kind: "ok" | "error"; text: string } | null;

function errorText(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback;
}

function StudyCard({ study, onSaved }: { study: StudyDetail; onSaved: (s: StudyDetail) => void }) {
  const pop = study.population ?? { age_min: null, age_max: null, regions: [], segment: null };
  const [form, setForm] = useState({
    title: study.title,
    summary: study.summary ?? "",
    method_type: study.method_type ?? "",
    sample_size: study.sample_size?.toString() ?? "",
    fieldwork_end: study.fieldwork_end ?? "",
    age_min: pop.age_min?.toString() ?? "",
    age_max: pop.age_max?.toString() ?? "",
    regions: pop.regions.join(", "),
    segment: pop.segment ?? "",
    access_level: study.access_level,
  });
  const [status, setStatus] = useState<Status>(null);
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setStatus(null);
    try {
      const updated = await api<StudyDetail>(`/api/review/studies/${study.id}`, {
        method: "PATCH",
        json: {
          title: form.title,
          summary: form.summary,
          method_type: form.method_type || null,
          sample_size: form.sample_size ? Number(form.sample_size) : null,
          fieldwork_end: form.fieldwork_end || null,
          access_level: form.access_level,
          population: {
            age_min: form.age_min ? Number(form.age_min) : null,
            age_max: form.age_max ? Number(form.age_max) : null,
            regions: form.regions.split(",").map((r) => r.trim()).filter(Boolean),
            segment: form.segment || null,
          },
        },
      });
      onSaved(updated);
      setStatus({ kind: "ok", text: `Saved. Computed tier: ${updated.robustness_tier ?? "not yet"}.` });
    } catch (e) {
      setStatus({ kind: "error", text: errorText(e, "Could not save.") });
    }
  }

  return (
    <form onSubmit={save} className="panel">
      <h2>Study card</h2>
      <div className="field">
        <label htmlFor="title">Title</label>
        <input id="title" value={form.title} onChange={set("title")} />
      </div>
      <div className="field">
        <label htmlFor="summary">Summary</label>
        <textarea id="summary" rows={3} value={form.summary} onChange={set("summary")} />
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor="method">Method</label>
          <select id="method" value={form.method_type} onChange={set("method_type")}>
            <option value="">Not set</option>
            <option value="quant">Quantitative</option>
            <option value="qual">Qualitative</option>
            <option value="mixed">Mixed</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="n">Sample size</label>
          <input id="n" type="number" min={1} value={form.sample_size} onChange={set("sample_size")} />
          <p className="hint">Respondents; for qualitative work, participants.</p>
        </div>
        <div className="field">
          <label htmlFor="fieldwork">Fieldwork ended</label>
          <input id="fieldwork" type="date" value={form.fieldwork_end} onChange={set("fieldwork_end")} />
        </div>
      </div>
      <div className="field-row pairs">
        <div className="field">
          <label htmlFor="age-min">Youngest age</label>
          <input id="age-min" type="number" value={form.age_min} onChange={set("age_min")} />
        </div>
        <div className="field">
          <label htmlFor="age-max">Oldest age</label>
          <input id="age-max" type="number" value={form.age_max} onChange={set("age_max")} />
        </div>
        <div className="field">
          <label htmlFor="regions">Regions</label>
          <input id="regions" value={form.regions} onChange={set("regions")} placeholder="NCR, Cebu, Nationwide" />
        </div>
        <div className="field">
          <label htmlFor="segment">Segment</label>
          <input id="segment" value={form.segment} onChange={set("segment")} />
        </div>
      </div>
      <div className="field" style={{ maxWidth: 360 }}>
        <label htmlFor="access-level">Access</label>
        <select id="access-level" value={form.access_level} onChange={set("access_level")}>
          <option value="restricted">Restricted to {study.owner_team}</option>
          <option value="open">Open to all teams</option>
        </select>
      </div>
      {status && <p role={status.kind === "error" ? "alert" : "status"} className={status.kind === "error" ? "error" : "muted"}>{status.text}</p>}
      <button className="btn btn-primary">Save study card</button>
    </form>
  );
}

function TierPanel({ study, onSaved }: { study: StudyDetail; onSaved: (s: StudyDetail) => void }) {
  const [override, setOverride] = useState<Tier | "">(study.tier_override ?? "");
  const [reason, setReason] = useState(study.tier_override_reason ?? "");
  const [status, setStatus] = useState<Status>(null);
  const b = study.tier_breakdown;

  async function save(clear: boolean) {
    setStatus(null);
    try {
      const updated = await api<StudyDetail>(`/api/review/studies/${study.id}`, {
        method: "PATCH",
        json: clear ? { clear_tier_override: true } : { tier_override: override, tier_override_reason: reason },
      });
      onSaved(updated);
      setOverride(updated.tier_override ?? "");
      setReason(updated.tier_override_reason ?? "");
      setStatus({ kind: "ok", text: clear ? "Override removed. Logged to the audit trail." : "Override saved. Logged to the audit trail." });
    } catch (e) {
      setStatus({ kind: "error", text: errorText(e, "Could not save the override.") });
    }
  }

  return (
    <div className="panel">
      <h2>Robustness tier</h2>
      <p>
        Effective tier{" "}
        {study.effective_tier ? (
          <TierBadge tier={study.effective_tier} sample={`n=${n(study.sample_size)}`} when={study.fieldwork_end?.slice(0, 4) ?? "n.d."} />
        ) : (
          <span className="muted">not computed until method and fieldwork end are set</span>
        )}
        {study.tier_override && <span className="muted small"> (computed {study.robustness_tier}, overridden)</span>}
      </p>
      {b && <TierScore breakdown={b} />}
      <p className="hint" style={{ marginBottom: 14 }}>
        Points and cut-offs are proposed defaults, not yet validated by S&amp;I. Recency is re-checked nightly.
      </p>
      <div className="field-row">
        <div className="field">
          <label htmlFor="override">Override</label>
          <select id="override" value={override} onChange={(e) => setOverride(e.target.value as Tier | "")}>
            <option value="">No override</option>
            <option value="A">A</option>
            <option value="B">B</option>
            <option value="C">C</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="reason">Reason (required for an override)</label>
        <textarea id="reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      {status && <p role={status.kind === "error" ? "alert" : "status"} className={status.kind === "error" ? "error" : "muted"}>{status.text}</p>}
      <div className="actions">
        <button className="btn btn-primary" type="button" disabled={!override || !reason.trim()} onClick={() => save(false)}>
          Save override
        </button>
        {study.tier_override && (
          <button className="btn" type="button" onClick={() => save(true)}>Remove override</button>
        )}
      </div>
    </div>
  );
}

function FindingEditor({ finding, studyId, hasDocument }: { finding: FindingRow; studyId: string; hasDocument: boolean }) {
  const [f, setF] = useState(finding);
  const [status, setStatus] = useState<Status>(null);
  const sub = f.subgroup ?? {};
  const update = (patch: Partial<FindingRow>) => setF((cur) => ({ ...cur, ...patch }));

  async function save() {
    setStatus(null);
    try {
      const subgroup = Object.fromEntries(Object.entries(f.subgroup ?? {}).filter(([, v]) => v));
      const saved = await api<FindingRow>(`/api/review/findings/${finding.id}`, {
        method: "PATCH",
        json: {
          text: f.text,
          theme: f.theme || null,
          finding_type: f.finding_type,
          metric_key: f.metric_key || null,
          value: f.finding_type === "quant_stat" && f.value !== null ? Number(f.value) : null,
          unit: f.unit || null,
          base_n: f.base_n ? Number(f.base_n) : null,
          subgroup: Object.keys(subgroup).length ? subgroup : null,
          direction: f.direction || null,
        },
      });
      setF(saved);
      setStatus({ kind: "ok", text: "Saved." });
    } catch (e) {
      setStatus({ kind: "error", text: errorText(e, "Could not save.") });
    }
  }

  return (
    <li>
      <div className="field">
        <div className="finding-head">
          <label htmlFor={`text-${f.id}`}>Finding {f.ordinal + 1}</label>
          {hasDocument ? (
            <CiteLink studyId={studyId} code={null} page={f.page ?? null} />
          ) : (
            f.page != null && <span className="muted small">p.{f.page}</span>
          )}
          {hasDocument && f.page == null && <span className="muted small">Page not found in the PDF</span>}
        </div>
        <textarea id={`text-${f.id}`} rows={2} value={f.text} onChange={(e) => update({ text: e.target.value })} />
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor={`type-${f.id}`}>Type</label>
          <select id={`type-${f.id}`} value={f.finding_type ?? ""} onChange={(e) => update({ finding_type: (e.target.value || null) as FindingRow["finding_type"] })}>
            <option value="">Not set</option>
            <option value="quant_stat">Quant statistic</option>
            <option value="qual_theme">Qualitative theme</option>
            <option value="verbatim">Verbatim</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`metric-key-${f.id}`}>Metric key</label>
          <input id={`metric-key-${f.id}`} value={f.metric_key ?? ""} onChange={(e) => update({ metric_key: e.target.value })} placeholder="barrier:fees" />
        </div>
        <div className="field">
          <label htmlFor={`direction-${f.id}`}>Direction</label>
          <select id={`direction-${f.id}`} value={f.direction ?? ""} onChange={(e) => update({ direction: (e.target.value || null) as FindingRow["direction"] })}>
            <option value="">Not set</option>
            <option value="high">High: prominent</option>
            <option value="low">Low: not prominent</option>
            <option value="neutral">Neutral</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`theme-${f.id}`}>Theme</label>
          <input id={`theme-${f.id}`} value={f.theme ?? ""} onChange={(e) => update({ theme: e.target.value })} />
        </div>
      </div>
      {f.finding_type === "quant_stat" && (
        <div className="field-row">
          <div className="field">
            <label htmlFor={`value-${f.id}`}>Value</label>
            <input id={`value-${f.id}`} type="number" step="any" value={f.value ?? ""} onChange={(e) => update({ value: e.target.value === "" ? null : Number(e.target.value) })} />
          </div>
          <div className="field">
            <label htmlFor={`unit-${f.id}`}>Unit</label>
            <select id={`unit-${f.id}`} value={f.unit ?? ""} onChange={(e) => update({ unit: (e.target.value || null) as FindingRow["unit"] })}>
              <option value="">Not set</option>
              <option value="%">%</option>
              <option value="rank">rank</option>
              <option value="score">score</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`base-n-${f.id}`}>Base n</label>
            <input id={`base-n-${f.id}`} type="number" min={1} value={f.base_n ?? ""} onChange={(e) => update({ base_n: e.target.value === "" ? null : Number(e.target.value) })} />
          </div>
        </div>
      )}
      <div className="field-row">
        <div className="field">
          <label htmlFor={`subgroup-age-band-${f.id}`}>Subgroup: age band</label>
          <input id={`subgroup-age-band-${f.id}`} value={sub.age_band ?? ""} onChange={(e) => update({ subgroup: { ...sub, age_band: e.target.value } })} placeholder="20-29" />
        </div>
        <div className="field">
          <label htmlFor={`subgroup-region-${f.id}`}>Subgroup: region</label>
          <input id={`subgroup-region-${f.id}`} value={sub.region ?? ""} onChange={(e) => update({ subgroup: { ...sub, region: e.target.value } })} />
        </div>
        <div className="field">
          <label htmlFor={`subgroup-segment-${f.id}`}>Subgroup: segment</label>
          <input id={`subgroup-segment-${f.id}`} value={sub.segment ?? ""} onChange={(e) => update({ subgroup: { ...sub, segment: e.target.value } })} />
        </div>
      </div>
      <div className="actions">
        <button type="button" className="btn" onClick={save}>Save finding</button>
        {status && <span role={status.kind === "error" ? "alert" : "status"} className={status.kind === "error" ? "error" : "muted small"}>{status.text}</span>}
      </div>
    </li>
  );
}

/** The flagged part of a finding, marked so the analyst sees exactly what matched. */
function Marked({ text, matches }: { text: string; matches: { start: number; end: number; label: string }[] }) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const m of matches) {
    if (m.start < at) continue;
    parts.push(text.slice(at, m.start));
    parts.push(<mark key={m.start} title={m.label}>{text.slice(m.start, m.end)}</mark>);
    at = m.end;
  }
  parts.push(text.slice(at));
  return <>{parts}</>;
}

/**
 * Checkpoint 1 aids: personal data in findings (pattern rules) and approved studies this one
 * overlaps (meaning plus code). Both inform the analyst; neither decides.
 */
function ReviewChecks({ study, onRecheck }: { study: StudyDetail; onRecheck: () => void }) {
  const flags = study.privacy?.findings ?? [];
  const overlaps = study.overlaps ?? [];
  if (!study.privacy && !study.overlaps) return null;
  return (
    <section className="checks-before" aria-labelledby="checks-title">
      <h2 id="checks-title">Checks before you approve</h2>
      <div className="check-grid">
        <div className={`check-card${flags.length ? " warn" : " ok"}`}>
          <h3>{flags.length ? `Personal data: ${flags.length} ${flags.length === 1 ? "finding" : "findings"} to check` : "Personal data: none found"}</h3>
          {flags.length ? (
            <>
              <p className="hint">Readers would see these. Edit the finding below, or confirm they identify no one when you approve.</p>
              <ul>
                {flags.map((f) => (
                  <li key={f.finding_id}>
                    <span className="flag-kinds">{[...new Set(f.matches.map((m) => m.label))].join(", ")}</span>
                    <q><Marked text={f.text} matches={f.matches} /></q>
                  </li>
                ))}
              </ul>
              <button type="button" className="btn btn-quiet" onClick={onRecheck}>Check again after editing</button>
            </>
          ) : (
            <p className="hint">No phone numbers, emails, account numbers, tax IDs, addresses or names matched in the findings.</p>
          )}
          {study.privacy && study.privacy.source_matches > 0 && (
            <p className="hint">The original report text has {study.privacy.source_matches} more {study.privacy.source_matches === 1 ? "match" : "matches"}; only S&amp;I sees that text.</p>
          )}
        </div>
        <div className="check-card">
          <h3>{overlaps.length ? `Overlaps ${overlaps.length} approved ${overlaps.length === 1 ? "study" : "studies"}` : "No overlap with approved studies"}</h3>
          {overlaps.length ? (
            <ul className="overlaps">
              {overlaps.map((o) => (
                <li key={o.study_id}>
                  <p className={`overlap-verdict v-${o.verdict}`}>{o.verdict_text}</p>
                  <p>
                    <CiteChip code={o.code} /> <Link href={`/studies/${o.study_id}`}>{o.title}</Link>
                  </p>
                  <p className="hint">
                    {[o.owner_team, o.place, o.fieldwork_end ? `fieldwork ${monthYear(o.fieldwork_end)}` : "", o.topics.join(", ")]
                      .filter(Boolean).join(" · ")}
                    {o.differs_by.length > 0 && <> · differs by {o.differs_by.join(", ")}</>}
                  </p>
                  {o.figures.length > 0 && (
                    <ul className="overlap-figures">
                      {o.figures.map((f) => (
                        <li key={f.metric}>{f.metric}: <strong className="nums">{f.new}</strong> here, <strong className="nums">{f.old}</strong> in {o.code}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nothing approved covers the same topics closely. This may be new research.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function Review({ id }: { id: string }) {
  const [study, setStudy] = useState<StudyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<Status>(null);
  const [deciding, setDeciding] = useState(false);
  const [privacyChecked, setPrivacyChecked] = useState(false);

  const load = useCallback(() => {
    api<StudyDetail>(`/api/studies/${id}`).then(setStudy).catch((e) => setError(errorText(e, "Could not load the study.")));
  }, [id]);
  useEffect(load, [load]);

  async function decide(approve: boolean) {
    setDecision(null);
    setDeciding(true);
    try {
      const updated = await api<StudyDetail & { answer_alerts?: number }>(`/api/review/studies/${id}/decision`, { method: "POST", json: { approve, note: note || null, privacy_checked: privacyChecked } });
      setStudy(updated);
      // Earlier questions this study now answers were searched again as their askers.
      const alerted = updated.answer_alerts ?? 0;
      const alertText = alerted
        ? ` It answers ${alerted} earlier ${alerted === 1 ? "question" : "questions"} nobody could answer before; ${alerted === 1 ? "that person has" : "those people have"} been told.`
        : "";
      setDecision({ kind: "ok", text: approve ? `Approved. The study is now searchable for teams that may read it.${alertText}` : "Rejected." });
    } catch (e) {
      setDecision({ kind: "error", text: errorText(e, "Could not record the decision.") });
    } finally {
      setDeciding(false);
    }
  }

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!study) return <p className="loading" role="status">Loading…</p>;

  return (
    <>
      <section className="page-head">
        <p className="crumbs">
          <Link href="/review">Review queue</Link>
          <CiteChip code={study.code} />
          <span className={study.review_status === "approved" ? "status status-ok" : study.review_status === "rejected" ? "status status-bad" : "status status-wait"}>
            {stateLabel(study.review_status)}
          </span>
        </p>
        <title>{`Review: ${study.title} · ALAMKansya`}</title>
        <h1>{study.title}</h1>
        <p>
          {study.owner_team} · {study.access_level} · fieldwork ended {monthYear(study.fieldwork_end)} · source{" "}
          {study.source_name ?? "not recorded"}
        </p>
        {study.document && (
          <div className="actions study-actions">
            <OpenReportButton studyId={study.id} label="Open report" />
            <span className="muted small nums">
              {study.document.filename}{study.document.page_count ? `, ${study.document.page_count} pages` : ""}
            </span>
          </div>
        )}
      </section>

      <ReviewChecks study={study} onRecheck={load} />

      <div className="two-col">
        <StudyCard key={`card-${study.id}`} study={study} onSaved={setStudy} />
        <div>
          <TierPanel key={`tier-${study.id}`} study={study} onSaved={setStudy} />
          <div className="panel">
            <h2>Decision</h2>
            <div className="field">
              <label htmlFor="note">Note (optional)</label>
              <textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            {(study.privacy?.findings.length ?? 0) > 0 && study.review_status === "pending_review" && (
              <div className="confirm-check">
                <input id="privacy-checked" type="checkbox" checked={privacyChecked} onChange={(e) => setPrivacyChecked(e.target.checked)} />
                <label htmlFor="privacy-checked">I checked the flagged findings and they identify no one</label>
              </div>
            )}
            {decision && <p role={decision.kind === "error" ? "alert" : "status"} className={decision.kind === "error" ? "error" : "muted"}>{decision.text}</p>}
            <div className="actions">
              <button className="btn btn-primary" onClick={() => decide(true)} disabled={deciding || study.review_status === "approved"}>
                Approve
              </button>
              <button className="btn" onClick={() => decide(false)} disabled={deciding || study.review_status === "rejected"}>
                Reject
              </button>
            </div>
          </div>
        </div>
      </div>

      <section className="section" style={{ marginTop: 32 }}>
        <div className="section-head">
          <h2>Findings</h2>
          <span className="tag">{study.findings.length} extracted · check type, metric, direction and base n</span>
        </div>
        <ul className="findings">
          {study.findings.map((f) => (
            <FindingEditor key={f.id} finding={f} studyId={study.id} hasDocument={Boolean(study.document)} />
          ))}
        </ul>
      </section>

      {study.source_text && (
        <details style={{ marginTop: 24 }}>
          <summary>Original report text</summary>
          <pre className="source-text">{study.source_text}</pre>
        </details>
      )}
    </>
  );
}

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return (
    <SignedIn siOnly>
      <Review id={id} />
    </SignedIn>
  );
}
