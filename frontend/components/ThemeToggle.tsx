"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

export const THEME_KEY = "si-evidence:theme";
const CHANGE_EVENT = "si-evidence:themechange";

/**
 * Runs in <head> before first paint (see app/layout.tsx), so a saved choice never flashes the
 * other theme. Light unless the reader chose dark; the device setting is deliberately ignored.
 */
export const THEME_INIT_SCRIPT = `(function(){var t="light";try{if(localStorage.getItem("${THEME_KEY}")==="dark")t="dark"}catch(e){}document.documentElement.dataset.theme=t})();`;

function read(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  // Another tab changed the setting: apply it here too.
  const onStorage = (e: StorageEvent) => {
    if (e.key === THEME_KEY) apply(e.newValue === "dark" ? "dark" : "light", false);
  };
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function apply(theme: Theme, persist = true): void {
  document.documentElement.dataset.theme = theme;
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Storage unavailable (private window): the choice lasts for this page only.
    }
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

const OPTIONS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: "Light theme", Icon: Sun },
  { value: "dark", label: "Dark theme", Icon: Moon },
];

export function ThemeToggle() {
  // The server can't know the stored choice, so it renders light; the client snapshot follows.
  const theme = useSyncExternalStore(subscribe, read, () => "light" as Theme);

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
          <Icon size={16} strokeWidth={1.75} aria-hidden />
        </button>
      ))}
    </div>
  );
}
