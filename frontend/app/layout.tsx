import type { Metadata } from "next";
import { Archivo, Fragment_Mono } from "next/font/google";
import { SessionProvider } from "@/components/Session";
import { SiteHeader } from "@/components/SiteHeader";
import { THEME_INIT_SCRIPT } from "@/components/ThemeToggle";
import "./globals.css";

// Archivo: a grotesque drawn for print and screen, with tabular figures, the peso sign and a width
// axis (headings use a slightly narrower cut). latin-ext carries the peso sign (U+20B1).
const sans = Archivo({
  subsets: ["latin", "latin-ext"],
  axes: ["wdth"],
  style: ["normal", "italic"],
  variable: "--font-sans",
  display: "swap",
  fallback: ["Segoe UI", "system-ui", "sans-serif"],
});
// Study codes only.
const mono = Fragment_Mono({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-mono",
  display: "swap",
  fallback: ["ui-monospace", "monospace"],
});

export const metadata: Metadata = {
  title: "ALAMKansya · Strategy & Insights",
  description: "Approved research findings, cited, for BPI business teams. Synthetic demonstration data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The inline script sets data-theme on <html> before React hydrates, hence suppressHydrationWarning.
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <SessionProvider>
          <SiteHeader />
          <main>
            <div className="shell">{children}</div>
          </main>
          <footer className="demo-note">
            <div className="shell">
              Synthetic demonstration data. Findings come only from studies approved by S&amp;I and readable by the
              signed-in team.
            </div>
          </footer>
        </SessionProvider>
      </body>
    </html>
  );
}
