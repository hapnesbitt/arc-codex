"use client";

// File: /frontend/components/UserMenu.tsx
// VERSION: v5 — Removed local auth (/api/me), login now uses signIn() provider picker

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import { useSession, signIn, signOut } from "next-auth/react";
import { useUserPrefs } from "@/components/UserPrefsContext";
import { Settings, LogOut, Globe, Trash2, X, Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import LANGUAGES from "@/lib/languages.json";

export default function UserMenu() {
    const { data: session, status } = useSession();
    const { prefs, savePreferredLang, clearPreferredLang, deleteAccount } = useUserPrefs();
    const [panelOpen, setPanelOpen]         = useState(false);
    const [langValue, setLangValue]         = useState("");
    const [saving, setSaving]               = useState(false);
    const [saved, setSaved]                 = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [deleting, setDeleting]           = useState(false);
    const [deleteError, setDeleteError]     = useState<string | null>(null);
    const panelRef        = useRef<HTMLDivElement>(null);
    const triggerRef      = useRef<HTMLButtonElement>(null);
    const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        if (prefs?.preferred_lang !== undefined) setLangValue(prefs.preferred_lang);
    }, [prefs?.preferred_lang]);

    useEffect(() => {
        if (!panelOpen) return;
        const handleClick = (e: MouseEvent) => {
            if (panelRef.current && !panelRef.current.contains(e.target as Node)) closePanel();
        };
        const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") closePanel(); };
        document.addEventListener("mousedown", handleClick);
        document.addEventListener("keydown", handleEsc);
        return () => {
            document.removeEventListener("mousedown", handleClick);
            document.removeEventListener("keydown", handleEsc);
        };
    }, [panelOpen]);

    useEffect(() => {
        return () => { if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current); };
    }, []);

    const closePanel = () => {
        setPanelOpen(false);
        setConfirmDelete(false);
        setDeleteError(null);
        if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
        triggerRef.current?.focus();
    };

    const handleSaveLang = async () => {
        setSaving(true);
        try {
            langValue.trim() ? await savePreferredLang(langValue.trim()) : await clearPreferredLang();
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        } finally {
            setSaving(false);
        }
    };

    const handleDeleteClick = () => {
        if (!confirmDelete) {
            setConfirmDelete(true);
            setDeleteError(null);
            confirmTimerRef.current = setTimeout(() => setConfirmDelete(false), 5000);
            return;
        }
        handleDeleteConfirmed();
    };

    const handleDeleteConfirmed = async () => {
        if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
        setDeleting(true);
        setDeleteError(null);
        try {
            await deleteAccount();
            await signOut({ redirect: false });
            setPanelOpen(false);
            setConfirmDelete(false);
        } catch (err) {
            setDeleteError(err instanceof Error ? err.message : "Failed to delete account. Please try again.");
            setConfirmDelete(false);
        } finally {
            setDeleting(false);
        }
    };

    const handleCancelDelete = () => {
        if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
        setConfirmDelete(false);
        setDeleteError(null);
    };

    if (status === "loading") {
        return (
            <div className="px-3 py-2">
                <div className="h-8 w-full rounded-lg bg-white/5 animate-pulse" aria-hidden="true" />
            </div>
        );
    }

    // ── Not authenticated ─────────────────────────────────────────────────────
    if (status === "unauthenticated") {
        return (
            <div className="px-3 py-2 border-t border-white/10 mt-2">
                <button
                    onClick={() => signIn()}
                    className="w-full flex items-center justify-center gap-2.5 px-3 py-2 rounded-lg
                               text-sm text-slate-400 hover:text-amber-300 hover:bg-white/5
                               border border-transparent hover:border-amber-400/20
                               transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
                >
                    <LogIn className="h-4 w-4" aria-hidden="true" />
                    <span>Sign In</span>
                </button>
            </div>
        );
    }

    // ── OAuth authenticated (GitHub) — existing prefs panel ──────────────────
    const user = session!.user;
    const displayLang = prefs?.preferred_lang || null;

    return (
        <div className="px-3 py-2 border-t border-white/10 mt-2 relative" ref={panelRef}>
            <button
                ref={triggerRef}
                onClick={() => setPanelOpen((v) => !v)}
                aria-expanded={panelOpen}
                aria-haspopup="dialog"
                aria-label={`User settings${displayLang ? `, preferred language: ${displayLang}` : ''}`}
                className="w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-white/5
                           transition-colors group outline-none focus-visible:ring-2 focus-visible:ring-yellow-400/50"
            >
                {user.image ? (
                    <Image
                        src={user.image}
                        alt=""
                        width={28}
                        height={28}
                        className="rounded-full ring-1 ring-white/10 group-hover:ring-yellow-400/40 transition-all flex-shrink-0"
                    />
                ) : (
                    <div
                        className="h-7 w-7 rounded-full bg-blue-500/30 border border-blue-400/30 flex items-center justify-center flex-shrink-0"
                        aria-hidden="true"
                    >
                        <span className="text-xs font-bold text-blue-300">
                            {(user.name ?? user.email ?? "?")[0].toUpperCase()}
                        </span>
                    </div>
                )}
                <div className="flex-1 min-w-0 text-left" aria-hidden="true">
                    <p className="text-xs font-medium text-slate-300 truncate group-hover:text-yellow-300 transition-colors">
                        {user.name ?? user.email}
                    </p>
                    {displayLang && (
                        <p className="text-[10px] text-slate-500 truncate">{displayLang}</p>
                    )}
                </div>
                <Settings
                    className={cn(
                        "h-3.5 w-3.5 text-slate-500 flex-shrink-0 transition-transform duration-300",
                        panelOpen ? "rotate-90 text-yellow-400" : "group-hover:text-slate-300"
                    )}
                    aria-hidden="true"
                />
            </button>

            {panelOpen && (
                <div
                    role="dialog"
                    aria-label="User preferences"
                    aria-modal="true"
                    className="absolute bottom-0 left-full ml-4 w-72 rounded-xl border border-white/10 bg-[#0d1117]/95
                               backdrop-blur-xl overflow-visible shadow-2xl z-[100] animate-in fade-in slide-in-from-left-2 duration-200"
                >
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                            Interface Prefs
                        </span>
                        <button
                            onClick={closePanel}
                            aria-label="Close preferences panel"
                            className="text-slate-500 hover:text-slate-300 transition-colors p-1 rounded focus-visible:ring-2 focus-visible:ring-yellow-400/50 outline-none"
                        >
                            <X className="h-4 w-4" aria-hidden="true" />
                        </button>
                    </div>

                    <div className="p-4 border-b border-white/10">
                        <div className="flex items-center gap-2 mb-3">
                            <Globe className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
                            <span className="text-[11px] font-bold text-slate-300 uppercase tracking-tighter">
                                Native Protocol
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <label htmlFor="usermenu-lang-select" className="sr-only">Preferred language</label>
                            <select
                                id="usermenu-lang-select"
                                value={langValue}
                                onChange={(e) => setLangValue(e.target.value)}
                                className="flex-1 text-xs bg-black/40 text-slate-200 rounded-lg px-2 py-2
                                           border border-white/10 focus:border-yellow-400/50 outline-none
                                           focus:ring-1 focus:ring-yellow-400/30 cursor-pointer"
                            >
                                <option value="">Auto-Detect (Original)</option>
                                {LANGUAGES.map(({ code, name }) => (
                                    <option key={code} value={name}>{name}</option>
                                ))}
                            </select>
                            <button
                                onClick={handleSaveLang}
                                disabled={saving || langValue === (prefs?.preferred_lang ?? "")}
                                aria-label={saving ? "Saving" : saved ? "Saved" : "Save language preference"}
                                className="h-8 min-w-[60px] flex items-center justify-center rounded-lg text-[10px] font-black uppercase tracking-widest
                                           bg-amber-500/10 text-amber-500 border border-amber-500/30
                                           hover:bg-amber-500/20 disabled:opacity-20 disabled:cursor-not-allowed
                                           transition-all active:scale-95 focus-visible:ring-2 focus-visible:ring-amber-400/50 outline-none"
                            >
                                {saved ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : saving ? "..." : "Save"}
                            </button>
                        </div>
                        {displayLang && (
                            <p className="text-[10px] text-slate-500 mt-3 italic leading-tight">
                                Intelligence will auto-translate to {displayLang} on load.
                            </p>
                        )}
                    </div>

                    <div className="p-2 space-y-1">
                        <button
                            onClick={() => signOut({ redirect: false }).then(() => setPanelOpen(false))}
                            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest
                                       text-slate-400 hover:text-white hover:bg-white/5 transition-all outline-none
                                       focus-visible:ring-2 focus-visible:ring-white/30"
                        >
                            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                            Sign out
                        </button>

                        {deleteError && (
                            <div role="alert" className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-[10px]">
                                <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" aria-hidden="true" />
                                <span>{deleteError}</span>
                            </div>
                        )}

                        {confirmDelete ? (
                            <div className="flex gap-1">
                                <button
                                    onClick={handleDeleteConfirmed}
                                    disabled={deleting}
                                    aria-label={deleting ? "Deleting account" : "Confirm account deletion"}
                                    aria-busy={deleting}
                                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest
                                               bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20
                                               disabled:opacity-50 disabled:cursor-wait transition-all outline-none
                                               focus-visible:ring-2 focus-visible:ring-red-400/50"
                                >
                                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                    {deleting ? "Purging..." : "Confirm Purge"}
                                </button>
                                <button
                                    onClick={handleCancelDelete}
                                    disabled={deleting}
                                    aria-label="Cancel account deletion"
                                    className="px-3 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest
                                               text-slate-400 hover:text-white hover:bg-white/5 disabled:opacity-50
                                               transition-all outline-none focus-visible:ring-2 focus-visible:ring-white/30"
                                >
                                    Cancel
                                </button>
                            </div>
                        ) : (
                            <button
                                onClick={handleDeleteClick}
                                aria-label="Delete account data"
                                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest
                                           text-slate-600 hover:text-red-400 hover:bg-red-500/5 transition-all
                                           outline-none focus-visible:ring-2 focus-visible:ring-red-400/50"
                            >
                                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                Purge Data
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

// Named import needed internally — not exported
function LogIn({ className }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
            <polyline points="10 17 15 12 10 7"/>
            <line x1="15" y1="12" x2="3" y2="12"/>
        </svg>
    );
}
