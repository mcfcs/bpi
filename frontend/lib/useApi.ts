"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * GET `path` on mount and whenever `path` or `key` changes (pass the signed-in profile id as `key`
 * so lists refresh on persona switch). A failed load keeps the last data and reports the error,
 * instead of looking like an empty list. Responses that arrive after a newer request are dropped.
 */
export function useApi<T>(path: string | null, key?: unknown): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let current = true;
    setLoading(true);
    setError(null);
    api<T>(path)
      .then((value) => {
        if (current) setData(value);
      })
      .catch((e: unknown) => {
        if (current) setError(e instanceof Error ? e.message : "Could not load this page.");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [path, key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
