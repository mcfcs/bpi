"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import type { Profile } from "@/lib/types";

interface SessionValue {
  profile: Profile | null;
  personas: Profile[];
  ready: boolean;
  error: string | null;
  signIn: (email: string) => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

/** Demo sign-in with the seeded synthetic personas. In production this is Supabase Auth. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [personas, setPersonas] = useState<Profile[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = useCallback(async (email: string) => {
    const result = await api<{ token: string; profile: Profile }>("/api/demo/login", { method: "POST", json: { email } });
    setToken(result.token);
    setProfile(result.profile);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Independent requests: fetch the persona list and the current profile together.
      const mePromise = getToken()
        ? api<Profile>("/api/me").catch(() => {
            setToken(null);
            return null;
          })
        : Promise.resolve(null);
      try {
        const [list, me] = await Promise.all([api<Profile[]>("/api/demo/personas"), mePromise]);
        if (cancelled) return;
        setPersonas(list);
        if (me) setProfile(me);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load the demo personas.");
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ profile, personas, ready, error, signIn }), [profile, personas, ready, error, signIn]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
