"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";

export const THEME_KEY = "si-evidence:theme";
const CHANGE_EVENT = "si-evidence:themechange";

/**
 * Runs in <head> before first paint (see app/layout.tsx), so a saved choice never flashes the
 * other theme. "system" is the absence of data-theme: the CSS then follows prefers-color-scheme.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}})();`;

function read(): Theme {
  const t = document.documentElement.dataset.theme;
  return t === "light" || t === "dark" ? t : "system";
}

function subscribe(onChange: () => void): () => void {
  // Another tab changed the setting: apply it here too.
  const onStorage = (e: StorageEvent) => {
    if (e.key !== THEME_KEY) return;
    apply(e.newValue === "light" || e.newValue === "dark" ? e.newValue : "system", false);
  };
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function apply(theme: Theme, persist = true): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  if (persist) {
    try {
      if (theme === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Storage unavailable (private window): the choice lasts for this page only.
    }
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

const OPTIONS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "Match device", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

export function ThemeToggle() {
  // The server can't know the stored choice, so it renders "system"; the client snapshot follows.
  const theme = useSyncExternalStore(subscribe, read, () => "system" as Theme);

  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          aria-pressed={theme === value}
          aria-label={label}
          title={label}
          onClick={() => apply(value)}
        >
          <Icon size={15} strokeWidth={1.75} aria-hidden />
        </button>
      ))}
    </div>
  );
}
