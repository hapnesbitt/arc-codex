"use client";

/**
 * Arc Codex — TranslateButton.tsx
 *
 * v4 — languages.json replaces hardcoded list (158 languages).
 *      English included in dropdown (valid target for foreign-language articles).
 *      Accessibility pass: aria-label states, aria-controls, aria-hidden on SVGs,
 *      focus management, listbox role alignment.
 *
 * v4.1 — cached-language pills sit alongside the icon trigger, with a
 *        dedicated "Original" pill that surfaces the revert path. The
 *        "Show original" list item at the top of the 158-language dropdown
 *        was the only way back before, and on mobile it was buried behind
 *        a scroll — the pill makes it a one-tap action. Pill styling
 *        matches the Huntaegis TranslateButton, which is the working
 *        reference for this pattern.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useUserPrefs } from "@/components/UserPrefsContext";
import { cn } from "@/lib/utils";
import LANGUAGES from "@/lib/languages.json";

// ── Types ─────────────────────────────────────────────────────────────────────

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
  /** Detected language of the article (from scribe langdetect) */
  sourceLang?: string | null;
  onTranslated: (fields: TranslatedFields, rtl: boolean) => void;
  onReset: () => void;
  onLangChange?: (lang: string | null) => void;
}

// Language display names for the dropdown (all 158, sorted A→Z by name)
const LANGUAGE_NAMES = LANGUAGES.map((l) => l.name);

const RTL_LANGS = new Set(["Arabic", "Persian", "Urdu", "Hebrew", "Pashto", "Sindhi", "Uyghur", "Divehi", "Yiddish", "Kurdish"]);

// ── Main Component ────────────────────────────────────────────────────────────

export default function TranslateButton({
  articleId,
  cachedLangs = [],
  sourceLang = null,
  onTranslated,
  onReset,
  onLangChange,
}: TranslateButtonProps) {
  const { prefs } = useUserPrefs();
  const [isOpen, setIsOpen]             = useState(false);
  const [loadingLang, setLoadingLang]   = useState<string | null>(null);
  const [activeLang, setActiveLang]     = useState<string | null>(null);
  const [sessionCached, setSessionCached] = useState<string[]>([]);

  const dropdownRef  = useRef<HTMLDivElement>(null);
  const triggerRef   = useRef<HTMLButtonElement>(null);
  const listRef      = useRef<HTMLUListElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const dropdownId   = `translate-menu-${articleId}`;

  // Combine backend cache + current session cache
  const allCached = Array.from(new Set([...cachedLangs, ...sessionCached]));

  const handleClose = useCallback(() => {
    setIsOpen(false);
    triggerRef.current?.focus();
  }, []);

  // Close on outside click or Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        handleClose();
      }
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEsc);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEsc);
    };
  }, [isOpen, handleClose]);

  // Arrow key navigation: down from trigger focuses first item in list
  const handleTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && isOpen) {
      e.preventDefault();
      const first = listRef.current?.querySelector("button");
      (first as HTMLElement)?.focus();
    }
    if (e.key === "Tab") {
      setIsOpen(false);
    }
  };

  // Arrow key navigation within list
  const handleListKeyDown = (e: React.KeyboardEvent<HTMLUListElement>) => {
    const items = Array.from(
      listRef.current?.querySelectorAll("button") ?? []
    ) as HTMLElement[];
    const current = document.activeElement as HTMLElement;
    const idx = items.indexOf(current);

    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[idx + 1]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (idx === 0) {
        triggerRef.current?.focus();
      } else {
        items[idx - 1]?.focus();
      }
    } else if (e.key === "Tab") {
      setIsOpen(false);
    }
  };

  const handleTranslate = async (lang: string) => {
    if (lang === activeLang) return;
    setIsOpen(false);

    // Cancel any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoadingLang(lang);

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
      const res = await fetch(
        `${backendUrl}/api/translate/${encodeURIComponent(articleId)}?lang=${encodeURIComponent(lang)}`,
        { signal: controller.signal }
      );

      if (!res.ok) throw new Error(`Translate API error: ${res.status}`);

      const data = await res.json();
      const isRtl = RTL_LANGS.has(lang) || !!data.rtl;

      onTranslated(data, isRtl);
      setActiveLang(lang);
      onLangChange?.(lang);
      setSessionCached((prev) => Array.from(new Set([...prev, lang])));
    } catch (err: any) {
      if (err.name === "AbortError") {
        console.log("Translation aborted for:", lang);
      } else {
        console.error("Translation error:", err);
      }
    } finally {
      if (abortControllerRef.current === controller) {
        setLoadingLang(null);
      }
    }
  };

  const handleReset = () => {
    setActiveLang(null);
    onReset();
    onLangChange?.(null);
    setIsOpen(false);
  };

  const toggleDropdown = () => {
    const pref = prefs?.preferred_lang;

    // Smart fire: if user has a preferred lang AND article is in a different language,
    // translate immediately instead of opening the picker.
    // Works for English users reading foreign articles too.
    if (!isOpen && !activeLang && pref) {
      const articleLang = sourceLang || "English";
      if (pref !== articleLang) {
        // Use cached version if available, otherwise fetch
        if (allCached.includes(pref)) {
          handleTranslate(pref);
        } else {
          handleTranslate(pref);
        }
        return;
      }
    }

    setIsOpen((prev) => !prev);
  };

  // Compute accessible label for the trigger button
  const triggerLabel = loadingLang
    ? `Translating to ${loadingLang}`
    : activeLang
    ? `Translated to ${activeLang}. Click to change language`
    : "Translate article";

  // Pills sit next to the icon trigger. `Original` reverts to source and is
  // rendered only when a translation is active. Cached-language pills give a
  // one-tap route to every language the backend already has stored for this
  // article, minus whichever one is active. When neither is present the wrapper
  // stays inline-block so the icon slots into the parent's icon grid the same
  // way it always has.
  const otherCached = allCached.filter((l) => l !== activeLang);
  const hasPills = !!activeLang || otherCached.length > 0;

  return (
    <div
      className={cn(
        "relative",
        hasPills
          ? "col-span-full flex flex-wrap items-center gap-2"
          : "inline-block"
      )}
      ref={dropdownRef}
    >
      {/* Trigger — icon-only, matches the action-row pattern */}
      <button
        ref={triggerRef}
        onClick={toggleDropdown}
        onKeyDown={handleTriggerKeyDown}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={dropdownId}
        aria-label={triggerLabel}
        data-tooltip="Translate this article and its A.R.C. analysis into another language — cached translations load instantly, new ones take a moment."
        disabled={!!loadingLang}
        className={cn(
          "inline-flex items-center justify-center h-10 w-10 rounded-sm transition-colors ring-focus disabled:cursor-wait",
          activeLang || loadingLang
            ? "text-emerald-400 hover:text-emerald-300 hover:bg-slate-800/40"
            : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/40"
        )}
      >
        {loadingLang ? (
          <Spinner aria-hidden="true" />
        ) : (
          <GlobeIcon aria-hidden="true" />
        )}
      </button>

      {/* Original pill — visible only while a translation is active. This is
          the fast path back to source, replacing the "Show original" row that
          used to sit at the top of the 158-language scroll list. */}
      {activeLang && (
        <button
          onClick={handleReset}
          aria-label="Show original text"
          className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-slate-400 text-[10px] font-bold uppercase tracking-widest hover:text-white hover:bg-white/10 transition-all outline-none focus-visible:ring-2 focus-visible:ring-white"
        >
          Original
        </button>
      )}

      {/* Cached-language pills. Excludes the active language (the pill would
          be a no-op) and disables interaction while any translation is in
          flight, so the abort-and-refetch dance stays predictable. */}
      {otherCached.map((lang) => (
        <button
          key={lang}
          onClick={() => handleTranslate(lang)}
          disabled={!!loadingLang}
          aria-label={
            loadingLang === lang
              ? `Translating to ${lang}`
              : `Switch to ${lang} translation`
          }
          aria-busy={loadingLang === lang}
          className="px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[10px] font-bold uppercase tracking-widest hover:bg-blue-500/20 transition-all disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
        >
          {loadingLang === lang ? (
            <span className="flex items-center gap-1">
              <Spinner aria-hidden="true" />
              <span>{lang}</span>
            </span>
          ) : (
            lang
          )}
        </button>
      ))}

      {/* Dropdown menu */}
      {isOpen && (
        <div
          id={dropdownId}
          role="menu"
          aria-label="Select language"
          aria-orientation="vertical"
          className="absolute right-0 mt-2 z-[60] w-52 rounded-xl border border-white/10 bg-[#0a0a0a]/95 shadow-2xl overflow-hidden backdrop-blur-xl animate-in fade-in zoom-in-95 duration-100"
        >
          <div className="p-3 border-b border-white/5 bg-white/[0.02]" aria-hidden="true">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">
              Protocol
            </span>
          </div>
          <ul
            ref={listRef}
            onKeyDown={handleListKeyDown}
            className="max-h-64 overflow-y-auto p-1 custom-scrollbar"
            role="none"
          >
            {/* No "Show original" entry here — the Original pill outside the
                dropdown covers that path and is always in view, so hiding a
                copy of it at the top of a 158-item scroll would just be the
                bug this component is fixing. */}
            {LANGUAGE_NAMES.map((lang) => (
              <li key={lang} role="none">
                <button
                  role="menuitem"
                  onClick={() => handleTranslate(lang)}
                  aria-label={
                    allCached.includes(lang)
                      ? `${lang} (cached)`
                      : lang
                  }
                  className={cn(
                    "w-full text-left px-3 py-2.5 rounded-lg text-xs font-bold transition-all flex items-center justify-between group outline-none focus:bg-amber-500/10 focus:text-amber-400",
                    activeLang === lang
                      ? "bg-amber-500/10 text-amber-400"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  )}
                >
                  <span>{lang}</span>
                  {allCached.includes(lang) && (
                    <span
                      className="text-[8px] px-1.5 py-0.5 rounded-md bg-blue-500/10 text-blue-400 opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity"
                      aria-hidden="true"
                    >
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

function GlobeIcon({ ...props }: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function Spinner({ ...props }: React.SVGProps<SVGSVGElement>) {
  return (
    <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" {...props}>
      <circle
        className="opacity-25"
        cx="12" cy="12" r="10"
        stroke="currentColor" strokeWidth="4" fill="none"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}
