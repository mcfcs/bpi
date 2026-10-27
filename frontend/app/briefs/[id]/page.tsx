"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { BriefView } from "@/components/BriefView";
import { SignedIn } from "@/components/SiteHeader";
import { useSession } from "@/components/Session";
import { api, ApiError } from "@/lib/api";
import type { Brief } from "@/lib/types";

function StoredBrief({ id }: { id: string }) {
  const { profile } = useSession();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBrief(null);
    setError(null);
    api<Brief>(`/api/briefs/${id}`)
      .then(setBrief)
      .catch((e) => setError(e instanceof ApiError && e.status === 404
        ? "This brief belongs to someone else, or it does not exist."
        : e instanceof Error ? e.message : "Could not load the brief."));
  }, [id, profile?.id]);

  if (error) {
    return (
      <p className="notice">
        {error} <Link href="/">Ask a question</Link>
      </p>
    );
  }
  if (!brief) return <p className="loading">Loading the brief…</p>;
  return <BriefView brief={brief} />;
}

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return (
    <SignedIn>
      <StoredBrief id={id} />
    </SignedIn>
  );
}
