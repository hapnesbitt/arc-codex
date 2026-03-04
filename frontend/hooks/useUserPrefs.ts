/**
 * Arc Codex — useUserPrefs Hook
 * frontend/hooks/useUserPrefs.ts
 *
 * Client hook for reading and writing user preferences.
 * Returns null prefs when not authenticated — callers must handle this.
 *
 * Usage:
 *   const { prefs, loading, savePreferredLang, deleteAccount } = useUserPrefs();
 */

"use client";

import { useState, useEffect, useCallback } from "react";
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

interface UseUserPrefsReturn {
    prefs: UserPrefs | null;
    loading: boolean;
    error: string | null;
    savePreferredLang: (lang: string) => Promise<void>;
    clearPreferredLang: () => Promise<void>;
    deleteAccount: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useUserPrefs(): UseUserPrefsReturn {
    const { data: session, status } = useSession();
    const [prefs, setPrefs] = useState<UserPrefs | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const backendUrl =
        process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:5005";

    // Fetch prefs when session becomes available
    useEffect(() => {
        if (status !== "authenticated" || !session?.user?.id) {
            setPrefs(null);
            return;
        }

        const fetchPrefs = async () => {
            setLoading(true);
            setError(null);
            try {
                // Prefs are fetched via our own Next.js API proxy to avoid
                // exposing the X-User-Id header to the browser.
                const res = await fetch("/api/user/prefs");
                if (res.status === 404) {
                    // First login — prefs not yet created (signIn callback handles creation)
                    setPrefs(null);
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                setPrefs(data);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load preferences");
            } finally {
                setLoading(false);
            }
        };

        fetchPrefs();
    }, [status, session?.user?.id]);

    // Save preferred language
    const savePreferredLang = useCallback(async (lang: string) => {
        if (!session?.user?.id) return;
        try {
            const res = await fetch("/api/user/prefs", {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ preferred_lang: lang }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setPrefs((prev) => prev ? { ...prev, preferred_lang: lang } : prev);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to save preference");
            throw err;
        }
    }, [session?.user?.id]);

    // Clear preferred language
    const clearPreferredLang = useCallback(async () => {
        await savePreferredLang("");
    }, [savePreferredLang]);

    // Delete all user data
    const deleteAccount = useCallback(async () => {
        if (!session?.user?.id) return;
        try {
            const res = await fetch("/api/user/prefs", { method: "DELETE" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setPrefs(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to delete account");
            throw err;
        }
    }, [session?.user?.id]);

    return { prefs, loading, error, savePreferredLang, clearPreferredLang, deleteAccount };
}
