"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import type { Plan, PublicConfig, User } from "@/lib/types";

type SessionState = {
  user: User | null;
  plan: Plan | null;
  config: PublicConfig | null;
  loading: boolean;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<SessionState>({
  user: null,
  plan: null,
  config: null,
  loading: true,
  refresh: async () => {},
});

export function AppProviders({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const s = await api.session();
      setUser(s.user);
      setPlan(s.plan);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    api.config().then(setConfig).catch(() => setConfig(null));
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, [refresh]);

  return <SessionContext.Provider value={{ user, plan, config, loading, refresh }}>{children}</SessionContext.Provider>;
}

export const useSession = () => useContext(SessionContext);
