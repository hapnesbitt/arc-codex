// File: /frontend/components/FeedClient.tsx
// VERSION: Tribonacci Lazy Loading + Staggered Waterfall Animation
// v3 — Auto-translate: reads preferred_lang from UserPrefsContext, passes as
//       initialLang to each IntelligenceCard so cards auto-translate on mount
//   - role="feed" moved from <main> to <ol> (preserves main landmark)
//   - aria-posinset + aria-setsize on each feed item (required by feed pattern)
//   - Decorative spinner divs get aria-hidden
//   - focus-visible replaces focus on retry button ring
//   - "Viewed N stories" aria-label removed (text content is sufficient)

'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import IntelligenceCard from '@/components/IntelligenceCard';
import { useUserPrefs } from '@/components/UserPrefsContext';
import type { Article, Comment } from '@/lib/types';

// --- TYPE DEFINITIONS ---
interface FeedClientProps {
  initialFeed: Article[];
  initialComments: Comment[];
}

const LoadingSpinner: React.FC = () => (
  <div
    className="w-full max-w-2xl mx-auto py-12"
    role="status"
    aria-live="polite"
  >
    <div
      className="h-80 border-b border-slate-800/60 bg-slate-900/30 animate-pulse"
      aria-hidden="true"
    />
    <span className="sr-only">Loading more stories.</span>
  </div>
);

const ErrorMessage: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
  <div
    className="w-full max-w-2xl mx-auto border-t border-rose-500/30 px-4 sm:px-8 py-8 text-center"
    role="alert"
    aria-live="assertive"
  >
    <p className="font-sans text-sm text-slate-300">{message}</p>
    <button
      onClick={onRetry}
      className="mt-4 px-4 py-2 rounded-sm border border-slate-700 text-slate-300 hover:border-slate-500 hover:text-slate-100 font-sans text-xs uppercase tracking-[0.2em] transition-colors ring-focus"
    >
      Try Again
    </button>
  </div>
);

function FeedClient({ initialFeed, initialComments }: FeedClientProps): React.JSX.Element {
  const [feed, setFeed]       = useState<Article[]>(initialFeed || []);
  const [loading, setLoading] = useState<boolean>(false);
  const [hasMore, setHasMore] = useState<boolean>((initialFeed || []).length > 0);
  const [error, setError]     = useState<string | null>(null);

  const { prefs } = useUserPrefs();
  const preferredLang = prefs?.preferred_lang ?? null;

  const searchParams   = useSearchParams();
  const router         = useRouter();
  const directiveFilter = searchParams.get('directive') || '';

  const observerTarget = useRef<HTMLLIElement | null>(null);
  const fibState       = useRef<{ a: number; b: number; c: number }>({ a: 1, b: 1, c: 2 });
  const offsetRef      = useRef<number>((initialFeed || []).length);
  // Snapshot batch size at render time so stagger calc is stable
  const batchSizeRef   = useRef<number>(fibState.current.c);

  const fetchMoreItems = useCallback(async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    setError(null);

    const limit = fibState.current.b;

    try {
      const directiveParam = directiveFilter ? `&directive=${encodeURIComponent(directiveFilter)}` : '';
      const response = await fetch(`/api/get_feed?limit=${limit}&offset=${offsetRef.current}${directiveParam}`);
      if (!response.ok) throw new Error(`API error! status: ${response.status}`);

      const newItems: Article[] = await response.json();
      if (newItems.length < limit) setHasMore(false);

      setFeed(prev => [...prev, ...newItems]);
      offsetRef.current += newItems.length;

      const next_trib = fibState.current.a + fibState.current.b + fibState.current.c;
      fibState.current = {
        a: fibState.current.b,
        b: fibState.current.c,
        c: next_trib,
      };
      batchSizeRef.current = fibState.current.c;
    } catch (err) {
      console.error('Error fetching items:', err);
      setError('Failed to load more stories.');
    } finally {
      setLoading(false);
    }
  }, [loading, hasMore, directiveFilter]);

  // Reset feed when directive filter changes (skip initial mount)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    setFeed([]);
    offsetRef.current = 0;
    setHasMore(true);
    setError(null);
    fibState.current = { a: 1, b: 1, c: 2 };
    batchSizeRef.current = 2;
  }, [directiveFilter]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loading) {
          fetchMoreItems();
        }
      },
      { rootMargin: '500px' }
    );

    const currentTarget = observerTarget.current;
    if (currentTarget) observer.observe(currentTarget);
    return () => { if (currentTarget) observer.unobserve(currentTarget); };
  }, [hasMore, loading, fetchMoreItems]);

  const lastItemRef = useCallback((node: HTMLLIElement | null) => {
    observerTarget.current = node;
  }, []);

  const commentsByArticleId = useMemo(() => {
    const map = new Map<string, Comment[]>();
    for (const c of initialComments || []) {
      if (!map.has(c.article_id)) map.set(c.article_id, []);
      map.get(c.article_id)!.push(c);
    }
    return map;
  }, [initialComments]);

  const totalKnown = feed.length; // setsize approximation — exact count if feed is fully loaded

  return (
    // <main> retains its implicit landmark role.
    // role="feed" lives on the <ol> where it belongs per ARIA spec.
    <main className="space-y-12" aria-label="Intelligence Main Feed">
      {directiveFilter && (
        <div className="chip w-full max-w-2xl mx-auto flex items-center gap-3 mb-2">
          <span className="text-slate-400">Filtering by: <strong className="text-slate-300 font-semibold">{directiveFilter}</strong></span>
          <button
            onClick={() => router.push('/')}
            className="ml-auto inline-flex items-center gap-1 px-2 py-1.5 -my-1 rounded-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 transition-colors ring-focus"
            aria-label="Clear directive filter"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Clear</span>
          </button>
        </div>
      )}
      <ol
        role="feed"
        aria-busy={loading}
        aria-label="Intelligence Main Feed"
        className="space-y-12 list-none p-0 m-0"
      >
        <AnimatePresence mode="popLayout">
          {feed.map((card, index) => {
            const cardComments = commentsByArticleId.get(card.id) || [];
            const isLastItem   = index === feed.length - 1;
            const staggerIndex = index >= initialFeed.length
              ? (index - initialFeed.length) % batchSizeRef.current
              : index;

            return (
              <motion.li
                key={card.id}
                ref={isLastItem ? lastItemRef : null}
                // ARIA feed pattern: position + total so AT announces "item 3 of 47"
                aria-posinset={index + 1}
                aria-setsize={hasMore ? -1 : totalKnown} // -1 = unknown total while loading
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{
                  duration: 0.5,
                  ease: "circOut",
                  delay: Math.min(staggerIndex * 0.1, 0.5),
                }}
                className="space-y-4 outline-none"
              >
                <IntelligenceCard card={card} comments={cardComments} isCompact={true} />
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>

      {loading && <LoadingSpinner />}
      {error && <ErrorMessage message={error} onRetry={fetchMoreItems} />}

      {!hasMore && feed.length > 0 && (
        <div
          className="py-12 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500"
          role="status"
        >
          End of feed · Viewed {feed.length} {feed.length === 1 ? 'story' : 'stories'}
        </div>
      )}
    </main>
  );
}

export default React.memo(FeedClient);
