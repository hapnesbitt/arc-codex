// File: /frontend/app/ClientLayout.tsx
// VERSION: v4 — Removed local auth (/api/me), login uses signIn() provider picker
// MODIFICATION: Set mobile responsive horizontal padding to px-0 so cards render edge-to-edge on small viewports.

'use client';

import React, { useState, useEffect, useRef, ReactNode } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BookOpen, Send, Search, Activity, Home, LogIn,
  X, Globe, Check, AlertCircle, Trash2, Shield, Library, Film, Rss, BookText,
} from 'lucide-react';
import { cn } from "@/lib/utils";
import styles from './LayoutTheme.module.css';
import { SessionProvider, useSession, signIn, signOut } from "next-auth/react";
import { UserPrefsProvider, useUserPrefs } from "@/components/UserPrefsContext";
import UserMenu from '@/components/UserMenu';
import LANGUAGES from '@/lib/languages.json';

// ---------------------------------------------------------------------------
// MobileAuthButton
// ---------------------------------------------------------------------------

const MobileAuthButton = () => {
  const { data: session, status } = useSession();
  const { prefs, savePreferredLang, clearPreferredLang, deleteAccount } = useUserPrefs();
  const [isOpen, setIsOpen]               = useState(false);
  const [tempLang, setTempLang]           = useState("");
  const [isSaving, setIsSaving]           = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [isDeleting, setIsDeleting]       = useState(false);
  const [deleteError, setDeleteError]     = useState<string | null>(null);
  const closeButtonRef  = useRef<HTMLButtonElement>(null);
  const triggerRef      = useRef<HTMLButtonElement>(null);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listboxRef      = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTempLang(prefs?.preferred_lang ?? "");
      setTimeout(() => closeButtonRef.current?.focus(), 50);
    }
  }, [isOpen, prefs?.preferred_lang]);

  useEffect(() => {
    return () => { if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current); };
  }, []);

  const closeSheet = () => {
    setIsOpen(false);
    setConfirmDelete(false);
    setDeleteError(null);
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeSheet(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen]);

  if (status === 'loading') return null;

  const handleCommitChanges = async () => {
    setIsSaving(true);
    try {
      tempLang.trim() ? await savePreferredLang(tempLang.trim()) : await clearPreferredLang();
      setTimeout(() => closeSheet(), 300);
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setIsSaving(false);
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
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount();
      await signOut({ redirect: false });
      closeSheet();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete account. Please try again.");
      setConfirmDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancelDelete = () => {
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    setConfirmDelete(false);
    setDeleteError(null);
  };

  if (status === 'authenticated' && session?.user?.image) {
    return (
      <>
        <button
          ref={triggerRef}
          onClick={() => setIsOpen(true)}
          className="group relative flex flex-col items-center flex-1 outline-none"
          aria-label="Open settings"
          aria-expanded={isOpen}
          aria-haspopup="dialog"
        >
          <motion.div
            whileHover={{ y: -5 }}
            className="relative rounded-xl p-1.5 transition-all bg-black/40 border border-white/5 group-ring-focus"
          >
            <Image
              src={session.user.image}
              alt=""
              width={24}
              height={24}
              className="rounded-full ring-1 ring-amber-400/40"
            />
          </motion.div>
          <span className="mt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 group-hover:text-slate-300" aria-hidden="true">
            Settings
          </span>
        </button>

        <AnimatePresence>
          {isOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                onClick={closeSheet}
                className="fixed inset-0 bg-black/90 backdrop-blur-md z-[150]"
                aria-hidden="true"
              />

              <motion.div
                role="dialog"
                aria-modal="true"
                aria-labelledby="uplink-title"
                initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
                transition={{ type: "spring", damping: 25, stiffness: 200 }}
                className="fixed bottom-0 left-0 right-0 bg-[#0a0a0a] border-t border-white/10 rounded-t-3xl p-6 z-[200] flex flex-col max-h-[90vh]"
              >
                <div className="flex justify-between items-center mb-6">
                  <span id="uplink-title" className="text-[10px] font-black uppercase tracking-[0.3em] text-amber-500">
                    Interface Uplink
                  </span>
                  <button
                    ref={closeButtonRef}
                    onClick={closeSheet}
                    className="p-2 bg-white/5 rounded-full text-slate-400 hover:text-white transition-colors ring-focus"
                    aria-label="Close settings"
                  >
                    <X size={20} aria-hidden="true" />
                  </button>
                </div>

                <div className="flex items-center gap-2 mb-4 text-slate-400" aria-hidden="true">
                  <Globe size={14} />
                  <span className="text-[10px] font-bold uppercase tracking-wider">Select Language</span>
                </div>

                <div
                  ref={listboxRef}
                  role="listbox"
                  aria-label="Select preferred language"
                  aria-activedescendant={tempLang ? `lang-opt-${tempLang.replace(/\s+/g, '-')}` : undefined}
                  tabIndex={0}
                  className="flex-1 overflow-y-auto pr-2 mb-6 space-y-1 custom-scrollbar ring-focus rounded-xl"
                  style={{ maxHeight: '350px' }}
                  onKeyDown={(e) => {
                    const idx = tempLang ? LANGUAGES.findIndex(l => l.name === tempLang) : -1;
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      const next = Math.min(idx + 1, LANGUAGES.length - 1);
                      setTempLang(LANGUAGES[next].name);
                      document.getElementById(`lang-opt-${LANGUAGES[next].name.replace(/\s+/g, '-')}`)?.scrollIntoView({ block: 'nearest' });
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      const prev = Math.max(idx - 1, 0);
                      setTempLang(LANGUAGES[prev].name);
                      document.getElementById(`lang-opt-${LANGUAGES[prev].name.replace(/\s+/g, '-')}`)?.scrollIntoView({ block: 'nearest' });
                    } else if (e.key === 'Home') {
                      e.preventDefault();
                      setTempLang(LANGUAGES[0].name);
                      document.getElementById(`lang-opt-${LANGUAGES[0].name.replace(/\s+/g, '-')}`)?.scrollIntoView({ block: 'nearest' });
                    } else if (e.key === 'End') {
                      e.preventDefault();
                      setTempLang(LANGUAGES[LANGUAGES.length - 1].name);
                      document.getElementById(`lang-opt-${LANGUAGES[LANGUAGES.length - 1].name.replace(/\s+/g, '-')}`)?.scrollIntoView({ block: 'nearest' });
                    }
                  }}
                >
                  {LANGUAGES.map(({ code, name }) => (
                    <button
                      key={code}
                      id={`lang-opt-${name.replace(/\s+/g, '-')}`}
                      role="option"
                      aria-selected={tempLang === name}
                      onClick={() => setTempLang(name)}
                      tabIndex={-1}
                      className={cn(
                        "w-full text-left px-4 py-2.5 rounded-xl text-sm transition-all",
                        tempLang === name
                          ? "bg-amber-500/20 text-amber-300 font-bold"
                          : "text-slate-400 hover:bg-white/5 hover:text-white"
                      )}
                    >
                      {name}
                    </button>
                  ))}
                </div>

                <div className="border-t border-white/10 pt-4">
                  <button
                    onClick={handleCommitChanges}
                    disabled={isSaving}
                    aria-busy={isSaving}
                    className="w-full py-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-black uppercase tracking-widest hover:bg-amber-500/20 disabled:opacity-50 transition-colors mb-3 ring-focus"
                  >
                    {isSaving ? "Saving..." : "Save Preference"}
                  </button>

                  {deleteError && (
                    <div role="alert" className="flex items-start gap-2 px-3 py-2 mb-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-[10px]">
                      <AlertCircle size={14} className="flex-shrink-0 mt-0.5" aria-hidden="true" />
                      <span>{deleteError}</span>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <button
                      onClick={() => signOut()}
                      className="py-4 rounded-xl bg-white/5 border border-white/10 text-slate-400 text-[10px] font-bold uppercase tracking-widest hover:bg-white/10 transition-colors ring-focus"
                    >
                      Sign Out
                    </button>

                    {confirmDelete ? (
                      <div className="grid grid-cols-2 gap-1">
                        <button
                          onClick={handleDeleteConfirmed}
                          disabled={isDeleting}
                          aria-label={isDeleting ? "Deleting account" : "Confirm account deletion"}
                          aria-busy={isDeleting}
                          className="py-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-bold uppercase tracking-widest hover:bg-red-500/20 disabled:opacity-50 disabled:cursor-wait transition-colors focus-visible:ring-2 focus-visible:ring-red-400/50 outline-none flex items-center justify-center gap-1"
                        >
                          <Trash2 size={12} aria-hidden="true" />
                          {isDeleting ? "..." : "Confirm"}
                        </button>
                        <button
                          onClick={handleCancelDelete}
                          disabled={isDeleting}
                          aria-label="Cancel account deletion"
                          className="py-4 rounded-xl bg-white/5 border border-white/10 text-slate-400 text-[10px] font-bold uppercase tracking-widest hover:bg-white/10 disabled:opacity-50 transition-colors ring-focus"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={handleDeleteClick}
                        aria-label="Delete account data"
                        className="py-4 rounded-xl bg-red-500/5 border border-red-500/10 text-red-400 text-[10px] font-bold uppercase tracking-widest hover:bg-red-500/10 transition-colors focus-visible:ring-2 focus-visible:ring-red-400/50 outline-none"
                      >
                        Purge
                      </button>
                    )}
                  </div>
                </div>
                <div className="h-4" />
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </>
    );
  }

  return (
    <div className="group relative flex flex-col items-center flex-1">
      <button
        onClick={() => signIn()}
        className="group relative flex flex-col items-center outline-none"
        aria-label="Sign in"
      >
        <motion.div
          whileHover={{ y: -5 }}
          className="relative rounded-xl p-3 transition-all bg-black/40 border border-white/5 hover:bg-white/5 group-ring-focus"
        >
          <LogIn size={20} className="text-slate-500 group-hover:text-amber-400" aria-hidden="true" />
        </motion.div>
        <span className="mt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 group-hover:text-amber-400" aria-hidden="true">
          Sign In
        </span>
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------
// SidebarContent
// ---------------------------------------------------------------------------

const SidebarContent = ({ isMobile = false }: { isMobile?: boolean }) => {
  const pathname = usePathname();
  const { data: session } = useSession();
  const isAuthed = !!session?.user;

  // One voice: nav icons recede to slate; amber marks the one true
  // action (Publish). Active state is slate + hairline rail, not color.
  const links = [
    ...(isMobile ? [{ href: "/",      icon: <Home     size={20}             aria-hidden="true" />, label: "Home",    color: "text-slate-400" }] : []),
    {               href: "/search",  icon: <Search   size={isMobile?20:22} aria-hidden="true" />, label: "Search",  color: "text-slate-400" },
    {               href: "/publish", icon: <Send     size={isMobile?20:22} aria-hidden="true" />, label: "Publish", color: "text-amber-400" },
    ...(isAuthed ? [{ href: "https://vid.arc-codex.com", icon: <Film size={isMobile?20:22} aria-hidden="true" />, label: "Video", color: "text-slate-400" }] : []),
    {               href: "/wiki",    icon: <Library  size={isMobile?20:22} aria-hidden="true" />, label: "Wiki",    color: "text-slate-400" },
    {               href: "/library", icon: <BookText size={isMobile?20:22} aria-hidden="true" />, label: "Library", color: "text-slate-400" },
    {               href: "/sources", icon: <Rss      size={isMobile?20:22} aria-hidden="true" />, label: "Sources", color: "text-slate-400" },
    {               href: "/about",   icon: <BookOpen size={isMobile?20:22} aria-hidden="true" />, label: "More",    color: "text-slate-400" },
  ];

  return (
    <div className={cn("flex h-full w-full relative items-center", isMobile ? "flex-row justify-around px-2" : "flex-col py-8")}>
      {!isMobile && (
        <div className="mb-12">
          <Link
            href="/"
            aria-label="Arc Codex Home"
            onClick={() => document.getElementById('main-content')?.scrollTo({ top: 0, behavior: 'smooth' })}
          >
            <img
              src="/arc-codex-logo.jpg"
              alt="Arc Codex"
              className="w-16 h-16 rounded-xl object-cover opacity-90 hover:opacity-100 transition-opacity cursor-pointer mx-auto"
            />
          </Link>
        </div>
      )}

      <nav
        className={cn("flex items-center w-full", isMobile ? "flex-row justify-between" : "flex-col gap-8")}
        aria-label={isMobile ? "Mobile navigation" : "Main navigation"}
      >
        {links.map((link, idx) => {
          const isActive = pathname === link.href;
          const isExternal = link.href.startsWith('http');
          const inner = (
            <>
              <motion.div
                whileHover={{ y: isMobile ? -5 : -2 }}
                className={cn(
                  "relative rounded-xl p-3 transition-all group-ring-focus",
                  isActive
                    ? "bg-white/10 border border-white/20"
                    : "bg-black/40 border border-white/5"
                )}
              >
                <div className={cn("relative z-10", isActive ? "text-slate-100" : link.color)}>
                  {link.icon}
                </div>
              </motion.div>
              <span className={cn("mt-2 font-sans text-[10px] uppercase tracking-[0.25em]", isActive ? "text-slate-100" : "text-slate-500 group-hover:text-slate-300")}>
                {link.label}
              </span>
            </>
          );

          // "You are here" — hairline rail, not color: left edge on the
          // desktop sidebar, top edge on the mobile bottom bar.
          // Transparent placeholder keeps geometry stable across routes.
          const navItemClass = cn(
            "group relative flex flex-col items-center flex-1 outline-none",
            isMobile
              ? (isActive ? "border-t-2 border-slate-400" : "border-t-2 border-transparent")
              : cn("w-full", isActive ? "border-l-2 border-slate-400" : "border-l-2 border-transparent")
          );

          return isExternal ? (
            <a
              key={idx}
              href={link.href}
              className={navItemClass}
              aria-label={link.label}
            >
              {inner}
            </a>
          ) : (
            <Link
              key={idx}
              href={link.href}
              className={navItemClass}
              aria-current={isActive ? "page" : undefined}
              onClick={isActive ? (e: React.MouseEvent) => {
                e.preventDefault();
                document.getElementById('main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
              } : undefined}
            >
              {inner}
            </Link>
          );
        })}
        {isMobile && <MobileAuthButton />}
      </nav>

      {!isMobile && (
        <div className="mt-auto flex flex-col items-center w-full gap-3">
          <UserMenu />
          <Activity size={16} className="text-amber-500 animate-pulse opacity-20" aria-hidden="true" />
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// ClientLayout
// ---------------------------------------------------------------------------

export default function ClientLayout({ children }: { children: ReactNode }) {
  const mainScrollRef = useRef<HTMLElement>(null);

  return (
    <SessionProvider>
      <UserPrefsProvider>
        <div className={cn(styles.wrapper, "bg-[#040404] min-h-screen text-slate-200 font-sans")}>

          <a
            href="#main-content"
            className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-4 focus-visible:left-4 focus-visible:z-[100] focus-visible:px-4 focus-visible:py-2 focus-visible:bg-amber-500 focus-visible:text-black focus-visible:font-bold focus-visible:rounded-lg focus-visible:ring-2 focus-visible:ring-white"
          >
            Skip to content
          </a>

          <aside
            className="hidden md:flex fixed top-0 left-0 z-50 h-full w-28 border-r border-white/5 bg-black/60 backdrop-blur-2xl shadow-2xl"
            aria-label="Desktop sidebar"
          >
            <SidebarContent />
          </aside>

          <aside
            className="flex md:hidden fixed bottom-0 left-0 right-0 z-50 h-24 border-t border-white/10 bg-black/90 backdrop-blur-2xl shadow-[0_-10px_30px_rgba(0,0,0,0.5)]"
            aria-label="Mobile navigation"
          >
            <SidebarContent isMobile={true} />
          </aside>

          <main
            id="main-content"
            ref={mainScrollRef}
            className={cn(styles.mainContent, "md:pl-28 pb-28 md:pb-0 relative transition-all outline-none")}
            tabIndex={-1}
          >
            {/* MODIFIED: px-6 changed to px-0 md:px-6 to flush inner items completely edge-to-edge on mobile display viewports */}
            <div className="max-w-6xl mx-auto px-0 md:px-6 py-6 md:py-10 relative z-10">
              {children}
            </div>
          </main>

        </div>
      </UserPrefsProvider>
    </SessionProvider>
  );
}