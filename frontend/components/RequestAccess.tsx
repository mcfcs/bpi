"use client";

import { createContext, use, useState } from "react";
import { api, ApiError } from "@/lib/api";

type RequestStatus = "pending" | "approved" | "denied" | null;

interface RequestAccessValue {
  studyId: string;
  ownerTeam: string;
  status: RequestStatus;
  open: boolean;
  setOpen: (open: boolean) => void;
  submit: (purpose: string) => Promise<boolean>;
  busy: boolean;
  error: string | null;
}

const RequestAccessContext = createContext<RequestAccessValue | null>(null);

function useRequestAccess(): RequestAccessValue {
  const value = use(RequestAccessContext);
  if (!value) throw new Error("RequestAccess parts must sit inside RequestAccess.Provider");
  return value;
}

/**
 * Holds one study's access request: its stored status, whether the purpose form is open, and the
 * send. The action (button or status) and the form are separate parts so each page can place them
 * in its own layout: the brief puts the form under the row, the Studies list under the title.
 */
function Provider({ studyId, ownerTeam, initialStatus, children }: { studyId: string; ownerTeam: string; initialStatus: RequestStatus; children: React.ReactNode }) {
  const [status, setStatus] = useState<RequestStatus>(initialStatus);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(purpose: string) {
    setBusy(true);
    setError(null);
    try {
      await api("/api/access-requests", { method: "POST", json: { study_id: studyId, purpose } });
      setStatus("pending");
      setOpen(false);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The request could not be sent.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <RequestAccessContext value={{ studyId, ownerTeam, status, open, setOpen, submit, busy, error }}>
      {children}
    </RequestAccessContext>
  );
}

/** The request's state, or the button that starts one. `approved` is what an approval means here. */
function Action({ approved = "Approved" }: { approved?: string }) {
  const { status, ownerTeam, open, setOpen } = useRequestAccess();
  if (status === "pending") return <span className="status status-wait" role="status">Requested, waiting for {ownerTeam}</span>;
  if (status === "approved") return <span className="status status-ok">{approved}</span>;
  if (open) return null;
  return (
    <span className="actions">
      {status === "denied" && <span className="status status-bad">Not approved</span>}
      <button type="button" className="btn" onClick={() => setOpen(true)}>
        {status === "denied" ? "Request again" : "Request access"}
      </button>
    </span>
  );
}

/** Why the team needs the study. Shown only while a request is being written. */
function Form({ className }: { className?: string }) {
  const { studyId, open, setOpen, submit, busy, error } = useRequestAccess();
  const [purpose, setPurpose] = useState("");
  if (!open) return null;
  const id = `purpose-${studyId}`;
  return (
    <form
      className={className}
      onSubmit={(event) => {
        event.preventDefault();
        submit(purpose).then((sent) => sent && setPurpose(""));
      }}
    >
      <div className="field">
        <label htmlFor={id}>How will your team use this study?</label>
        <textarea id={id} rows={3} value={purpose} onChange={(e) => setPurpose(e.target.value)} required minLength={10} autoFocus />
        <p className="hint">The owning team or S&amp;I reviews every request. Approval shares the study with your team.</p>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button className="btn btn-primary" disabled={busy || purpose.trim().length < 10}>{busy ? "Sending…" : "Send request"}</button>
        <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  );
}

export const RequestAccess = { Provider, Action, Form };
