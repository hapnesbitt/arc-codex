"use client";

/**
 * Arc Codex — UserPrefsContext.tsx
 * frontend/components/UserPrefsContext.tsx
 *
 * Single source of truth for user preferences.
 * Wrap the app with <UserPrefsProvider> so all components share one fetch.
 * Both UserMenu and TranslateButton consume from this context — saves in
 * UserMenu are immediately visible to TranslateButton without a page refresh.
 */

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { useSession } from "next-auth/react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserPrefs {
  sub: string;
  email: string;
  name: string;
  picture: string;
  preferred_lang: string;
  created_at: string;
  last_seen: string;
}

interface UserPrefsContextValue {
  prefs: UserPrefs | null;
  loading: boolean;
  error: string | null;
  savePreferredLang: (lang: string) => Promise<void>;
  clearPreferredLang: () => Promise<void>;
  deleteAccount: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const UserPrefsContext = createContext<UserPrefsContextValue>({
  prefs: null,
  loading: false,
  error: null,
  savePreferredLang: async () => {},
  clearPreferredLang: async () => {},
  deleteAccount: async () => {},
});

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function UserPrefsProvider({ children }: { children: ReactNode }) {
  const { data: session, status } = useSession();
  const [prefs, setPrefs] = useState<UserPrefs | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch once when session becomes available
  useEffect(() => {
    if (status !== "authenticated" || !session?.user?.id) {
      setPrefs(null);
      return;
    }

    const fetchPrefs = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/user/prefs");
        if (res.status === 404) { setPrefs(null); return; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setPrefs(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load preferences");
      } finally {
        setLoading(false);
      }
    };

    fetchPrefs();
  }, [status, session?.user?.id]);

  const savePreferredLang = useCallback(async (lang: string) => {
    try {
      const res = await fetch("/api/user/prefs", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferred_lang: lang }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Update local state immediately — no refetch needed
      setPrefs((prev) => prev ? { ...prev, preferred_lang: lang } : prev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save preference");
      throw err;
    }
  }, []);

  const clearPreferredLang = useCallback(() => savePreferredLang(""), [savePreferredLang]);

  const deleteAccount = useCallback(async () => {
    const res = await fetch("/api/user/prefs", { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    setPrefs(null);
  }, []);

  return (
    <UserPrefsContext.Provider value={{ prefs, loading, error, savePreferredLang, clearPreferredLang, deleteAccount }}>
      {children}
    </UserPrefsContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook — drop-in replacement for the old useUserPrefs
// ---------------------------------------------------------------------------

export function useUserPrefs() {
  return useContext(UserPrefsContext);
}
