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
import { Search, ArrowLeft, Clock, Newspaper, Zap, Shield, TrendingUp, Radio, Database, CalendarDays, Terminal } from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';

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

const getChimeraColor = (score: number) => {
  if (score >= 0.7) return { bar: 'bg-red-500',     text: 'text-red-400',     label: 'HIGH' };
  if (score >= 0.4) return { bar: 'bg-amber-500',   text: 'text-amber-400',   label: 'MED'  };
  return               { bar: 'bg-emerald-500', text: 'text-emerald-400', label: 'LOW'  };
};

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
function ResultCard({ result, index }: { result: SearchResult; index: number }) {
  const chimera = result.chimera_score || 0;
  const chimeraColors = getChimeraColor(chimera);
  const chimeraPercent = Math.round(chimera * 100);
  const dir = getDirectiveConfig(result.directive);

  return (
    <motion.div
      initial={reducedMotion ? {} : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reducedMotion ? {} : { opacity: 0, y: -10 }}
      transition={{ duration: 0.25, delay: index * 0.04 }}
    >
      <Link
        href={`/article/${result.id}`}
        className={`group relative block bg-slate-900/30 border ${dir.border} rounded-2xl p-5 backdrop-blur-sm transition-all duration-300 hover:scale-[1.005] ${dir.glow} outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950`}
      >
        {/* Left accent bar */}
        <div
          className="absolute left-0 top-4 bottom-4 w-0.5 rounded-full opacity-20 group-hover:opacity-80 transition-opacity duration-300"
          style={{ background: dir.accentBar }}
          aria-hidden="true"
        />

        <div className="flex gap-4">
          <div className="flex-1 min-w-0 space-y-2.5">
            <h2 className="text-base font-bold text-slate-50 group-hover:text-amber-300 transition-colors leading-snug line-clamp-2 tracking-tight">
              {result.title}
            </h2>

            {result.snippet && (
              <p
                className="text-sm text-slate-400 leading-relaxed line-clamp-2 arc-snippet"
                dangerouslySetInnerHTML={{ __html: result.snippet }}
              />
            )}

            <div className="flex items-center gap-3 text-xs flex-wrap">
              {result.source && (
                <span className="flex items-center gap-1.5 text-slate-400">
                  <Newspaper className="h-3 w-3" aria-hidden="true" />
                  {result.source}
                </span>
              )}
              {result.timestamp && (
                <time dateTime={result.timestamp} className="flex items-center gap-1.5 text-slate-500">
                  <Clock className="h-3 w-3" aria-hidden="true" />
                  {formatRelativeTime(result.timestamp)}
                </time>
              )}
              {result.directive && (
                <span className={`flex items-center gap-1 px-2 py-0.5 ${dir.badgeBg} border ${dir.border} rounded-full uppercase tracking-wider font-mono font-medium text-[10px] ${dir.color}`}>
                  {dir.icon}
                  {result.directive.replace(/_/g, ' ')}
                </span>
              )}
            </div>
          </div>

          {/* Tone bar */}
          {chimera > 0 && (
            <div
              className="flex-shrink-0 flex flex-col items-center justify-center gap-1.5 w-12"
              title="Tone: emotional charge of the article. High = more emotionally loaded."
              aria-label={`Tone score ${chimeraPercent}, ${chimeraColors.label}`}
            >
              <span className="text-[9px] font-bold tracking-widest text-slate-500 uppercase font-mono" aria-hidden="true">Tone</span>
              <span className={`text-xs font-bold tabular-nums font-mono ${chimeraColors.text}`} aria-hidden="true">{chimeraPercent}</span>
              <div className="w-1.5 h-12 bg-slate-700/60 rounded-full overflow-hidden rotate-180" aria-hidden="true">
                <motion.div
                  className={`w-full ${chimeraColors.bar} rounded-full`}
                  initial={{ height: 0 }}
                  animate={{ height: `${chimeraPercent}%` }}
                  transition={{ duration: 0.6, delay: index * 0.04 + 0.2, ease: 'easeOut' }}
                />
              </div>
              <span className={`text-[9px] font-bold tracking-widest font-mono ${chimeraColors.text} opacity-70`} aria-hidden="true">{chimeraColors.label}</span>
            </div>
          )}
        </div>
      </Link>
    </motion.div>
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
  const [sortBy, setSortBy] = useState<'recent' | 'relevant' | 'score_desc' | 'score_asc'>('relevant');
  const [stats, setStats] = useState<{ article_count: number; newest: string | null } | null>(null);

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
  }, []);

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

  const performSearch = useCallback(async (searchQuery: string, sort: typeof sortBy = 'relevant') => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(searchQuery.trim())}&limit=30&sort=${sort}`);
      const data: SearchResponse = await response.json();
      if (!response.ok) {
        setError(data.error || 'Search failed');
        setResults([]);
        setTotal(0);
        return;
      }
      setResults(data.results || []);
      setTotal(data.total || 0);
      setTimeout(() => resultsRef.current?.focus(), 100);
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
    if (query) performSearch(query, sort);
  };

  return (
    <PageWrapper>
      <style>{`
        .arc-snippet em {
          color: rgb(251 191 36);
          font-style: normal;
          font-weight: 600;
          background: rgb(251 191 36 / 0.1);
          padding: 0 2px;
          border-radius: 2px;
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
          <p className="text-lg text-amber-300/80 italic max-w-xl mx-auto">
            Full-spectrum archive query — {stats ? <span className="font-mono not-italic text-amber-400">{stats.article_count.toLocaleString()}</span> : '—'} articles indexed
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
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/50 text-slate-400 hover:text-amber-300 hover:border-amber-500/30 transition-all outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
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
                className="px-5 py-3.5 bg-amber-500/90 hover:bg-amber-400 disabled:bg-slate-800/80 disabled:text-slate-600 text-slate-900 font-black rounded-xl transition-all text-sm flex items-center gap-2 outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
              >
                {loading
                  ? <div className="w-4 h-4 border-2 border-slate-700/40 border-t-slate-500 rounded-full animate-spin" aria-hidden="true" />
                  : <><Search className="h-4 w-4" aria-hidden="true" /><span className="hidden sm:inline">Search</span></>
                }
              </button>
            </div>
          </form>
        </motion.div>

        {/* ── Results header + sort ── */}
        <AnimatePresence>
          {searched && !loading && !error && total > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between"
            >
              <p className="text-sm text-slate-400" aria-live="polite" aria-atomic="true">
                <span className="text-amber-400 font-black tabular-nums font-mono">{total.toLocaleString()}</span>
                {' '}result{total !== 1 ? 's' : ''} for{' '}
                <span className="text-slate-300 font-mono">&ldquo;{query}&rdquo;</span>
              </p>
              <div role="group" aria-label="Sort results" className="flex items-center gap-1 bg-slate-900/60 rounded-lg p-0.5 border border-slate-700/40">
                {([
                  { key: 'relevant',   label: 'Relevant' },
                  { key: 'recent',     label: 'Recent'   },
                  { key: 'score_desc', label: 'Tone ↑'   },
                  { key: 'score_asc',  label: 'Tone ↓'   },
                ] as const).map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => handleSortChange(key)}
                    aria-pressed={sortBy === key}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 ${
                      sortBy === key
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Error ── */}
        <AnimatePresence>
          {error && (
            <motion.div
              role="alert"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="bg-red-950/40 border border-red-700/40 rounded-2xl p-4 text-red-300 text-sm font-mono backdrop-blur-sm"
            >
              {error}
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
          className="space-y-3 outline-none"
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
                      className="text-amber-400/80 hover:text-amber-300 transition-colors font-mono outline-none focus-visible:ring-1 focus-visible:ring-amber-400/60 rounded"
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
