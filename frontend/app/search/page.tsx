// Filename: /frontend/app/search/page.tsx
// Arc Codex Search Page — v4.0
// Visual style matches developer/about pages:
//   - Dark card sections with colored border gradients + amber glow
//   - backdrop-blur, font-mono accents, amber/slate palette
//   - Radar pulse empty state
//   - Directive-colored result cards
// Accessibility: ARIA landmarks, live regions, focus-visible, reduced motion

'use client';

import React, { useState, useEffect, useCallback, Suspense, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, ArrowLeft, Clock, Newspaper, Zap, Shield, TrendingUp, Radio, Database, CalendarDays, Terminal, Globe, Tag, X } from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import LANG_LIST from '@/lib/languages.json';
import { escapeHtml } from '@/lib/textUtils';

// Solr highlighter wraps matched terms in these sentinels, not raw <mark>
// tags. Backend (main.py, /api/search route) sets hl.simple.pre/post to
// these exact strings. If either side changes, update the other.
const HL_PRE  = '⟪HL⟫';
const HL_POST = '⟪/HL⟫';
const HL_MARK_OPEN  = '<mark class="bg-amber-400/30 text-slate-100 px-0.5 rounded">';
const HL_MARK_CLOSE = '</mark>';

// Order matters: ALWAYS escape the raw snippet first, THEN restore the
// sentinels back to <mark> markup. Restoring first would allow any HTML
// in the article content to reach the DOM live.
const renderSnippet = (snippet: string): string =>
  escapeHtml(snippet).split(HL_PRE).join(HL_MARK_OPEN).split(HL_POST).join(HL_MARK_CLOSE);

// ── Reduced motion ────────────────────────────────────────────────────────────
const reducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false;

// ── Types ─────────────────────────────────────────────────────────────────────
interface SearchResult {
  id: string;
  title: string;
  source: string;
  url: string;
  timestamp: string;
  directive: string;
  chimera_score: number;
  snippet: string;
  score: number;
  source_lang?: string;
}

interface SearchResponse {
  query: string;
  total: number;
  offset: number;
  limit: number;
  results: SearchResult[];
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const formatRelativeTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffHours / 24);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch { return ''; }
};

const getDirectiveConfig = (directive: string) => {
  const d = directive?.toLowerCase() || '';
  if (d.includes('threat') || d.includes('intel'))
    return { icon: <Shield className="h-3 w-3" />, color: 'text-red-400', border: 'border-red-500/30', badgeBg: 'bg-red-500/10', accentBar: '#ef4444', glow: 'shadow-[0_0_20px_rgba(239,68,68,0.1)] hover:shadow-[0_0_35px_rgba(239,68,68,0.2)]' };
  if (d.includes('tech') || d.includes('surv'))
    return { icon: <Radio className="h-3 w-3" />, color: 'text-cyan-400', border: 'border-cyan-500/30', badgeBg: 'bg-cyan-500/10', accentBar: '#06b6d4', glow: 'shadow-[0_0_20px_rgba(6,182,212,0.1)] hover:shadow-[0_0_35px_rgba(6,182,212,0.2)]' };
  if (d.includes('econ') || d.includes('finance'))
    return { icon: <TrendingUp className="h-3 w-3" />, color: 'text-emerald-400', border: 'border-emerald-500/30', badgeBg: 'bg-emerald-500/10', accentBar: '#10b981', glow: 'shadow-[0_0_20px_rgba(16,185,129,0.1)] hover:shadow-[0_0_35px_rgba(16,185,129,0.2)]' };
  return { icon: <Zap className="h-3 w-3" />, color: 'text-amber-400', border: 'border-amber-500/30', badgeBg: 'bg-amber-500/10', accentBar: '#f59e0b', glow: 'shadow-[0_0_20px_rgba(245,158,11,0.1)] hover:shadow-[0_0_35px_rgba(245,158,11,0.2)]' };
};

const getChimeraColors = (score: number) => {
  // score is 0..1 from search; convert to 0-100 difficulty
  const pct = Math.round(score);
  if (pct < 30)  return { bar: 'bg-emerald-200', text: 'text-emerald-300', label: 'Elementary' };
  if (pct < 50)  return { bar: 'bg-emerald-400', text: 'text-emerald-300', label: 'High School' };
  if (pct < 60)  return { bar: 'bg-emerald-500', text: 'text-emerald-200', label: 'College' };
  if (pct < 70)  return { bar: 'bg-emerald-600', text: 'text-emerald-200', label: 'Graduate' };
  if (pct < 80)  return { bar: 'bg-emerald-700', text: 'text-emerald-100', label: 'Academic' };
  return         { bar: 'bg-emerald-900', text: 'text-emerald-100', label: 'Specialist' };
};

// ── Directive topics (from directives.json) ──────────────────────────────────
const DIRECTIVE_TOPICS: { topic: string; directives: string[] }[] = [
  { topic: 'Finance & Economics', directives: ['Economic Policy and Financial Markets', 'Corporate Actions and Labor Market'] },
  { topic: 'Technology & AI',     directives: ['AI Developments and Discourse', 'Consumer Tech & Electronics'] },
  { topic: 'Intelligence & Security', directives: ['Intelligence Community Operations', 'Crisis Event Monitoring', 'Epstein Case and Network'] },
  { topic: 'Governance & Policy', directives: ['Government Actions and Political Discourse', 'Major Legal and Supreme Court Developments', 'Anti-DEI Monitoring', 'Immigration Policy and News', 'Education Policy and Debates'] },
  { topic: 'Media & Information', directives: ['Media and Journalism Standards'] },
  { topic: 'Science & Environment', directives: ['Science, Math & Philosophy Insight', 'Climate and Environment', 'US Farming and Agriculture'] },
  { topic: 'General',             directives: ['General News, Culture & Lifestyle'] },
];

// Full ISO-639 language list, alphabetized for the filter dropdown.
// Shared with backend (backend/languages.json is a copy of this file).
const KNOWN_LANGUAGES = LANG_LIST.map(l => l.name).sort();

// ── Skeleton ──────────────────────────────────────────────────────────────────
function ResultSkeleton() {
  return (
    <div className="bg-slate-900/30 border border-white/5 rounded-2xl p-5 space-y-3 animate-pulse backdrop-blur-sm" aria-hidden="true">
      <div className="h-5 bg-slate-700/60 rounded-lg w-3/4" />
      <div className="space-y-2">
        <div className="h-3 bg-slate-700/40 rounded w-full" />
        <div className="h-3 bg-slate-700/40 rounded w-5/6" />
      </div>
      <div className="flex gap-3">
        <div className="h-3 bg-slate-700/30 rounded w-20" />
        <div className="h-3 bg-slate-700/30 rounded w-16" />
      </div>
    </div>
  );
}

// ── Result Card ───────────────────────────────────────────────────────────────
function ResultCard({ result }: { result: SearchResult; index: number }) {
  const chimera = result.chimera_score || 0;
  const chimeraColors = getChimeraColors(chimera);
  const chimeraPercent = Math.round(chimera);

  return (
    <Link
      href={`/article/${result.id}`}
      className="group block px-6 py-6 border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors ring-focus"
    >
      <div className="flex gap-6">
        <div className="flex-1 min-w-0 space-y-3">
          <h2 className="font-serif text-xl font-semibold text-slate-50 leading-snug tracking-tight line-clamp-2 group-hover:text-slate-100 transition-colors">
            {result.title}
          </h2>

          {result.snippet && (
            <p
              className="font-serif text-base text-slate-300 leading-relaxed line-clamp-2 arc-snippet"
              dangerouslySetInnerHTML={{ __html: renderSnippet(result.snippet) }}
            />
          )}

          <div className="flex items-center gap-4 flex-wrap font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
            {result.source && (
              <span>{result.source}</span>
            )}
            {result.timestamp && (
              <time dateTime={result.timestamp}>
                {formatRelativeTime(result.timestamp)}
              </time>
            )}
            {result.directive && (
              <span className="text-slate-400">
                {result.directive.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>

        {/* Chimera Difficulty column */}
        {chimera > 0 && (
          <div
            className="flex-shrink-0 flex flex-col items-center justify-center gap-1.5 w-14"
            title="Chimera Difficulty Score — synthesizes Flesch-Kincaid, Coleman-Liau, SMOG, and Dale-Chall readability metrics"
            aria-label={`Chimera score ${chimeraPercent}, ${chimeraColors.label}`}
          >
            <span className="font-sans text-[9px] font-semibold tracking-[0.2em] text-slate-500 uppercase" aria-hidden="true">Chimera</span>
            <span className={`text-xs font-bold tabular-nums font-mono ${chimeraColors.text}`} aria-hidden="true">{chimeraPercent}</span>
            <div className="w-1 h-12 bg-slate-800 overflow-hidden flex flex-col-reverse" aria-hidden="true">
              <div
                className={`w-full ${chimeraColors.bar}`}
                style={{ height: `${chimeraPercent}%` }}
              />
            </div>
            <span className={`font-sans text-[9px] font-semibold tracking-[0.15em] text-center leading-tight ${chimeraColors.text}`} aria-hidden="true">{chimeraColors.label}</span>
          </div>
        )}
      </div>
    </Link>
  );
}

// ── Radar Ring ────────────────────────────────────────────────────────────────
function RadarRing({ delay = 0 }: { delay?: number }) {
  if (reducedMotion) return null;
  return (
    <motion.div
      className="absolute inset-0 rounded-full border border-amber-500/20"
      initial={{ scale: 1, opacity: 0.4 }}
      animate={{ scale: 2.8, opacity: 0 }}
      transition={{ duration: 3.5, delay, repeat: Infinity, ease: 'easeOut' }}
      aria-hidden="true"
    />
  );
}

// ── Main Export ───────────────────────────────────────────────────────────────
export default function SearchPage() {
  return (
    <Suspense fallback={
      <PageWrapper>
        <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
          {[...Array(5)].map((_, i) => <ResultSkeleton key={i} />)}
        </div>
      </PageWrapper>
    }>
      <SearchPageContent />
    </Suspense>
  );
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialQuery = searchParams.get('q') || '';
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const [query, setQuery] = useState(initialQuery);
  const [inputValue, setInputValue] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'recent' | 'oldest' | 'score_desc' | 'score_asc'>('recent');
  const [stats, setStats] = useState<{ article_count: number; newest: string | null } | null>(null);
  const [langFilter, setLangFilter]           = useState<string>('');
  const [directiveFilter, setDirectiveFilter] = useState<string>('');
  const [showLangPicker, setShowLangPicker]   = useState(false);
  const [showDirPicker, setShowDirPicker]     = useState(false);

  useEffect(() => {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? '';
    const fetchStats = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/stats`);
        if (res.ok) setStats(await res.json());
      } catch { /* silent */ }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, [langFilter, directiveFilter]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const performSearch = useCallback(async (searchQuery: string, sort: typeof sortBy = 'recent', lang = langFilter, directive = directiveFilter) => {
    if (!searchQuery.trim() && !lang && !directive) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const params = new URLSearchParams({ limit: '30', sort });
      if (searchQuery.trim()) params.set('q', searchQuery.trim());
      if (lang)      params.set('lang', lang);
      if (directive) params.set('directive', directive);
      const response = await fetch(`/api/search?${params.toString()}`);
      const data: SearchResponse = await response.json();
      if (!response.ok) {
        setError(data.error || 'Search failed');
        setResults([]);
        setTotal(0);
        return;
      }
      setResults(data.results || []);
      setTotal(data.total || 0);
      setTimeout(() => resultsRef.current?.focus({ preventScroll: true }), 100);
    } catch (err) {
      console.error('Search error:', err);
      setError('Network error. Please check your connection.');
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialQuery) performSearch(initialQuery, sortBy);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    router.push(`/search?q=${encodeURIComponent(trimmed)}`, { scroll: false });
    performSearch(trimmed, sortBy);
  };

  const handleSortChange = (sort: typeof sortBy) => {
    setSortBy(sort);
    if (query || langFilter || directiveFilter) performSearch(query, sort, langFilter, directiveFilter);
  };

  const handleLangSelect = (lang: string) => {
    const newLang = langFilter === lang ? '' : lang;
    setLangFilter(newLang);
    setShowLangPicker(false);
    setSearched(true);
    performSearch(query, sortBy, newLang, directiveFilter);
  };

  const handleDirectiveSelect = (dir: string) => {
    const newDir = directiveFilter === dir ? '' : dir;
    setDirectiveFilter(newDir);
    setShowDirPicker(false);
    setSearched(true);
    performSearch(query, sortBy, langFilter, newDir);
  };

  const clearAllFilters = () => {
    setLangFilter('');
    setDirectiveFilter('');
    setShowLangPicker(false);
    setShowDirPicker(false);
    if (query) performSearch(query, sortBy, '', '');
  };

  return (
    <PageWrapper>
      <style>{`
        .arc-snippet em {
          color: rgb(241 245 249);
          font-style: normal;
          font-weight: 600;
          background: transparent;
          border-bottom: 1px solid rgb(100 116 139 / 0.6);
        }
      `}</style>

      {/* Skip to content */}
      <a
        href="#search-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
      >
        Skip to main content
      </a>

      <main id="search-main" className="max-w-4xl mx-auto px-4 sm:px-6 space-y-8">

        {/* ── Hero header ── */}
        <motion.header
          initial={reducedMotion ? {} : { opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="flex flex-col items-center text-center space-y-4 py-8"
        >
          <div
            className="p-4 rounded-2xl bg-gradient-to-br from-amber-500/30 via-orange-400/20 to-yellow-500/30 border border-amber-400/50 shadow-[0_0_40px_rgba(251,191,36,0.4)]"
            aria-hidden="true"
          >
            <Terminal className="h-10 w-10 text-amber-300" />
          </div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-slate-50">
            Intelligence Search
          </h1>
          <p className="text-lg text-slate-400 italic max-w-xl mx-auto font-serif">
            Full-spectrum archive query — {stats ? <span className="font-mono not-italic text-slate-200 font-semibold">{stats.article_count.toLocaleString()}</span> : '—'} articles indexed
          </p>
          <div className="w-20 h-1 bg-gradient-to-r from-amber-400 to-orange-500 rounded-full animate-pulse" aria-hidden="true" />
        </motion.header>

        {/* ── Search form ── */}
        <motion.div
          initial={reducedMotion ? {} : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="p-6 rounded-2xl bg-slate-900/30 border border-amber-400/40 backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.15)]"
        >
          <div className="flex items-center gap-3 mb-4">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/50 text-slate-400 hover:text-amber-300 hover:border-amber-500/30 transition-all ring-focus"
            >
              <ArrowLeft className="h-3 w-3" aria-hidden="true" />
              <span>Home</span>
            </Link>
            <span className="hidden sm:flex items-center gap-1.5 text-xs text-slate-600 border border-slate-700/40 rounded-md px-2 py-1 font-mono bg-slate-800/40 ml-auto">
              <kbd>/</kbd> focus
            </span>
          </div>

          <form onSubmit={handleSubmit} role="search" aria-label="Search intelligence archive">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" aria-hidden="true" />
                <input
                  ref={inputRef}
                  type="search"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Search articles, topics, entities, sources…"
                  aria-label="Search query"
                  className="w-full pl-11 pr-4 py-3.5 bg-slate-900/80 border border-slate-700/60 hover:border-slate-600 focus:border-amber-500/60 rounded-xl text-slate-100 placeholder-slate-600 focus:ring-2 focus:ring-amber-500/15 transition-all text-sm outline-none font-mono"
                  autoFocus
                />
              </div>
              <button
                type="submit"
                disabled={loading || !inputValue.trim()}
                aria-label={loading ? 'Searching…' : 'Run search'}
                className="px-5 py-3.5 bg-amber-500/90 hover:bg-amber-400 disabled:bg-slate-800/80 disabled:text-slate-600 text-slate-900 font-black rounded-xl transition-all text-sm flex items-center gap-2 ring-focus"
              >
                {loading
                  ? <div className="w-4 h-4 border-2 border-slate-700/40 border-t-slate-500 rounded-full animate-spin" aria-hidden="true" />
                  : <><Search className="h-4 w-4" aria-hidden="true" /><span className="hidden sm:inline">Search</span></>
                }
              </button>
            </div>
          </form>
        </motion.div>

        {/* ── Filter bar ── */}
        <motion.div
          initial={reducedMotion ? {} : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15 }}
          className="flex flex-wrap items-center gap-2"
        >
          {/* Language filter */}
          <div className="relative">
            <button
              onClick={() => { setShowLangPicker(v => !v); setShowDirPicker(false); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ring-focus ${
                langFilter
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                  : 'bg-slate-800/60 border-slate-700/50 text-slate-400 hover:text-slate-300'
              }`}
              aria-expanded={showLangPicker}
              aria-haspopup="listbox"
            >
              <Globe className="h-3 w-3" aria-hidden="true" />
              {langFilter || 'Language'}
              {langFilter && (
                <span
                  onClick={(e) => { e.stopPropagation(); handleLangSelect(langFilter); }}
                  className="ml-1 hover:text-white cursor-pointer"
                  aria-label="Clear language filter"
                >×</span>
              )}
            </button>
            {showLangPicker && (
              <div className="absolute top-full mt-1 left-0 z-50 bg-slate-900 border border-slate-700/60 rounded-xl shadow-xl p-2 min-w-[160px]" role="listbox" aria-label="Select language">
                {KNOWN_LANGUAGES.map(lang => (
                  <button
                    key={lang}
                    role="option"
                    aria-selected={langFilter === lang}
                    onClick={() => handleLangSelect(lang)}
                    className={`w-full text-left px-3 py-1.5 text-xs rounded-lg transition-colors ${
                      langFilter === lang
                        ? 'bg-cyan-500/20 text-cyan-300'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                    }`}
                  >
                    {lang}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Directive filter */}
          <div className="relative">
            <button
              onClick={() => { setShowDirPicker(v => !v); setShowLangPicker(false); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ring-focus ${
                directiveFilter
                  ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                  : 'bg-slate-800/60 border-slate-700/50 text-slate-400 hover:text-slate-300'
              }`}
              aria-expanded={showDirPicker}
              aria-haspopup="listbox"
            >
              <Tag className="h-3 w-3" aria-hidden="true" />
              {directiveFilter ? directiveFilter.length > 28 ? directiveFilter.slice(0, 28) + '…' : directiveFilter : 'Topic'}
              {directiveFilter && (
                <span
                  onClick={(e) => { e.stopPropagation(); handleDirectiveSelect(directiveFilter); }}
                  className="ml-1 hover:text-white cursor-pointer"
                  aria-label="Clear topic filter"
                >×</span>
              )}
            </button>
            {showDirPicker && (
              <div className="absolute top-full mt-1 left-0 z-50 bg-slate-900 border border-slate-700/60 rounded-xl shadow-xl p-2 min-w-[260px] max-h-80 overflow-y-auto" role="listbox" aria-label="Select topic">
                {DIRECTIVE_TOPICS.map(({ topic, directives }) => (
                  <div key={topic}>
                    <div className="px-3 py-1 text-[10px] uppercase tracking-widest text-slate-600 font-mono font-bold mt-1">{topic}</div>
                    {directives.map(dir => (
                      <button
                        key={dir}
                        role="option"
                        aria-selected={directiveFilter === dir}
                        onClick={() => handleDirectiveSelect(dir)}
                        className={`w-full text-left px-3 py-1.5 text-xs rounded-lg transition-colors ${
                          directiveFilter === dir
                            ? 'bg-amber-500/20 text-amber-300'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                        }`}
                      >
                        {dir}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Clear all */}
          {(langFilter || directiveFilter) && (
            <button
              onClick={clearAllFilters}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs text-slate-500 hover:text-red-400 border border-slate-700/30 hover:border-red-500/30 transition-all outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
            >
              <X className="h-3 w-3" aria-hidden="true" /> Clear filters
            </button>
          )}
        </motion.div>

        {/* ── Results header + sort ── */}
        {/* Sort buttons render unconditionally — users can pick a default
             before issuing a query. The result-count line sits next to them
             only after a search has actually returned hits. */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-3">
          <p
            className="font-serif text-sm text-slate-400 min-h-[1.25rem]"
            aria-live="polite"
            aria-atomic="true"
          >
            {searched && !loading && !error && total > 0 && (
              <>
                <span className="text-slate-300 font-mono font-semibold tabular-nums">{total.toLocaleString()}</span>
                {' '}result{total !== 1 ? 's' : ''} for{' '}
                <span className="text-slate-300 font-mono">&ldquo;{query}&rdquo;</span>
              </>
            )}
          </p>
          <div role="group" aria-label="Sort results" className="flex items-center gap-1">
            {([
              { key: 'recent',     label: 'Newest'  },
              { key: 'oldest',     label: 'Oldest'  },
              { key: 'score_desc', label: 'Hardest' },
              { key: 'score_asc',  label: 'Easiest' },
            ] as const).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => handleSortChange(key)}
                aria-pressed={sortBy === key}
                className={`px-3 py-1.5 font-sans text-xs uppercase tracking-[0.2em] border rounded-sm transition-colors ring-focus ${
                  sortBy === key
                    ? 'bg-slate-800/40 text-slate-100 border-slate-700'
                    : 'text-slate-500 border-slate-800 hover:text-slate-300 hover:border-slate-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Error ── */}
        <AnimatePresence>
          {error && (
            <motion.div
              role="alert"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex items-start gap-2 py-3"
            >
              <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" aria-hidden="true" />
              <span className="font-serif text-sm text-slate-300 italic leading-relaxed">{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Loading skeletons ── */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="space-y-3" role="status" aria-label="Loading results"
            >
              {[...Array(5)].map((_, i) => <ResultSkeleton key={i} />)}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Results ── */}
        <div
          ref={resultsRef}
          tabIndex={-1}
          className="outline-none border-t border-slate-800/60"
          aria-live="polite"
          aria-busy={loading}
        >
          <AnimatePresence mode="popLayout">
            {!loading && results.map((result, index) => (
              <ResultCard key={result.id} result={result} index={index} />
            ))}
          </AnimatePresence>
        </div>

        {/* ── Empty state ── */}
        {!searched && !loading && (
          <motion.div
            initial={reducedMotion ? {} : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16 space-y-10"
          >
            {/* Radar pulse */}
            <div className="flex justify-center">
              <div className="relative w-16 h-16">
                <RadarRing delay={0} />
                <RadarRing delay={1.2} />
                <RadarRing delay={2.4} />
                <div className="absolute inset-0 rounded-full border border-amber-500/30 bg-gradient-to-br from-amber-500/20 via-orange-400/10 to-yellow-500/20 flex items-center justify-center shadow-[0_0_30px_rgba(251,191,36,0.3)]">
                  <Search className="h-6 w-6 text-amber-300" aria-hidden="true" />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-slate-100 font-bold text-xl tracking-tight">Search the intelligence archive</p>
              <p className="text-sm text-slate-500 max-w-sm mx-auto">
                Try topics like{' '}
                {(['AI', 'Pentagon', 'sanctions'] as const).map((term, i, arr) => (
                  <span key={term}>
                    <button
                      onClick={() => { setInputValue(term); inputRef.current?.focus(); }}
                      className="text-amber-400/80 hover:text-amber-300 transition-colors font-mono ring-focus rounded"
                    >
                      {term}
                    </button>
                    {i < arr.length - 1 ? ', ' : ''}
                  </span>
                ))}{', '}or a source name
              </p>
            </div>

            {/* Live stats card — matches Section style */}
            {stats && (
              <motion.div
                initial={reducedMotion ? {} : { opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 }}
                className="inline-flex flex-col sm:flex-row items-center gap-4 sm:gap-6 bg-slate-900/30 border border-amber-400/30 rounded-2xl px-6 sm:px-8 py-5 backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.1)] mx-auto"
              >
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse" aria-hidden="true" />
                  <Database className="h-4 w-4 text-slate-500" aria-hidden="true" />
                  <div className="text-left">
                    <div className="text-2xl font-black text-amber-400 tabular-nums tracking-tight font-mono">
                      {stats.article_count.toLocaleString()}
                    </div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-mono">articles indexed</div>
                  </div>
                </div>

                {stats.newest && (
                  <>
                    <div className="hidden sm:block w-px h-10 bg-slate-700/60" aria-hidden="true" />
                    <div className="flex items-center gap-3">
                      <CalendarDays className="h-4 w-4 text-slate-500" aria-hidden="true" />
                      <div className="text-left">
                        <div className="text-sm font-bold text-slate-300 font-mono">
                          {formatRelativeTime(stats.newest)}
                        </div>
                        <div className="text-[10px] text-slate-500 uppercase tracking-widest font-mono">last ingested</div>
                      </div>
                    </div>
                  </>
                )}
              </motion.div>
            )}
          </motion.div>
        )}

        {/* ── No results ── */}
        {searched && !loading && !error && total === 0 && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="text-center py-20" role="status"
          >
            <p className="text-slate-400 font-bold mb-2">No articles matched</p>
            <p className="text-sm text-slate-500 font-mono">&ldquo;{query}&rdquo; — try different keywords</p>
          </motion.div>
        )}

      </main>
    </PageWrapper>
  );
}
