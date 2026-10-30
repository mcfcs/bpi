"use client";

import { FileText } from "lucide-react";
import { useState } from "react";
import { openReport } from "@/lib/api";

/** Opens a study's report in a new tab and remembers whether that failed, for the caller to say so. */
function useOpenReport(studyId: string, page: number | null | undefined) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function open() {
    setBusy(true);
    setError(null);
    try {
      await openReport(studyId, page);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The report could not be opened.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, open };
}

function OpenError({ message }: { message: string | null }) {
  return message ? <span className="error small open-error" role="alert">{message}</span> : null;
}

/**
 * The citation chip as a link into the report: "SI-2026-014 · p.3" opens the PDF at page 3 in a
 * new tab. Use it only when the study has a document; otherwise render the static CiteChip.
 */
export function CiteLink({ studyId, code, page, title }: { studyId: string; code: string | null; page?: number | null; title?: string }) {
  const { busy, error, open } = useOpenReport(studyId, page);
  const where = page != null ? `page ${page}` : "the first page";
  return (
    <>
      <button
        type="button"
        className="cite cite-link"
        onClick={open}
        aria-busy={busy || undefined}
        title={title ? `${title}: open the report at ${where}` : `Open the report at ${where}`}
        aria-label={`${[code, page != null ? `page ${page}` : ""].filter(Boolean).join(", ") || "Report"}: open the report at ${where} in a new tab`}
      >
        {code == null ? (page != null ? `p.${page}` : "Report") : (
          <>
            {code}
            {page != null && <span className="page">· p.{page}</span>}
          </>
        )}
      </button>
      <OpenError message={error} />
    </>
  );
}

/** A full button that opens the report, at `page` or its first page. */
export function OpenReportButton({ studyId, page, label = "Open report", className = "btn" }: { studyId: string; page?: number | null; label?: string; className?: string }) {
  const { busy, error, open } = useOpenReport(studyId, page);
  return (
    <>
      <button type="button" className={className} onClick={open} disabled={busy}>
        <FileText size={16} strokeWidth={1.75} aria-hidden />
        {busy ? "Opening…" : label}
        <span className="visually-hidden"> (opens in a new tab)</span>
      </button>
      <OpenError message={error} />
    </>
  );
}
