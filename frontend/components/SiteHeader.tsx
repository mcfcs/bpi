"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "./Session";
import { ROLE_LABELS } from "@/lib/format";
import { ThemeToggle } from "./ThemeToggle";

export function SiteHeader() {
  const pathname = usePathname();
  const { profile, personas, signIn } = useSession();
  const isSi = profile?.role === "si_analyst";

  const links = [
    { href: "/", label: "Ask a question", show: true },
    { href: "/studies", label: "Studies", show: true },
    { href: "/commission", label: "Before you commission", show: true },
    { href: "/access", label: "Access", show: true },
    { href: "/analyst", label: isSi ? "Analyst desk" : "Ask an analyst", show: true },
    { href: "/review", label: "Review queue", show: isSi },
    { href: "/audit", label: "Audit log", show: isSi },
  ];
  const current = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/briefs") : pathname.startsWith(href));

  return (
    <header className="site-header">
      <div className="shell">
        <Link href="/" className="wordmark">
          {/* The favicon's mark (app/icon.svg), gold on the band. */}
          <svg width="20" height="26" viewBox="9 7 14 18" aria-hidden>
            <g fill="var(--bpi-gold)">
              <rect x="9" y="7" width="3.5" height="18" />
              <rect x="9" y="7" width="14" height="3.5" />
              <rect x="9" y="14.25" width="10" height="3.5" />
              <rect x="9" y="21.5" width="14" height="3.5" />
            </g>
          </svg>
          <span>
            <strong>Evidence brief</strong>
            <small>Strategy &amp; Insights</small>
          </span>
        </Link>
        <nav className="nav" aria-label="Main">
          {links.filter((l) => l.show).map((l) => (
            <Link key={l.href} href={l.href} aria-current={current(l.href) ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <ThemeToggle />
        {personas.length > 0 && (
          <div className="persona">
            <label htmlFor="persona" className="visually-hidden">Viewing as (demo persona)</label>
            <select
              id="persona"
              value={profile?.email ?? ""}
              onChange={(e) => {
                if (e.target.value) signIn(e.target.value).catch(() => undefined);
              }}
            >
              {!profile && <option value="">Choose a persona</option>}
              {personas.map((p) => (
                <option key={p.email} value={p.email}>
                  {p.display_name} · {p.team_name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
    </header>
  );
}

/** Renders children once a persona is signed in; otherwise offers the persona list. */
export function SignedIn({ children, siOnly = false }: { children: React.ReactNode; siOnly?: boolean }) {
  const { profile, personas, ready, error, signIn } = useSession();
  if (!ready) return <p className="loading" role="status">Loading…</p>;
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!profile) {
    return (
      <section className="page-head" style={{ maxWidth: "none" }}>
        <h1>Choose who you are</h1>
        <p>This is a demo. Each persona sees only the studies their team may read, and all data is synthetic.</p>
        <ul className="personas">
          {personas.map((p) => (
            <li key={p.email}>
              <button type="button" aria-label={`Sign in as ${p.display_name}`} onClick={() => signIn(p.email).catch(() => undefined)}>
                <strong>{p.display_name}</strong>
                <span>{p.team_name} · {ROLE_LABELS[p.role]}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    );
  }
  if (siOnly && profile.role !== "si_analyst") {
    return <p className="notice">This page is for S&amp;I analysts. Switch persona to continue.</p>;
  }
  return <>{children}</>;
}
