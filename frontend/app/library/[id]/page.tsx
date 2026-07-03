// Filename: /frontend/app/library/[id]/page.tsx
// Library — single Project Gutenberg work, full text on one page.
// Server Component. Fetches the English work; the translation overlay
// (pills, banner, body swap on ?lang=) lives in LibraryReaderClient so
// Next.js ISR regeneration doesn't fan out into translation requests.

import React from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { ChevronLeft } from 'lucide-react';
import LibraryReaderClient from './LibraryReaderClient';

interface WorkResponse {
  gutenberg_id: string;
  title: string;
  author: string;
  language: string;
  subjects: string[];
  year_published: string;
  download_count: number;
  encoding: string;
  source_url: string;
  fetched_at: string;
  chimera_score: number | null;
  reading_label: string;
  chimera_skip_reason: string;
  fk_grade: number | null;
  coleman_liau: number | null;
  smog: number | null;
  dale_chall: number | null;
  scored_at: string;
  text: string;
  is_translated?: boolean;
  is_preview?: boolean;
  preview_chars?: number;
  total_chars?: number;
  language_name?: string;
  translation_error?: string;
}

const getChimeraColors = (score: number) => {
  if (score < 30) return { bar: 'bg-emerald-200', text: 'text-emerald-300' };
  if (score < 50) return { bar: 'bg-emerald-400', text: 'text-emerald-300' };
  if (score < 60) return { bar: 'bg-emerald-500', text: 'text-emerald-200' };
  if (score < 70) return { bar: 'bg-emerald-600', text: 'text-emerald-200' };
  if (score < 80) return { bar: 'bg-emerald-700', text: 'text-emerald-100' };
  return { bar: 'bg-emerald-900', text: 'text-emerald-100' };
};

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  'https://arc-codex.com';

export const revalidate = 3600;

async function getWork(id: string, lang: string): Promise<WorkResponse | null> {
  try {
    const url = lang && lang !== 'en'
      ? `${BACKEND}/api/library/${encodeURIComponent(id)}?lang=${encodeURIComponent(lang)}`
      : `${BACKEND}/api/library/${encodeURIComponent(id)}`;
    const res = await fetch(url, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const work = await getWork(id, 'en');
  if (!work) return { title: '404 — Arc Codex Library' };
  return {
    title: `${work.title} — ${work.author} — Arc Codex Library`,
    description: `${work.title} by ${work.author}, freely readable from Project Gutenberg via Arc Codex.`,
    alternates: {
      canonical: `https://arc-codex.com/library/${id}`,
      types: {
        'application/opensearchdescription+xml': '/opensearch.xml',
        'application/rss+xml': '/rss.xml',
      },
    },
  };
}

export default async function LibraryWorkPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const work = await getWork(id, 'en');
  if (!work) notFound();

  const gutenbergUrl = `https://www.gutenberg.org/ebooks/${work.gutenberg_id}`;
  const showChimera =
    typeof work.chimera_score === 'number' && work.chimera_skip_reason !== 'non-english';
  const chimeraColors = showChimera ? getChimeraColors(work.chimera_score as number) : null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Breadcrumb */}
        <nav
          aria-label="Breadcrumb"
          className="mb-12 flex items-center gap-3 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500"
        >
          <Link
            href="/library"
            className="flex items-center gap-1.5 hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
          >
            <ChevronLeft className="h-3 w-3" aria-hidden="true" />
            Library
          </Link>
          <span aria-hidden="true">/</span>
          <span className="text-slate-300 truncate">{work.author}</span>
        </nav>

        {/* Header */}
        <header className="pb-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.3em] text-slate-500">
            Project Gutenberg
          </div>
          <h1 className="font-serif text-4xl sm:text-5xl font-semibold tracking-tight text-slate-50 leading-tight">
            {work.title}
          </h1>
          <p className="font-serif italic text-xl text-slate-300">{work.author}</p>
          <div className="flex items-center gap-3 flex-wrap pt-2 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
            {work.year_published && <span>{work.year_published}</span>}
            {work.year_published && work.language && <span aria-hidden="true">·</span>}
            {work.language && <span>{work.language}</span>}
            <span aria-hidden="true">·</span>
            <span>Gutenberg #{work.gutenberg_id}</span>
            <span aria-hidden="true">·</span>
            <a
              href={gutenbergUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-200 transition-colors"
            >
              Original source
            </a>
          </div>

          {showChimera && chimeraColors && (
            <div
              className="flex items-center gap-3 pt-4"
              title="Chimera Difficulty Score — synthesizes Flesch-Kincaid, Coleman-Liau, SMOG, and Dale-Chall readability metrics. Computed on the first 30,000 characters."
            >
              <div className="flex items-center gap-2">
                <span className="font-sans text-[9px] font-semibold tracking-[0.25em] text-slate-500 uppercase">
                  Chimera
                </span>
                <span className={`font-mono text-2xl font-bold tabular-nums ${chimeraColors.text}`}>
                  {work.chimera_score}
                </span>
              </div>
              <div
                className="w-1 h-10 bg-slate-800 overflow-hidden flex flex-col-reverse"
                aria-hidden="true"
              >
                <div
                  className={`w-full ${chimeraColors.bar}`}
                  style={{ height: `${work.chimera_score}%` }}
                />
              </div>
              {work.reading_label && (
                <span
                  className={`font-sans text-[10px] font-semibold tracking-[0.2em] uppercase ${chimeraColors.text}`}
                >
                  {work.reading_label}
                </span>
              )}
              <span className="font-sans text-[9px] tracking-[0.15em] text-slate-600 uppercase ml-2 hidden sm:inline">
                FK {work.fk_grade ?? '—'} · CL {work.coleman_liau ?? '—'} · SMOG {work.smog ?? '—'} · DC {work.dale_chall ?? '—'}
              </span>
            </div>
          )}
        </header>

        <LibraryReaderClient work={work} />

        {/* Footer */}
        <footer className="border-t border-slate-800/60 pt-10 pb-6 mt-12 space-y-3 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <p>
            <Link href="/library" className="hover:text-slate-200 transition-colors">
              ← Back to the Library
            </Link>
          </p>
          <p>
            <a
              href={gutenbergUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-200 transition-colors"
            >
              View on Project Gutenberg
            </a>
          </p>
          <p className="text-slate-600 normal-case tracking-normal font-serif italic text-xs pt-2">
            Project Gutenberg works are free of copyright in the United States; license terms apply elsewhere.
          </p>
        </footer>
      </main>
    </div>
  );
}
