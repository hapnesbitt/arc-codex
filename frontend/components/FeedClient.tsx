// File: /frontend/components/FeedClient.tsx
// VERSION: Tribonacci Lazy Loading + Staggered Waterfall Animation
// REFACTOR: Inclusive/Solid Accessibility (ARIA Landmarks + Semantic List)
// FIX: Updated Ref types to HTMLLIElement to match semantic list structure.

'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import IntelligenceCard from '@/components/IntelligenceCard';
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
    <div className="relative">
      <div className="absolute inset-0 rounded-full bg-amber-400/20 blur-xl animate-pulse"></div>
      <div className="relative animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-amber-300"></div>
      <div className="absolute inset-2 rounded-full bg-amber-400/10 animate-ping"></div>
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
        className="mt-4 px-6 py-2 bg-amber-500 text-slate-900 font-bold rounded-lg hover:bg-amber-400 transition-colors shadow-md hover:shadow-lg focus:ring-2 focus:ring-white outline-none"
      >
        Try Again
      </motion.button>
    </div>
  </motion.div>
);

function FeedClient({ initialFeed, initialComments }: FeedClientProps): React.JSX.Element {
  const [feed, setFeed] = useState<Article[]>(initialFeed || []);
  const [loading, setLoading] = useState<boolean>(false);
  const [hasMore, setHasMore] = useState<boolean>((initialFeed || []).length > 0);
  const [error, setError] = useState<string | null>(null);

  // Updated to HTMLLIElement to match the list item structure
  const observerTarget = useRef<HTMLLIElement | null>(null);
  const fibState = useRef<{ a: number; b: number; c: number }>({ a: 1, b: 1, c: 2 });
  const offsetRef = useRef<number>((initialFeed || []).length);

  const fetchMoreItems = useCallback(async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    setError(null);

    const limit = fibState.current.b;

    try {
      const response = await fetch(`/api/get_feed?limit=${limit}&offset=${offsetRef.current}`);
      if (!response.ok) throw new Error(`API error! status: ${response.status}`);

      const newItems: Article[] = await response.json();
      if (newItems.length < limit) setHasMore(false);

      setFeed(prevFeed => [...prevFeed, ...newItems]);
      offsetRef.current += newItems.length;
      
      const next_trib = fibState.current.a + fibState.current.b + fibState.current.c;
      fibState.current.a = fibState.current.b;
      fibState.current.b = fibState.current.c;
      fibState.current.c = next_trib;
    } catch (err) {
      console.error('Error fetching items:', err);
      setError('Failed to load more stories.');
    } finally {
      setLoading(false);
    }
  }, [loading, hasMore]);

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

  // Updated parameter type to HTMLLIElement
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

  return (
    <main 
      className="space-y-12" 
      role="feed" 
      aria-busy={loading}
      aria-label="Intelligence Main Feed"
    >
      <ol className="space-y-12 list-none p-0 m-0">
        <AnimatePresence mode="popLayout">
          {feed.map((card, index) => {
            const cardComments = commentsByArticleId.get(card.id) || [];
            const isLastItem = index === feed.length - 1;
            
            // Calculate stagger delay based on its position in the current Tribonacci batch
            const staggerIndex = index >= initialFeed.length ? (index - initialFeed.length) % fibState.current.c : index;

            return (
              <motion.li
                key={card.id}
                ref={isLastItem ? lastItemRef : null}
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ 
                  duration: 0.5, 
                  ease: "circOut",
                  delay: Math.min(staggerIndex * 0.1, 0.5) // Max 0.5s delay to keep it snappy
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
            <p className="text-sm mt-2 text-slate-500" aria-label={`Total of ${feed.length} stories viewed`}>
                Viewed {feed.length} stories
            </p>
          </div>
        </motion.div>
      )}
    </main>
  );
}

export default React.memo(FeedClient);
