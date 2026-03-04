// Filename: /frontend/app/search/page.tsx
// Arc Codex Search Page — Full-text search via Solr with highlighted snippets
// Version 2.0

'use client';

import React, { useState, useEffect, useCallback, Suspense, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, ArrowLeft, Clock, Newspaper, Zap, Shield, TrendingUp, Radio, Database, CalendarDays } from 'lucide-react';

// --- TYPE DEFINITIONS ---
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

// --- HELPERS ---
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
  } catch {
    return '';
  }
};

const getDirectiveIcon = (directive: string) => {
  const d = directive?.toLowerCase() || '';
  if (d.includes('threat') || d.includes('intel')) return <Shield className="h-3 w-3" />;
  if (d.includes('tech') || d.includes('surv')) return <Radio className="h-3 w-3" />;
  if (d.includes('econ') || d.includes('finance')) return <TrendingUp className="h-3 w-3" />;
  return <Zap className="h-3 w-3" />;
};

const getChimeraColor = (score: number) => {
  if (score >= 0.7) return { bar: 'bg-red-500', text: 'text-red-400', label: 'HIGH' };
  if (score >= 0.4) return { bar: 'bg-amber-500', text: 'text-amber-400', label: 'MED' };
  return { bar: 'bg-emerald-500', text: 'text-emerald-400', label: 'LOW' };
};

// --- SKELETON LOADER ---
function ResultSkeleton() {
  return (
    <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-5 space-y-3 animate-pulse">
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

// --- RESULT CARD ---
function ResultCard({ result, index }: { result: SearchResult; index: number }) {
  const chimera = result.chimera_score || 0;
  const chimeraColors = getChimeraColor(chimera);
  const chimeraPercent = Math.round(chimera * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25, delay: index * 0.04 }}
    >
      <Link href={`/article/${result.id}`}>
        <div className="group relative bg-slate-800/40 border border-slate-700/40 hover:border-amber-500/40 rounded-xl p-5 transition-all duration-200 hover:bg-slate-800/70 cursor-pointer overflow-hidden">

          {/* Left accent bar */}
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-transparent via-amber-500/0 to-transparent group-hover:via-amber-500/60 transition-all duration-300" />

          <div className="flex gap-4">
            {/* Main content */}
            <div className="flex-1 min-w-0 space-y-2.5">
              <h3 className="text-base font-semibold text-slate-100 group-hover:text-amber-300 transition-colors leading-snug line-clamp-2">
                {result.title}
              </h3>

              {result.snippet && (
                <p
                  className="text-sm text-slate-400 leading-relaxed line-clamp-2 arc-snippet"
                  dangerouslySetInnerHTML={{ __html: result.snippet }}
                />
              )}

              <div className="flex items-center gap-3 text-xs text-slate-500 flex-wrap">
                {result.source && (
                  <span className="flex items-center gap-1.5 text-slate-400">
                    <Newspaper className="h-3 w-3" />
                    {result.source}
                  </span>
                )}
                {result.timestamp && (
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(result.timestamp)}
                  </span>
                )}
                {result.directive && (
                  <span className="flex items-center gap-1 px-2 py-0.5 bg-slate-700/60 border border-slate-600/40 rounded-full uppercase tracking-wider font-medium text-slate-400">
                    {getDirectiveIcon(result.directive)}
                    {result.directive.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
            </div>

            {/* Tone score sidebar */}
            {chimera > 0 && (
              <div
                className="flex-shrink-0 flex flex-col items-center justify-center gap-1.5 w-12"
                title="Tone: emotional charge of the article text. High = more emotionally loaded, Low = more neutral."
              >
                <span className="text-[9px] font-bold tracking-widest text-slate-500 uppercase">Tone</span>
                <span className={`text-xs font-bold tabular-nums ${chimeraColors.text}`}>
                  {chimeraPercent}
                </span>
                <div className="w-1.5 h-12 bg-slate-700/60 rounded-full overflow-hidden rotate-180">
                  <motion.div
                    className={`w-full ${chimeraColors.bar} rounded-full`}
                    initial={{ height: 0 }}
                    animate={{ height: `${chimeraPercent}%` }}
                    transition={{ duration: 0.6, delay: index * 0.04 + 0.2, ease: 'easeOut' }}
                  />
                </div>
                <span className={`text-[9px] font-bold tracking-widest ${chimeraColors.text} opacity-70`}>
                  {chimeraColors.label}
                </span>
              </div>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

// --- MAIN EXPORT ---
export default function SearchPage() {
  return (
    <Suspense fallback={
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
        {[...Array(5)].map((_, i) => <ResultSkeleton key={i} />)}
      </div>
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

  const [query, setQuery] = useState(initialQuery);
  const [inputValue, setInputValue] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'recent' | 'relevant' | 'score_desc' | 'score_asc'>('relevant');

  // Live archive stats
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

  // Press / to focus search
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

  const performSearch = useCallback(async (searchQuery: string, sort: 'recent' | 'relevant' | 'score_desc' | 'score_asc' = 'relevant') => {
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

  const handleSortChange = (sort: 'recent' | 'relevant' | 'score_desc' | 'score_asc') => {
    setSortBy(sort);
    if (query) performSearch(query, sort);
  };

  return (
    <>
      {/* Snippet highlight styles */}
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

      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/50 text-slate-400 hover:text-amber-300 hover:border-amber-500/30 hover:bg-slate-800 transition-all"
            >
              <ArrowLeft className="h-3 w-3" />
              <span>Home</span>
            </Link>
            <div className="h-4 w-px bg-slate-700" />
            <h1 className="text-xl font-bold text-slate-100 tracking-tight">Intelligence Search</h1>
          </div>
          <span className="hidden sm:flex items-center gap-1.5 text-xs text-slate-600 border border-slate-700/50 rounded-md px-2 py-1">
            <kbd className="font-mono">/</kbd>
            <span>to focus</span>
          </span>
        </div>

        {/* Search Form */}
        <form onSubmit={handleSubmit}>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Search articles, topics, entities, sources…"
                className="w-full pl-11 pr-4 py-3 bg-slate-900/80 border border-slate-700/60 hover:border-slate-600/60 focus:border-amber-500/60 rounded-xl text-slate-100 placeholder-slate-500 focus:ring-2 focus:ring-amber-500/20 transition-all text-sm outline-none"
                autoFocus
              />
            </div>
            <button
              type="submit"
              disabled={loading || !inputValue.trim()}
              className="px-5 py-3 bg-amber-500/90 hover:bg-amber-400/90 disabled:bg-slate-800 disabled:text-slate-600 text-slate-900 font-bold rounded-xl transition-all text-sm flex items-center gap-2"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-slate-700/40 border-t-slate-500 rounded-full animate-spin" />
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  <span className="hidden sm:inline">Search</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Results header row */}
        <AnimatePresence>
          {searched && !loading && !error && total > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between"
            >
              <span className="text-sm text-slate-400">
                <span className="text-amber-400 font-semibold">{total.toLocaleString()}</span>
                {' '}result{total !== 1 ? 's' : ''} for{' '}
                <span className="text-slate-300">&ldquo;{query}&rdquo;</span>
              </span>
              <div className="flex items-center gap-1 bg-slate-900/60 rounded-lg p-0.5 border border-slate-700/40">
                {([
                  { key: 'relevant',   label: 'Relevant' },
                  { key: 'recent',     label: 'Recent'   },
                  { key: 'score_desc', label: 'Tone ↑'   },
                  { key: 'score_asc',  label: 'Tone ↓'   },
                ] as const).map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => handleSortChange(key)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
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

        {/* Error */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="bg-red-950/40 border border-red-700/40 rounded-xl p-4 text-red-300 text-sm"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Loading skeletons */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-3"
            >
              {[...Array(5)].map((_, i) => <ResultSkeleton key={i} />)}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Results */}
        <AnimatePresence mode="popLayout">
          {!loading && results.map((result, index) => (
            <ResultCard key={result.id} result={result} index={index} />
          ))}
        </AnimatePresence>

        {/* Empty state — no search yet */}
        {!searched && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16 space-y-8"
          >
            {/* Search icon */}
            <div className="relative inline-block">
              <div className="absolute inset-0 bg-amber-500/10 rounded-full blur-xl scale-150" />
              <div className="relative w-16 h-16 rounded-full border border-slate-700/60 bg-slate-900/80 flex items-center justify-center mx-auto">
                <Search className="h-7 w-7 text-slate-500" />
              </div>
            </div>

            <div>
              <p className="text-slate-300 font-medium mb-2">Search the intelligence archive</p>
              <p className="text-sm text-slate-500 max-w-sm mx-auto">
                Try topics like <button onClick={() => { setInputValue('AI'); inputRef.current?.focus(); }} className="text-amber-500/70 hover:text-amber-400 transition-colors">AI</button>,{' '}
                <button onClick={() => { setInputValue('Pentagon'); inputRef.current?.focus(); }} className="text-amber-500/70 hover:text-amber-400 transition-colors">Pentagon</button>,{' '}
                <button onClick={() => { setInputValue('sanctions'); inputRef.current?.focus(); }} className="text-amber-500/70 hover:text-amber-400 transition-colors">sanctions</button>,{' '}
                or a source name
              </p>
            </div>

            {/* Live stats */}
            {stats && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 }}
                className="flex flex-col sm:flex-row items-center gap-4 sm:gap-6 bg-slate-900/60 border border-slate-700/40 rounded-2xl px-6 sm:px-8 py-5 mx-auto w-fit"
              >
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse" />
                  <Database className="h-4 w-4 text-slate-500" />
                  <div className="text-left">
                    <div className="text-2xl font-black text-amber-400 tabular-nums tracking-tight">
                      {stats.article_count.toLocaleString()}
                    </div>
                    <div className="text-xs text-slate-500 uppercase tracking-widest">articles indexed</div>
                  </div>
                </div>

                {stats.newest && (
                  <>
                    <div className="hidden sm:block w-px h-10 bg-slate-700/60" />
                    <div className="flex items-center gap-3">
                      <CalendarDays className="h-4 w-4 text-slate-500" />
                      <div className="text-left">
                        <div className="text-sm font-semibold text-slate-300">
                          {formatRelativeTime(stats.newest)}
                        </div>
                        <div className="text-xs text-slate-500 uppercase tracking-widest">last ingested</div>
                      </div>
                    </div>
                  </>
                )}
              </motion.div>
            )}
          </motion.div>
        )}

        {/* No results */}
        {searched && !loading && !error && total === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-20"
          >
            <p className="text-slate-400 font-medium mb-2">No articles matched</p>
            <p className="text-sm text-slate-500">&ldquo;{query}&rdquo; — try different keywords</p>
          </motion.div>
        )}
      </div>
    </>
  );
}
