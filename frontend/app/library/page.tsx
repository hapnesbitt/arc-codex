// Filename: /frontend/app/library/page.tsx
// Library landing — curated shelves only. Server Component.
//
// Previous version fetched all 6,595 works from /api/library and rendered
// them as one list. That payload + DOM made the page unusable. Books now
// live one click deeper at /library/shelf/<slug>.

import React from 'react';
import Link from 'next/link';
import type { Metadata } from 'next';
import { ChevronRight } from 'lucide-react';
import LibrarySearch from './LibrarySearch';

export const metadata: Metadata = {
  title: 'Library — Arc Codex',
  description: 'Curated shelves of public-domain works, freely readable — drawn from Project Gutenberg.',
  alternates: {
    canonical: 'https://arc-codex.com/library',
    types: {
      'application/opensearchdescription+xml': '/opensearch.xml',
      'application/rss+xml': '/rss.xml',
    },
  },
};

export const revalidate = 3600;

interface Shelf {
  slug: string;
  name: string;
  description: string;
  gutenberg_bookshelf_id: string;
  book_count: number;
}

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

async function getShelves(): Promise<Shelf[]> {
  try {
    const res = await fetch(`${BACKEND}/api/library/shelves`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

// Distinct works count from the API. NOT the sum of shelf book_count, which
// double-counts works that sit on more than one shelf.
async function getTotalWorks(): Promise<number> {
  try {
    const res = await fetch(`${BACKEND}/api/library/stats`, { next: { revalidate: 3600 } });
    if (!res.ok) return 0;
    const d = await res.json();
    return d.works ?? 0;
  } catch {
    return 0;
  }
}

export default async function LibraryPage() {
  const [shelves, totalWorks] = await Promise.all([getShelves(), getTotalWorks()]);

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
            Curated shelves of public-domain works, freely readable — drawn from Project Gutenberg.
          </p>
          <p className="font-serif text-sm text-slate-500 italic leading-relaxed max-w-xl mx-auto">
            Books may be read in English (original) or translated on demand to German, French, Spanish, or Brazilian Portuguese.
          </p>
          <div className="flex items-center justify-center gap-4 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            <span>{shelves.length} {shelves.length === 1 ? 'Shelf' : 'Shelves'}</span>
            <span aria-hidden="true">·</span>
            <span>{totalWorks.toLocaleString()} Works</span>
            <span aria-hidden="true">·</span>
            <span>Public Domain</span>
          </div>
        </header>

        <LibrarySearch />

        {shelves.length === 0 ? (
          <div className="py-16 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            No shelves currently indexed. Run library_fetcher.py to populate.
          </div>
        ) : (
          <ul className="border-t border-slate-800/40 mt-8">
            {shelves.map((shelf) => (
              <li key={shelf.slug} className="border-b border-slate-800/40">
                <Link
                  href={`/library/shelf/${shelf.slug}`}
                  className="flex items-center justify-between gap-4 py-6 px-2 -mx-2 hover:bg-slate-800/30 transition-colors group rounded-sm ring-focus"
                >
                  <div className="min-w-0 flex-1 space-y-2">
                    <h2 className="font-sans text-sm uppercase tracking-[0.25em] text-slate-100 group-hover:text-emerald-300 transition-colors">
                      {shelf.name}
                    </h2>
                    {shelf.description && (
                      <p className="font-serif italic text-sm text-slate-400 leading-snug">
                        {shelf.description}
                      </p>
                    )}
                    <div className="flex items-center gap-3 flex-wrap font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                      <span>{shelf.book_count} {shelf.book_count === 1 ? 'work' : 'works'}</span>
                    </div>
                  </div>
                  <ChevronRight
                    className="h-4 w-4 text-slate-600 group-hover:text-slate-300 transition-colors shrink-0"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}

        {/* Footer */}
        <footer className="text-center pt-12 pb-6 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 space-y-2">
          <p>
            Sourced from{' '}
            <a
              href="https://www.gutenberg.org/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-200 transition-colors"
            >
              Project Gutenberg
            </a>{' '}
            · Public Domain
          </p>
          <p className="text-slate-600">
            {totalWorks.toLocaleString()} {totalWorks === 1 ? 'volume' : 'volumes'} indexed across {shelves.length} {shelves.length === 1 ? 'shelf' : 'shelves'}
          </p>
        </footer>
      </main>
    </div>
  );
}
