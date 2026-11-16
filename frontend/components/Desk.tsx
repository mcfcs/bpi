"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, ClipboardCheck, FileSearch, KeyRound, Map, MessageSquareReply, Telescope } from "lucide-react";
import { api } from "@/lib/api";
import type { AccessRequest, EscalationRow, Profile, UsageSummary } from "@/lib/types";

interface Card {
  href: string;
  title: string;
  value: string;
  note: string;
  Icon: typeof ArrowRight;
  urgent?: boolean;
}

/** Counts behind one request each; a failed call just leaves its card without a number. */
async function count<T>(path: string, pick: (rows: T) => number): Promise<number | null> {
  try {
    return pick(await api<T>(path));
  } catch {
    return null;
  }
}

const shown = (n: number | null) => (n == null ? "–" : String(n));

/**
 * What is waiting for this person, on the ask page: for S&I the review queue, analyst questions,
 * access decisions and unanswered demand; for a business unit, analyst replies, access requests and
 * the ways in besides asking. Each card links to the page where the work is done.
 */
export function Desk({ profile }: { profile: Profile }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  const isSi = profile.role === "si_analyst";

  useEffect(() => {
    let live = true;
    (async () => {
      const access = count<AccessRequest[]>("/api/access-requests", (r) => r.filter((x) => x.can_decide).length);
      const escalations = api<EscalationRow[]>("/api/escalations").catch(() => null);
      if (isSi) {
        const [queue, decide, esc, usage] = await Promise.all([
          count<unknown[]>("/api/review/queue", (r) => r.length),
          access,
          escalations,
          api<UsageSummary>("/api/audit/summary?days=30").catch(() => null),
        ]);
        const open = esc ? esc.filter((e) => e.status === "open").length : null;
        if (!live) return;
        setCards([
          { href: "/review", title: "Review queue", value: shown(queue), note: "reports waiting; each gets a personal-data and overlap check", Icon: ClipboardCheck, urgent: !!queue },
          { href: "/analyst", title: "Analyst desk", value: shown(open), note: "questions from business units waiting for a reply", Icon: MessageSquareReply, urgent: !!open },
          { href: "/gaps", title: "Gap map", value: shown(usage?.unanswered_total ?? null), note: "questions no readable study answered in 30 days", Icon: Map },
          { href: "/access", title: "Access", value: shown(decide), note: "requests for S&I studies waiting for your decision", Icon: KeyRound, urgent: !!decide },
        ]);
      } else {
        const [decide, esc, mine] = await Promise.all([
          access,
          escalations,
          count<AccessRequest[]>("/api/access-requests", (r) => r.filter((x) => x.mine && x.status === "pending").length),
        ]);
        const replies = esc ? esc.filter((e) => e.status === "answered").length : null;
        if (!live) return;
        setCards([
          { href: "/analyst", title: "Analyst replies", value: shown(replies), note: "answers from S&I to questions you sent", Icon: MessageSquareReply, urgent: !!replies },
          { href: "/access", title: "Access", value: shown(profile.role === "bu_approver" ? decide : mine),
            note: profile.role === "bu_approver" ? "requests for your team's studies waiting for you" : "of your requests still waiting for the owner", Icon: KeyRound,
            urgent: profile.role === "bu_approver" && !!decide },
          { href: "/studies", title: "Studies", value: "Browse", note: "every approved study, including ones you can request", Icon: FileSearch },
          { href: "/commission", title: "Before you commission", value: "Check", note: "what existing research already covers your objectives", Icon: Telescope },
        ]);
      }
    })();
    return () => {
      live = false;
    };
  }, [isSi, profile.role]);

  return (
    <section className="desk" aria-labelledby="desk-title">
      <h2 id="desk-title">{isSi ? "Your desk" : "Also for you"}</h2>
      <ul>
        {(cards ?? Array.from({ length: 4 }, () => null)).map((c, i) => (
          <li key={c?.href ?? i}>
            {c ? (
              <Link href={c.href} className={`desk-card${c.urgent ? " urgent" : ""}`}>
                <span className="desk-top">
                  <c.Icon size={18} strokeWidth={1.75} aria-hidden />
                  {c.title}
                  <ArrowRight size={16} strokeWidth={1.75} aria-hidden className="desk-go" />
                </span>
                <span className="desk-value nums">{c.value}</span>
                <span className="desk-note">{c.note}</span>
              </Link>
            ) : (
              <span className="desk-card loading-card" aria-hidden />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
