import type { DiffersBy, MethodType, Provenance, SourceView } from "./types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function monthYear(iso: string | null | undefined): string {
  if (!iso) return "date not stated";
  const [year, month] = iso.slice(0, 10).split("-");
  return `${MONTHS[Number(month) - 1]} ${year}`;
}

export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function n(value: number | null | undefined): string {
  return value == null ? "?" : value.toLocaleString("en-US");
}

export function fmtValue(value: number, unit: string): string {
  const v = Number.isInteger(value) ? String(value) : value.toFixed(1);
  if (unit === "%") return `${v}%`;
  if (unit === "rank") return `rank ${v}`;
  return v;
}

export function year(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 4) : "n.d.";
}

/** "n=1,200" for surveys, "42 participants" for qualitative work. */
export function sampleLabel(source: Pick<SourceView, "method_type" | "sample_size">): string {
  if (source.sample_size == null) return "n not stated";
  return source.method_type === "qual" ? `${n(source.sample_size)} participants` : `n=${n(source.sample_size)}`;
}

export const METHOD_LABELS: Record<MethodType, string> = {
  quant: "Survey",
  qual: "Qualitative",
  mixed: "Mixed method",
};

/** "Survey · n=1,200", "Qualitative · 42 participants": what a study is, in the catalogue's words. */
export function methodSample(study: { method_type: MethodType | null; sample_size?: number | null }): string {
  const method = study.method_type ? METHOD_LABELS[study.method_type] : "Method not stated";
  return study.sample_size == null ? method : `${method} · ${sampleLabel({ method_type: study.method_type, sample_size: study.sample_size })}`;
}

export const PROVENANCE_LABELS: Record<Provenance, string> = {
  synthetic: "Synthetic S&I study",
  public: "Public source",
  internal: "Internal report",
};

/** "Public source · World Bank Group" for published research; the plain label otherwise. */
export function provenanceLabel(study: { provenance?: Provenance | null; publisher?: string | null }): string {
  if (!study.provenance) return "";
  const label = PROVENANCE_LABELS[study.provenance] ?? study.provenance;
  return study.provenance === "public" && study.publisher ? `${label} · ${study.publisher}` : label;
}

/** "SME owners aged 30–60": who a study asked, without the regions (listed on their own). */
export function populationLabel(pop: { age_min: number | null; age_max: number | null; segment: string | null } | null | undefined): string {
  if (!pop) return "not stated";
  const ages = pop.age_min != null && pop.age_max != null ? `aged ${pop.age_min}–${pop.age_max}`
    : pop.age_min != null ? `aged ${pop.age_min} and over`
    : pop.age_max != null ? `aged up to ${pop.age_max}` : "";
  return [pop.segment ?? "", ages].filter(Boolean).join(" ") || "not stated";
}

/** "pending_review" -> "Pending review": a stored state as it reads in a sentence. */
export function stateLabel(state: string): string {
  const s = state.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const DIFFERS_LABELS: Record<DiffersBy, string> = {
  age: "Age",
  region: "Region",
  segment: "Segment",
  period: "Period",
  method: "Method",
};

export const ROLE_LABELS = {
  si_analyst: "S&I analyst",
  bu_approver: "Approver",
  bu_user: "Business unit",
} as const;
