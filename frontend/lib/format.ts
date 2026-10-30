import type { DiffersBy, SourceView } from "./types";

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
