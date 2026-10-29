import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader, Public_Sans } from "next/font/google";
import { SessionProvider } from "@/components/Session";
import { SiteHeader } from "@/components/SiteHeader";
import { THEME_INIT_SCRIPT } from "@/components/ThemeToggle";
import "./globals.css";

const serif = Newsreader({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
  style: ["normal", "italic"],
  adjustFontFallback: false,
  fallback: ["Georgia", "serif"],
});
const sans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  adjustFontFallback: false,
  fallback: ["sans-serif"],
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
  adjustFontFallback: false,
  fallback: ["monospace"],
});

export const metadata: Metadata = {
  title: "Evidence brief · Strategy & Insights",
  description: "Approved research findings, cited, for BPI business teams. Synthetic demonstration data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The inline script sets data-theme on <html> before React hydrates, hence suppressHydrationWarning.
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`} suppressHydrationWarning>
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
