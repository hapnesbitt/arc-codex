'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Search, X } from 'lucide-react';

interface Book {
  gutenberg_id: string;
  title: string;
  author: string;
  language: string;
  download_count: number;
  year_published: string;
  subjects: string[];
  chimera_score: number | null;
  reading_label: string;
  chimera_skip_reason: string;
}

export default function ShelfBooksClient({ books }: { books: Book[] }) {
  const [query, setQuery] = useState('');

  const filteredBooks = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return books;
    return books.filter((b) =>
      `${b.title} ${b.author}`.toLowerCase().includes(q),
    );
  }, [books, query]);

  const showEmptyState = query.trim().length >= 2 && filteredBooks.length === 0;

  return (
    <>
      <div className="my-8">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search this shelf by title or author…"
            className="w-full pl-10 pr-10 py-3 bg-slate-900/50 border border-slate-800 rounded-sm font-serif text-base text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-400/40 focus:border-emerald-700"
            aria-label="Search this shelf"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {showEmptyState && (
          <p className="mt-4 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 text-center">
            No matches in this shelf.
          </p>
        )}
      </div>

      {!showEmptyState && (
        <ul className="border-t border-slate-800/40">
          {filteredBooks.map((work) => {
            const hasChimera = typeof work.chimera_score === 'number';
            return (
              <li key={work.gutenberg_id} className="border-b border-slate-800/40">
                <Link
                  href={`/library/${work.gutenberg_id}`}
                  className="flex items-center justify-between gap-4 py-5 px-2 -mx-2 hover:bg-slate-800/30 transition-colors group rounded-sm ring-focus"
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <h2 className="font-serif text-lg sm:text-xl text-slate-100 group-hover:text-slate-50 transition-colors leading-snug">
                      {work.title}
                    </h2>
                    <p className="font-serif italic text-sm text-slate-400 leading-snug">
                      {work.author || 'Unknown'}
                    </p>
                    <div className="flex items-center gap-3 flex-wrap font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                      <span>{work.download_count.toLocaleString()} Gutenberg downloads</span>
                      {work.language && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>{work.language}</span>
                        </>
                      )}
                      {work.year_published && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>{work.year_published}</span>
                        </>
                      )}
                      {hasChimera && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span
                            className="text-emerald-300/80"
                            title="Chimera Difficulty Score — synthesizes Flesch-Kincaid, Coleman-Liau, SMOG, and Dale-Chall readability metrics"
                          >
                            Difficulty {work.chimera_score}
                            {work.reading_label && ` (${work.reading_label})`}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <ChevronRight
                    className="h-4 w-4 text-slate-600 group-hover:text-slate-300 transition-colors shrink-0"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
