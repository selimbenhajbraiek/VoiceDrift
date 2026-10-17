"use client";
// Who is signed in (from the backend's cookie session), plus toasts and a polling hook shared by the pages.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import type { User } from "./types";

interface Session {
  /** undefined while checking, null when signed out */
  me: User | null | undefined;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
  toast: (msg: string) => void;
  toastMsg: string | null;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<User | null | undefined>(undefined);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe(null); // signed out (401), or the backend isn't running: the sign-in page explains which
    }
  }, []);
  const signOut = useCallback(async () => {
    await api.logout().catch(() => {});
    setMe(null);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!toastMsg) return;
    const t = setTimeout(() => setToastMsg(null), 2800);
    return () => clearTimeout(t);
  }, [toastMsg]);

  return <Ctx.Provider value={{ me, refresh, signOut, toast: setToastMsg, toastMsg }}>{children}</Ctx.Provider>;
}

export function useSession() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession must be used inside SessionProvider");
  return s;
}

/** Load data now and every `ms` (0 = once). Keeps the last good data if a later load fails. */
export function usePolling<T>(load: () => Promise<T>, ms: number, key: unknown = null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => { setData(null); }, [key]); // new key, new data: don't show the old one meanwhile
  useEffect(() => {
    reload();
    if (!ms) return;
    const t = setInterval(reload, ms);
    return () => clearInterval(t);
  }, [reload, ms, key]);

  return { data, error, reload, setData };
}
