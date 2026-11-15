"use client";

import { useRouter } from "next/navigation";
import { CornerDownRight } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Brief } from "@/lib/types";

/**
 * A follow-up question on this brief ("What about Mindanao?"). It becomes a new brief that searches
 * with this brief's question plus the follow-up, under the same permissions and checks.
 */
export function FollowUp({ brief }: { brief: Brief }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = text.trim().length >= 5;

  async function send(question: string) {
    setBusy(true);
    setError(null);
    try {
      const next = await api<Brief>(`/api/briefs/${brief.id}/follow-up`, { method: "POST", json: { question } });
      router.push(`/briefs/${next.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The follow-up could not be prepared.");
      setBusy(false);
    }
  }

  return (
    <form
      className="follow-up no-print"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !busy) send(text.trim());
      }}
    >
      <label htmlFor="follow-up">
        <CornerDownRight size={16} strokeWidth={2} aria-hidden /> Ask a follow-up
      </label>
      <div className="follow-up-row">
        <input
          id="follow-up"
          value={text}
          maxLength={300}
          onChange={(e) => setText(e.target.value)}
          placeholder="For example: What about Mindanao? Only owners under 30?"
          disabled={busy}
        />
        <button className="btn btn-primary" disabled={!ready || busy}>{busy ? "Preparing…" : "Ask"}</button>
      </div>
      <p className="hint">Searched together with this brief&rsquo;s question, from the same studies your team may read.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}
