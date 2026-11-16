"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Menu, X } from "lucide-react";
import { useSession } from "./Session";
import { ROLE_LABELS } from "@/lib/format";
import type { Profile } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";
import { ALERTS_CHANGED } from "./AnswerAlerts";
import { api } from "@/lib/api";
import type { AnswerAlert } from "@/lib/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

/** Closes a popover on Escape or a click outside `ref`. */
function useDismiss(open: boolean, close: () => void, ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open, close, ref]);
}

/**
 * The demo persona switch: who you are, as a compact button, and the other personas in a menu.
 * Replaces a native select whose "name · team" option text made the header wrap.
 */
function PersonaMenu({ profile, personas, signIn }: { profile: Profile | null; personas: Profile[]; signIn: (email: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useDismiss(open, () => setOpen(false), ref);

  return (
    <div className="persona" ref={ref}>
      <button
        type="button"
        className="persona-button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="avatar" aria-hidden>{profile ? initials(profile.display_name) : "?"}</span>
        <span className="persona-text">
          <span className="visually-hidden">Viewing as (demo persona): </span>
          <strong>{profile?.display_name ?? "Choose a persona"}</strong>
          {profile && <small>{profile.team_name}</small>}
        </span>
        <ChevronDown size={15} strokeWidth={2} aria-hidden className="chev" />
      </button>
      {open && (
        <div className="persona-menu" id={menuId}>
          <p className="persona-menu-head">Demo personas. Each sees only what their team may read.</p>
          <ul>
            {personas.map((p) => {
              const current = p.email === profile?.email;
              return (
                <li key={p.email}>
                  <button
                    type="button"
                    aria-current={current ? "true" : undefined}
                    onClick={() => {
                      setOpen(false);
                      if (!current) signIn(p.email).catch(() => undefined);
                    }}
                  >
                    <span className="avatar" aria-hidden>{initials(p.display_name)}</span>
                    <span>
                      <strong>{p.display_name}</strong>
                      <small>{p.team_name} · {ROLE_LABELS[p.role]}</small>
                    </span>
                    {current && <Check size={16} strokeWidth={2} aria-label="Current persona" className="tick" />}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const { profile, personas, signIn } = useSession();
  const isSi = profile?.role === "si_analyst";
  const [menuOpen, setMenuOpen] = useState(false);

  const links = [
    { href: "/", label: "Ask a question", show: true },
    { href: "/studies", label: "Studies", show: true },
    // Analysts have eight links; two shorter labels keep them on one row beside the tools.
    { href: "/commission", label: isSi ? "Commissioning" : "Before you commission", show: true },
    { href: "/access", label: "Access", show: true },
    { href: "/analyst", label: isSi ? "Analyst desk" : "Ask an analyst", show: true },
    { href: "/review", label: "Review queue", show: isSi },
    { href: "/gaps", label: "Gap map", show: isSi },
    { href: "/audit", label: "Audit log", show: isSi },
  ].filter((l) => l.show);
  const current = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/briefs") : pathname.startsWith(href));

  // A new page closes the small-screen menu.
  useEffect(() => setMenuOpen(false), [pathname]);

  // Unread "a new study answers your question" alerts, shown as a count on "Ask a question".
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!profile) {
      setUnread(0);
      return;
    }
    const load = () =>
      api<AnswerAlert[]>("/api/alerts")
        .then((rows) => setUnread(rows.filter((a) => !a.read_at).length))
        .catch(() => setUnread(0));
    load();
    window.addEventListener(ALERTS_CHANGED, load);
    return () => window.removeEventListener(ALERTS_CHANGED, load);
  }, [profile, pathname]);

  const linkList = links.map((l) => (
    <Link key={l.href} href={l.href} aria-current={current(l.href) ? "page" : undefined}>
      {l.label}
      {l.href === "/" && unread > 0 && (
        <span className="nav-badge" aria-label={`${unread} new ${unread === 1 ? "answer" : "answers"} to earlier questions`}>
          {unread}
        </span>
      )}
    </Link>
  ));

  return (
    // data-links sets the width at which the links fold into the menu button (see globals.css).
    <header className="site-header" data-links={links.length > 5 ? "many" : "few"}>
      <div className="shell header-bar">
        <Link href="/" className="wordmark">
          {/* The favicon's mark (app/icon.svg), gold on the band. */}
          <svg width="20" height="26" viewBox="9 7 14 18" aria-hidden>
            <g fill="var(--bpi-gold)">
              <rect x="9" y="7" width="3.5" height="18" />
              <rect x="19.5" y="7" width="3.5" height="18" />
              <rect x="9" y="7" width="14" height="3.5" />
              <rect x="9" y="15" width="14" height="3.5" />
            </g>
          </svg>
          <span>
            <strong>ALAMKansya</strong>
            <small>Strategy &amp; Insights</small>
          </span>
        </Link>
        <nav className="nav" aria-label="Main">{linkList}</nav>
        <div className="header-tools">
          <ThemeToggle />
          {personas.length > 0 && <PersonaMenu profile={profile} personas={personas} signIn={signIn} />}
          <button
            type="button"
            className="menu-button"
            aria-expanded={menuOpen}
            aria-controls="site-menu"
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? <X size={18} strokeWidth={2} aria-hidden /> : <Menu size={18} strokeWidth={2} aria-hidden />}
            <span>Menu</span>
          </button>
        </div>
      </div>
      <nav id="site-menu" className="nav-panel" aria-label="Main menu" hidden={!menuOpen}>
        <div className="shell">{linkList}</div>
      </nav>
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
