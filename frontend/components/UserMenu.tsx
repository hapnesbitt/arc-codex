"use client";

import { useState, useRef, useEffect } from "react";
import { useSession, signIn, signOut } from "next-auth/react";
import { useUserPrefs } from "@/components/UserPrefsContext";
import { Settings, LogOut, Globe, Trash2, X, Check } from "lucide-react";
import { cn } from "@/lib/utils";

const COMMON_LANGUAGES = [
    "Arabic", "Bengali", "Chinese (Simplified)", "Chinese (Traditional)",
    "Dutch", "English", "French", "German", "Greek", "Hindi", "Indonesian",
    "Italian", "Japanese", "Korean", "Malay", "Persian", "Polish",
    "Portuguese", "Russian", "Spanish", "Swahili", "Swedish",
    "Tamil", "Telugu", "Thai", "Turkish", "Ukrainian", "Urdu",
    "Vietnamese",
];

export default function UserMenu() {
    const { data: session, status } = useSession();
    const { prefs, savePreferredLang, clearPreferredLang, deleteAccount } = useUserPrefs();
    const [panelOpen, setPanelOpen] = useState(false);
    const [langValue, setLangValue] = useState("");
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const panelRef = useRef<HTMLDivElement>(null);

    // Sync language picker with stored prefs
    useEffect(() => {
        if (prefs?.preferred_lang !== undefined) {
            setLangValue(prefs.preferred_lang);
        }
    }, [prefs?.preferred_lang]);

    // Close panel on outside click or Escape key
    useEffect(() => {
        if (!panelOpen) return;
        const handleClick = (e: MouseEvent) => {
            if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
                setPanelOpen(false);
                setConfirmDelete(false);
            }
        };
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                setPanelOpen(false);
                setConfirmDelete(false);
            }
        };
        document.addEventListener("mousedown", handleClick);
        document.addEventListener("keydown", handleEsc);
        return () => {
            document.removeEventListener("mousedown", handleClick);
            document.removeEventListener("keydown", handleEsc);
        };
    }, [panelOpen]);

    const handleSaveLang = async () => {
        setSaving(true);
        try {
            if (langValue.trim()) {
                await savePreferredLang(langValue.trim());
            } else {
                await clearPreferredLang();
            }
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        } finally {
            setSaving(false);
        }
    };

    const handleDeleteAccount = async () => {
        if (!confirmDelete) {
            setConfirmDelete(true);
            return;
        }
        await deleteAccount();
        await signOut({ redirect: false });
        setPanelOpen(false);
        setConfirmDelete(false);
    };

    if (status === "loading") {
        return (
            <div className="px-3 py-2">
                <div className="h-8 w-full rounded-lg bg-white/5 animate-pulse" />
            </div>
        );
    }

    if (status === "unauthenticated") {
        return (
            <div className="px-3 py-2 border-t border-white/10 mt-2">
                <button
                    onClick={() => signIn("google")}
                    className="w-full flex items-center justify-center gap-2.5 px-3 py-2 rounded-lg
                               text-sm text-slate-400 hover:text-yellow-300
                               hover:bg-white/5 border border-transparent hover:border-yellow-400/20
                               transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-yellow-400/50"
                >
                    <svg className="h-4 w-4" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                    </svg>
                    <span>Sign in with Google</span>
                </button>
            </div>
        );
    }

    const user = session!.user;
    const displayLang = prefs?.preferred_lang || null;

    return (
        <div className="px-3 py-2 border-t border-white/10 mt-2 relative" ref={panelRef}>
            <button
                onClick={() => setPanelOpen((v) => !v)}
                aria-expanded={panelOpen}
                aria-haspopup="true"
                aria-label="User settings"
                className="w-full flex items-center gap-3 px-2 py-2 rounded-lg
                           hover:bg-white/5 transition-colors group outline-none focus-visible:ring-2 focus-visible:ring-yellow-400/50"
            >
                {user.image ? (
                    <img
                        src={user.image}
                        alt=""
                        className="h-7 w-7 rounded-full ring-1 ring-white/10 group-hover:ring-yellow-400/40 transition-all flex-shrink-0"
                    />
                ) : (
                    <div className="h-7 w-7 rounded-full bg-blue-500/30 border border-blue-400/30 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-bold text-blue-300">
                            {(user.name ?? user.email ?? "?")[0].toUpperCase()}
                        </span>
                    </div>
                )}
                <div className="flex-1 min-w-0 text-left">
                    <p className="text-xs font-medium text-slate-300 truncate group-hover:text-yellow-300 transition-colors">
                        {user.name ?? user.email}
                    </p>
                    {displayLang && (
                        <p className="text-[10px] text-slate-500 truncate">{displayLang}</p>
                    )}
                </div>
                <Settings className={cn(
                    "h-3.5 w-3.5 text-slate-500 flex-shrink-0 transition-transform duration-300",
                    panelOpen ? "rotate-90 text-yellow-400" : "group-hover:text-slate-300"
                )} />
            </button>

            {panelOpen && (
                <div 
                    role="dialog"
                    aria-label="Preferences"
                    className="absolute bottom-0 left-full ml-4 w-72 rounded-xl border border-white/10 bg-[#0d1117]/95
                               backdrop-blur-xl overflow-visible shadow-2xl z-[100] animate-in fade-in slide-in-from-left-2 duration-200"
                >
                    {/* Header */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                            Interface Prefs
                        </span>
                        <button
                            onClick={() => { setPanelOpen(false); setConfirmDelete(false); }}
                            className="text-slate-500 hover:text-slate-300 transition-colors p-1"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    </div>

                    {/* Default language */}
                    <div className="p-4 border-b border-white/10">
                        <div className="flex items-center gap-2 mb-3">
                            <Globe className="h-3.5 w-3.5 text-amber-500" />
                            <span className="text-[11px] font-bold text-slate-300 uppercase tracking-tighter">Native Protocol</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <select
                                value={langValue}
                                onChange={(e) => setLangValue(e.target.value)}
                                className="flex-1 text-xs bg-black/40 text-slate-200 rounded-lg px-2 py-2
                                           border border-white/10 focus:border-yellow-400/50 outline-none
                                           focus:ring-1 focus:ring-yellow-400/30 cursor-pointer"
                            >
                                <option value="">Auto-Detect (Original)</option>
                                {COMMON_LANGUAGES.map((lang) => (
                                    <option key={lang} value={lang}>{lang}</option>
                                ))}
                            </select>
                            
                            {/* Fixed chopped button by ensuring enough width and consistent padding */}
                            <button
                                onClick={handleSaveLang}
                                disabled={saving || langValue === (prefs?.preferred_lang ?? "")}
                                className="h-8 min-w-[60px] flex items-center justify-center rounded-lg text-[10px] font-black uppercase tracking-widest
                                           bg-amber-500/10 text-amber-500 border border-amber-500/30
                                           hover:bg-amber-500/20 disabled:opacity-20 disabled:cursor-not-allowed
                                           transition-all active:scale-95"
                            >
                                {saved ? <Check className="h-3.5 w-3.5" /> : saving ? "..." : "Save"}
                            </button>
                        </div>
                        {displayLang && (
                            <p className="text-[10px] text-slate-500 mt-3 italic leading-tight">
                                Intelligence will auto-translate to {displayLang} on load.
                            </p>
                        )}
                    </div>

                    {/* Bottom Actions */}
                    <div className="p-2 space-y-1">
                        <button
                            onClick={() => signOut({ redirect: false }).then(() => setPanelOpen(false))}
                            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest
                                       text-slate-400 hover:text-white hover:bg-white/5 transition-all outline-none"
                        >
                            <LogOut className="h-3.5 w-3.5" />
                            Sign out
                        </button>
                        <button
                            onClick={handleDeleteAccount}
                            className={cn(
                                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all",
                                confirmDelete
                                    ? "bg-red-500/10 text-red-400 border border-red-500/20"
                                    : "text-slate-600 hover:text-red-400 hover:bg-red-500/5"
                            )}
                        >
                            <Trash2 className="h-3.5 w-3.5" />
                            {confirmDelete ? "Confirm Identity Purge" : "Purge Data"}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
