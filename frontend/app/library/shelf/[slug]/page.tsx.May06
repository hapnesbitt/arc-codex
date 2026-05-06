// Filename: /frontend/app/library/shelf/[slug]/page.tsx
// Library — single curated shelf detail page. Server Component.

import React from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { ChevronRight } from 'lucide-react';

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

interface ShelfDetail {
  slug: string;
  name: string;
  description: string;
  gutenberg_bookshelf_id: string;
  fetched_at: string;
  book_count: number;
  books: Work[];
}

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

async function getShelf(slug: string): Promise<ShelfDetail | null> {
  try {
    const res = await fetch(`${BACKEND}/api/library/shelf/${encodeURIComponent(slug)}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const shelf = await getShelf(slug);
  if (!shelf) {
    return { title: 'Shelf — Arc Codex Library' };
  }
  return {
    title: `${shelf.name} — Arc Codex Library`,
    description: shelf.description || `Curated shelf of public-domain works: ${shelf.name}.`,
  };
}

export default async function LibraryShelfDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const shelf = await getShelf(slug);
  if (!shelf) notFound();

  const books = shelf.books ?? [];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Curated Shelf
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            {shelf.name}
          </h1>
          {shelf.description && (
            <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
              {shelf.description}
            </p>
          )}
          <div className="flex items-center justify-center gap-4 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 flex-wrap">
            <span>{books.length} {books.length === 1 ? 'Work' : 'Works'}</span>
            {shelf.gutenberg_bookshelf_id && (
              <>
                <span aria-hidden="true">·</span>
                <span>
                  Drawn from{' '}
                  <a
                    href={`https://www.gutenberg.org/ebooks/bookshelf/${shelf.gutenberg_bookshelf_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-slate-200 transition-colors"
                  >
                    Project Gutenberg Bookshelf #{shelf.gutenberg_bookshelf_id}
                  </a>
                </span>
              </>
            )}
          </div>
        </header>

        {books.length === 0 ? (
          <div className="py-16 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            No works in this shelf yet. Run the library fetcher to populate.
          </div>
        ) : (
          <ul className="border-t border-slate-800/40 mt-8">
            {books.map((work) => {
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
          <p>
            <Link href="/library/shelves" className="hover:text-slate-200 transition-colors">
              ← All Shelves
            </Link>
          </p>
        </footer>
      </main>
    </div>
  );
}
