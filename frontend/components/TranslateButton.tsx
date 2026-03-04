"use client";

/**
 * Arc Codex — TranslateButton.tsx
 *
 * Drop-in translation control for IntelligenceCard.tsx.
 * Fetches /api/translate/{id}?lang=X, replaces displayed fields,
 * and supports RTL languages + "Show original" toggle.
 *
 * v3 — Always shows Translate button. Accumulates language pills
 * for every cached translation (backend + session).
 * Preferred lang skips to dropdown if already English.
 * "Original" reset pill instead of confusing "EN".
 * AbortController for in-flight cancel.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useUserPrefs } from "@/components/UserPrefsContext";
import { cn } from "@/lib/utils";

// ── Types ────────────────────────────────────────────────────────────────────

export interface TranslatedFields {
  title?: string;
  original_text?: string;
  red_team_analysis?: string;
  blue_team_analysis?: string;
  purple_team_analysis?: string;
}

interface TranslateButtonProps {
  articleId: string;
  /** Languages the backend already has cached (from card.cached_langs) */
  cachedLangs?: string[];
  onTranslated: (fields: TranslatedFields, rtl: boolean) => void;
  onReset: () => void;
  onLangChange?: (lang: string | null) => void;
}

const COMMON_LANGUAGES = [
  "Arabic",
  "Bengali",
  "Chinese (Simplified)",
  "Chinese (Traditional)",
  "Dutch",
  "English",
  "French",
  "German",
  "Greek",
  "Hindi",
  "Indonesian",
  "Italian",
  "Japanese",
  "Korean",
  "Malay",
  "Persian",
  "Polish",
  "Portuguese",
  "Russian",
  "Spanish",
  "Swahili",
  "Swedish",
  "Tamil",
  "Telugu",
  "Thai",
  "Turkish",
  "Ukrainian",
  "Urdu",
  "Vietnamese",
];

const RTL_LANGS = ["Arabic", "Persian", "Urdu", "Hebrew"];

// ── Main Component ───────────────────────────────────────────────────────────

export default function TranslateButton({
  articleId,
  cachedLangs = [],
  onTranslated,
  onReset,
  onLangChange,
}: TranslateButtonProps) {
  const { prefs } = useUserPrefs();
  const [isOpen, setIsOpen] = useState(false);
  const [loadingLang, setLoadingLang] = useState<string | null>(null);
  const [activeLang, setActiveLang] = useState<string | null>(null);

  /**
   * sessionCached stores languages translated during THIS session.
   * This ensures that if a user translates to "French", the French pill
   * stays visible even if the backend hasn't globally cached it yet.
   */
  const [sessionCached, setSessionCached] = useState<string[]>([]);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Combine backend cache + current session cache
  const allCached = Array.from(new Set([...cachedLangs, ...sessionCached]));

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        handleClose();
      }
    };

    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleEsc);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEsc);
    };
  }, [isOpen, handleClose]);

  /**
   * Logic for Keyboard Navigation within the dropdown
   */
  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const first = listRef.current?.querySelector("button");
      (first as HTMLElement)?.focus();
    }
    if (e.key === "Tab") {
      setIsOpen(false);
    }
  };

  const handleTranslate = async (lang: string) => {
    if (lang === activeLang) return;
    setIsOpen(false);

    // Cancel in-flight translation if user swaps quickly
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoadingLang(lang);

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
      const res = await fetch(
        `${backendUrl}/api/translate/${encodeURIComponent(
          articleId
        )}?lang=${encodeURIComponent(lang)}`,
        {
          signal: controller.signal,
        }
      );

      if (!res.ok) {
        throw new Error(`Translate API error: ${res.status}`);
      }

      const data = await res.json();

      // Check if language is RTL
      const isRtl = RTL_LANGS.includes(lang) || !!data.rtl;

      // Pass translated fields back to parent
      onTranslated(data, isRtl);
      setActiveLang(lang);
      if (onLangChange) onLangChange(lang);

      // Add to session cache so the pill appears immediately
      setSessionCached((prev) => Array.from(new Set([...prev, lang])));
    } catch (err: any) {
      if (err.name === "AbortError") {
        console.log("Translation aborted for:", lang);
      } else {
        console.error("Translation error:", err);
      }
    } finally {
      // Only clear loading state if this was the latest request
      if (abortControllerRef.current === controller) {
        setLoadingLang(null);
      }
    }
  };

  const handleResetInternal = () => {
    setActiveLang(null);
    onReset();
    if (onLangChange) onLangChange(null);
    setIsOpen(false);
  };

  const toggleDropdown = () => {
    const pref = prefs?.preferred_lang;

    /**
     * SMART SKIP LOGIC:
     * If the user has a preferred language set (and it's not English),
     * and we aren't already viewing a translation,
     * and that language isn't already in the cached pills list...
     * ...trigger the translation immediately on the first click.
     */
    if (
      !isOpen &&
      pref &&
      pref !== "English" &&
      !activeLang &&
      !allCached.includes(pref)
    ) {
      handleTranslate(pref);
      return;
    }

    setIsOpen(!isOpen);
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <div className="flex flex-wrap items-center gap-2">
        {/* The Primary "Translate" Trigger */}
        <button
          onClick={toggleDropdown}
          onKeyDown={handleKeydown}
          aria-haspopup="true"
          aria-expanded={isOpen}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all outline-none focus-visible:ring-2 focus-visible:ring-amber-500",
            isOpen || activeLang
              ? "bg-amber-500 text-black shadow-[0_0_12px_rgba(245,158,11,0.4)]"
              : "bg-white/5 text-slate-400 hover:bg-white/10 border border-white/5"
          )}
        >
          {loadingLang ? (
            <svg
              className="h-3.5 w-3.5 animate-spin text-current"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
          ) : (
            <GlobeIcon />
          )}
          <span>{activeLang ? activeLang : "Translate"}</span>
        </button>

        {/* Reset / Original Toggle (Only shows when a translation is active) */}
        {activeLang && (
          <button
            onClick={handleResetInternal}
            className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-slate-500 text-[10px] font-bold uppercase tracking-widest hover:text-white hover:bg-white/10 transition-all outline-none focus-visible:ring-2 focus-visible:ring-white"
            aria-label="Show original text"
          >
            Original
          </button>
        )}

        {/* Cached Language Pills - Allows user to swap between translations instantly */}
        {allCached
          .filter((l) => l !== activeLang)
          .map((lang) => (
            <button
              key={lang}
              onClick={() => handleTranslate(lang)}
              disabled={!!loadingLang}
              className="px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[10px] font-bold uppercase tracking-widest hover:bg-blue-500/20 transition-all disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
            >
              {loadingLang === lang ? (
                <span className="flex items-center gap-1">
                   <Spinner /> {lang}
                </span>
              ) : (
                lang
              )}
            </button>
          ))}
      </div>

      {/* The Protocol Dropdown */}
      {isOpen && (
        <div
          className="absolute left-0 mt-2 z-[60] w-52 rounded-xl border border-white/10 bg-[#0a0a0a]/95 shadow-2xl overflow-hidden backdrop-blur-xl animate-in fade-in zoom-in-95 duration-100"
          role="menu"
          aria-orientation="vertical"
        >
          <div className="p-3 border-b border-white/5 bg-white/[0.02]">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">
              Protocol
            </span>
          </div>
          <ul
            ref={listRef}
            className="max-h-64 overflow-y-auto p-1 custom-scrollbar"
            role="none"
          >
            {COMMON_LANGUAGES.filter((l) => l !== "English").map((lang) => (
              <li key={lang} role="none">
                <button
                  role="menuitem"
                  onClick={() => handleTranslate(lang)}
                  className={cn(
                    "w-full text-left px-3 py-2.5 rounded-lg text-xs font-bold transition-all flex items-center justify-between group outline-none focus:bg-amber-500/10 focus:text-amber-400",
                    activeLang === lang
                      ? "bg-amber-500/10 text-amber-400"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  )}
                >
                  <span>{lang}</span>
                  {allCached.includes(lang) && (
                    <span className="text-[8px] px-1.5 py-0.5 rounded-md bg-blue-500/10 text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity">
                      Cached
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Micro-icons ───────────────────────────────────────────────────────────────

function GlobeIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg
      className="h-3 w-3 animate-spin"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
        fill="none"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
