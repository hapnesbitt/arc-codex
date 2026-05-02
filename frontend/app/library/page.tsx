// Filename: /frontend/app/library/page.tsx
// Library — top 100 public-domain works from Project Gutenberg.
// Server Component. Same librarian aesthetic as /sources and /wiki.

import React from 'react';
import Link from 'next/link';
import type { Metadata } from 'next';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Library — Arc Codex',
  description: 'One hundred public-domain works from Project Gutenberg, freely readable.',
};

export const revalidate = 3600;

interface Work {
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

type SortMode = 'author' | 'difficulty_asc' | 'difficulty_desc' | 'downloads';

const SORT_OPTIONS: { id: SortMode; label: string }[] = [
  { id: 'author',           label: 'Author A–Z' },
  { id: 'difficulty_asc',   label: 'Easiest → Hardest' },
  { id: 'difficulty_desc',  label: 'Hardest → Easiest' },
  { id: 'downloads',        label: 'Most Downloaded' },
];

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

async function getWorks(): Promise<Work[]> {
  try {
    const res = await fetch(`${BACKEND}/api/library`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

/**
 * Surname extraction for sort. Handles "Last, First", "First Last", and
 * multi-author "& "-joined fields by using the first author's surname.
 */
function authorSortKey(author: string): string {
  if (!author) return 'zzzz';
  const first = author.split('&')[0].trim();
  if (first.includes(',')) {
    return first.split(',')[0].trim().toLowerCase();
  }
  const parts = first.split(/\s+/).filter(Boolean);
  return (parts[parts.length - 1] || first).toLowerCase();
}

function sortWorks(works: Work[], mode: SortMode): Work[] {
  const arr = [...works];
  if (mode === 'difficulty_asc' || mode === 'difficulty_desc') {
    // Unscored / non-English works sink to the bottom regardless of direction.
    const dir = mode === 'difficulty_asc' ? 1 : -1;
    return arr.sort((a, b) => {
      const aHas = typeof a.chimera_score === 'number';
      const bHas = typeof b.chimera_score === 'number';
      if (aHas && !bHas) return -1;
      if (!aHas && bHas) return 1;
      if (!aHas && !bHas) return a.title.localeCompare(b.title);
      const cmp = ((a.chimera_score as number) - (b.chimera_score as number)) * dir;
      return cmp !== 0 ? cmp : a.title.localeCompare(b.title);
    });
  }
  if (mode === 'downloads') {
    return arr.sort((a, b) => {
      const cmp = b.download_count - a.download_count;
      return cmp !== 0 ? cmp : a.title.localeCompare(b.title);
    });
  }
  return arr.sort((a, b) => {
    const k = authorSortKey(a.author).localeCompare(authorSortKey(b.author));
    return k !== 0 ? k : a.title.localeCompare(b.title);
  });
}

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const params = await searchParams;
  const requestedSort = params?.sort as SortMode | undefined;
  const sortMode: SortMode = SORT_OPTIONS.some((o) => o.id === requestedSort)
    ? (requestedSort as SortMode)
    : 'author';

  const works = await getWorks();
  const sorted = sortWorks(works, sortMode);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            The Library
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Library
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
            One hundred public-domain works, freely readable — drawn from Project Gutenberg.
          </p>
          <p className="font-serif text-sm text-slate-500 italic leading-relaxed max-w-xl mx-auto">
            Books may be read in English (original) or translated on demand to German, French, Spanish, or Brazilian Portuguese.
          </p>
          <div className="flex items-center justify-center gap-4 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            <span>{sorted.length} {sorted.length === 1 ? 'Work' : 'Works'}</span>
            <span aria-hidden="true">·</span>
            <span>Public Domain</span>
          </div>
        </header>

        {/* Curated shelves entry point */}
        <div className="mt-8 mb-12 pb-8 border-b border-slate-800/60">
          <Link
            href="/library/shelves"
            className="font-sans text-xs uppercase tracking-[0.25em] text-slate-400 hover:text-emerald-400 transition-colors"
          >
            ◈ Browse curated shelves →
          </Link>
        </div>

        {/* Sort */}
        {sorted.length > 0 && (
          <nav
            aria-label="Sort works"
            className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 py-6 border-b border-slate-800/40 font-sans text-[10px] uppercase tracking-[0.2em]"
          >
            <span className="text-slate-600">Sort</span>
            {SORT_OPTIONS.map((opt) => {
              const active = opt.id === sortMode;
              const href = opt.id === 'author' ? '/library' : `/library?sort=${opt.id}`;
              return (
                <Link
                  key={opt.id}
                  href={href}
                  className={
                    active
                      ? 'text-emerald-300 border-b border-emerald-400/60 pb-0.5 transition-colors'
                      : 'text-slate-500 hover:text-slate-200 transition-colors'
                  }
                >
                  {opt.label}
                </Link>
              );
            })}
          </nav>
        )}

        {sorted.length === 0 ? (
          <div className="py-16 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            No works currently indexed. Run library_fetcher.py to ingest.
          </div>
        ) : (
          <ul className="border-t border-slate-800/40">
            {sorted.map((work) => {
              const hasChimera = typeof work.chimera_score === 'number';
              return (
                <li key={work.gutenberg_id} className="border-b border-slate-800/40">
                  <Link
                    href={`/library/${work.gutenberg_id}`}
                    className="flex items-center justify-between gap-4 py-5 px-2 -mx-2 hover:bg-slate-800/30 transition-colors group rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40"
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <h2 className="font-serif text-lg sm:text-xl text-slate-100 group-hover:text-slate-50 transition-colors leading-snug">
                        {work.title}
                      </h2>
                      <p className="font-serif italic text-sm text-slate-400 leading-snug">
                        {work.author || 'Unknown'}
                      </p>
                      <div className="flex items-center gap-3 flex-wrap font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                        <span>{work.download_count.toLocaleString()} downloads</span>
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

        {/* Footer */}
        <footer className="text-center pt-12 pb-6 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 space-y-2">
          <p>Sourced from <a href="https://www.gutenberg.org/" target="_blank" rel="noopener noreferrer" className="hover:text-slate-200 transition-colors">Project Gutenberg</a> · Public Domain</p>
          <p className="text-slate-600">{sorted.length} {sorted.length === 1 ? 'volume' : 'volumes'} indexed</p>
        </footer>
      </main>
    </div>
  );
}
