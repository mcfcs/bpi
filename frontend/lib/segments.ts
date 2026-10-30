/**
 * Reads the backend's segment statements back into lines, so the brief can show each population's
 * result on its own line instead of a block of prose (S&I consultation 2: "what it says", for whom,
 * where and when).
 *
 * The backend writes them deterministically (backend/app/describe.py):
 *   context difference  "Fees: a driver of drop-off among X (SI-2026-041, survey of 1,200, Jul 2026: 37%);
 *                        not a driver of drop-off among Y (SI-2025-018, ...: 11%). Each result ..."
 *   within one study    "Long ATM queues: two patterns in the same study, SI-2026-039, which asked Z
 *                        (survey of 1,600, May 2026). A pain point in Metro Manila (57%); not a main
 *                        pain point in Luzon outside NCR (24%) and in Visayas (19%). Each pattern ..."
 *   unresolved conflict "Prefers cashback rewards: SI-2026-027 found 21% (survey of 580, Apr 2026) and
 *                        SI-2026-021 found 54% (...). Both asked ... An S&I analyst is checking ..."
 *
 * Every parser returns null when the text does not have that shape (an LLM may word it differently);
 * callers then show the explanation as written. Nothing here adds or changes a fact.
 */

const CODE = /\b[A-Z]{2,}-\d{4}-\d{2,4}\b/;

/** Split on `sep` only outside parentheses. */
function splitTop(text: string, sep: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "(") depth++;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    else if (depth === 0 && text.startsWith(sep, i)) {
      parts.push(text.slice(start, i));
      start = i + sep.length;
      i += sep.length - 1;
    }
  }
  parts.push(text.slice(start));
  return parts.map((p) => p.trim()).filter(Boolean);
}

/** Sentences, split at a full stop outside parentheses that is followed by a capital letter. */
function sentences(text: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "(") depth++;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    else if (depth === 0 && ch === "." && text[i + 1] === " " && /[A-Z]/.test(text[i + 2] ?? "")) {
      out.push(text.slice(start, i + 1));
      start = i + 2;
    }
  }
  out.push(text.slice(start));
  return out.map((s) => s.trim()).filter(Boolean);
}

/** The first index of any needle outside parentheses, or -1. */
function indexTop(text: string, needles: string[]): number {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "(") depth++;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    else if (depth === 0 && needles.some((n) => text.startsWith(n, i))) return i;
  }
  return -1;
}

const capitalise = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const dropStop = (s: string) => s.replace(/\.\s*$/, "");

/** The text after "Label: ", whatever the label's case; null when there is no label prefix. */
function body(explanation: string, label: string): string {
  const text = explanation.trim();
  if (text.toLowerCase().startsWith(`${label.toLowerCase()}:`)) return text.slice(label.length + 1).trim();
  const colon = indexTop(text, [": "]);
  return colon > 0 && colon < 70 ? text.slice(colon + 2).trim() : text;
}

export interface SegmentLine {
  /** "a driver of drop-off", "improving"; empty when the statement carries none. */
  stance: string;
  /** "Credit card applicants aged 20–40 in Metro Manila", "In Visayas". */
  who: string;
  /** "SI-2026-041, survey of 1,200, Jul 2026" (the study details, without the result). */
  detail: string;
  /** "37%". */
  result: string;
  code: string | null;
}

export interface ParsedSegments {
  /** What came before the lines: for a study pattern, the study and who it asked. */
  intro: string | null;
  lines: SegmentLine[];
  /** A place contrast the statement ends with, e.g. "Metro Manila compared with provincial areas". */
  area: string | null;
  /** What follows the lines: "Each result describes the people that study asked; ...". */
  tail: string | null;
}

/** "who (detail)" items in a list joined by ", " and " and ". */
function groups(text: string): { who: string; detail: string }[] {
  const items: { who: string; detail: string }[] = [];
  let depth = 0;
  let buf = "";
  let inner = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "(") {
      if (depth > 0) inner += ch;
      depth++;
      continue;
    }
    if (ch === ")") {
      depth--;
      if (depth > 0) {
        inner += ch;
        continue;
      }
      items.push({ who: buf.trim(), detail: inner.trim() });
      buf = "";
      inner = "";
      // Skip the separator before the next item.
      const rest = text.slice(i + 1);
      const sep = rest.match(/^(,\s*and\s+|,\s*|\s+and\s+)/);
      if (sep) i += sep[0].length;
      continue;
    }
    if (depth > 0) inner += ch;
    else buf += ch;
  }
  if (buf.trim()) items.push({ who: buf.trim(), detail: "" });
  return items;
}

function splitResult(detail: string): { detail: string; result: string } {
  if (/^[-–\d.,\s]+%?$|^rank\s/i.test(detail)) return { detail: "", result: detail };
  const colon = detail.lastIndexOf(": ");
  if (colon > 0) return { detail: detail.slice(0, colon), result: detail.slice(colon + 2) };
  return { detail, result: "" };
}

/** A context difference or study pattern as lines: who/where/when → result. */
export function parseSegments(explanation: string, label: string): ParsedSegments | null {
  const sents = sentences(body(explanation, label));
  const at = sents.findIndex((s) => splitTop(s, "; ").length >= 2);
  if (at < 0) return null;
  const lines: SegmentLine[] = [];
  let area: string | null = null;
  for (const segment of splitTop(dropStop(sents[at]), "; ")) {
    const cut = indexTop(segment, [" among ", " in "]);
    const stance = cut > 0 ? segment.slice(0, cut).trim() : "";
    const rest = cut > 0 ? segment.slice(cut + 1).trim() : segment;
    for (const g of groups(rest)) {
      if (!g.who) {
        // A parenthesis with nobody before it is the place contrast the statement closes with.
        if (g.detail && !CODE.test(g.detail) && !/\d/.test(g.detail)) area = g.detail;
        continue;
      }
      const { detail, result } = splitResult(g.detail);
      lines.push({
        stance,
        who: capitalise(g.who.replace(/^(?:among|in)\s+/, "")),
        detail,
        result,
        code: detail.match(CODE)?.[0] ?? null,
      });
    }
  }
  if (lines.length < 2) return null;
  return {
    intro: sents.slice(0, at).join(" ") || null,
    lines,
    area,
    tail: sents.slice(at + 1).join(" ") || null,
  };
}

/** "two trends in the same study, SI-2026-025, which asked X (tracking survey of 2,000, Jun 2026)." */
export function parseStudyIntro(intro: string | null): { trends: boolean; who: string; detail: string } | null {
  if (!intro) return null;
  const m = intro.match(/^two (trends|patterns) in the same study, [^,]+, which asked (.+?)\s*\(([^()]*)\)\.?$/i);
  if (!m) return null;
  return { trends: m[1].toLowerCase() === "trends", who: m[2].trim(), detail: m[3].trim() };
}

export interface ConflictLine {
  code: string;
  result: string;
  detail: string;
}

/** An unresolved conflict as "what each found", plus the context sentences; the analyst sentence is left out. */
export function parseConflict(explanation: string, label: string): { lines: ConflictLine[]; context: string | null } | null {
  const sents = sentences(body(explanation, label));
  if (!sents.length) return null;
  const lines: ConflictLine[] = [];
  const found = /([A-Z]{2,}-\d{4}-\d{2,4}) found (.+?) \(([^()]*)\)/g;
  for (const m of sents[0].matchAll(found)) lines.push({ code: m[1], result: m[2], detail: m[3] });
  if (lines.length < 2) return null;
  const context = sents.slice(1).filter((s) => !/analyst is checking/i.test(s)).join(" ");
  return { lines, context: context || null };
}
