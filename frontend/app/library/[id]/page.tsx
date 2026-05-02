// Filename: /frontend/app/library/[id]/page.tsx
// Library — single Project Gutenberg work, full text on one page.
// Server Component. Translation is URL-driven via ?lang=<code>.

import React from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { ChevronLeft } from 'lucide-react';

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
  translation_error?: string;
}

const LANG_PILLS: { code: string; label: string }[] = [
  { code: 'de', label: 'Deutsch' },
  { code: 'fr', label: 'Français' },
  { code: 'es', label: 'Español' },
  { code: 'pt-br', label: 'Português (BR)' },
];

const LANG_CODE_RE = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$/i;

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
  };
}

function paragraphize(raw: string): string[] {
  const blocks = raw.replace(/\r\n/g, '\n').split(/\n\s*\n+/);
  return blocks
    .map((block) => {
      const trimmed = block.replace(/\n+$/g, '');
      const lines = trimmed.split('\n').filter(Boolean);
      const isVerse = lines.length > 1 && lines.every((l) => l.length < 60);
      return isVerse ? trimmed : trimmed.replace(/\n/g, ' ').replace(/\s{2,}/g, ' ').trim();
    })
    .filter(Boolean);
}

function buildHref(id: string, code: string | null): string {
  if (!code || code === 'en') return `/library/${id}`;
  return `/library/${id}?lang=${encodeURIComponent(code)}`;
}

export default async function LibraryWorkPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ lang?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;

  const requestedLang = (sp?.lang || 'en').toLowerCase().trim();
  const lang: string = LANG_CODE_RE.test(requestedLang) ? requestedLang : 'en';

  const work = await getWork(id, lang);
  if (!work) notFound();

  const workIsEnglish = (work.language || '').trim().toLowerCase() === 'en';
  const effectiveLang: string = workIsEnglish ? lang : 'en';
  const isTranslated = !!work.is_translated && effectiveLang !== 'en';

  const gutenbergUrl = `https://www.gutenberg.org/ebooks/${work.gutenberg_id}`;
  const showChimera =
    typeof work.chimera_score === 'number' && work.chimera_skip_reason !== 'non-english';
  const chimeraColors = showChimera ? getChimeraColors(work.chimera_score as number) : null;

  const text = work.text || '';
  const paragraphs = paragraphize(text);
  const lineLengths = text.split('\n').map((l) => l.length).filter((n) => n > 0);
  const avgLineLen =
    lineLengths.length > 0
      ? lineLengths.reduce((a, b) => a + b, 0) / lineLengths.length
      : 0;
  const renderAsVerse = lineLengths.length > 4 && avgLineLen > 0 && avgLineLen < 60;

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

          {/* Language pills (English originals only) */}
          {workIsEnglish && (
            <div className="pt-4 flex flex-wrap items-center gap-2">
              <Link
                href={buildHref(id, null)}
                className={
                  effectiveLang === 'en'
                    ? 'px-3 py-1.5 rounded-full bg-amber-500 text-black text-[10px] font-black uppercase tracking-widest'
                    : 'px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-slate-400 hover:text-white hover:bg-white/10 transition-all text-[10px] font-bold uppercase tracking-widest'
                }
              >
                English
              </Link>
              {LANG_PILLS.map((p) => {
                const active = effectiveLang === p.code;
                return (
                  <Link
                    key={p.code}
                    href={buildHref(id, p.code)}
                    className={
                      active
                        ? 'px-3 py-1.5 rounded-full bg-amber-500 text-black text-[10px] font-black uppercase tracking-widest'
                        : 'px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:bg-blue-500/20 transition-all text-[10px] font-bold uppercase tracking-widest'
                    }
                  >
                    {p.label}
                  </Link>
                );
              })}
            </div>
          )}
        </header>

        {work.translation_error && (
          <p className="pt-6 font-serif italic text-sm text-slate-400 text-center">
            Translation unavailable. Showing original English.
          </p>
        )}

        {isTranslated && (
          <p className="pt-6 font-serif italic text-sm text-slate-400 text-center">
            Translated from English. Translation by TranslateGemma 4B.
          </p>
        )}

        {/* Body */}
        {paragraphs.length === 0 ? (
          <div className="py-16 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            No body text available.
          </div>
        ) : renderAsVerse ? (
          <article className="py-10 font-serif text-lg text-slate-200 leading-[1.75] [text-wrap:pretty]">
            <pre className="font-serif whitespace-pre-wrap text-lg text-slate-200 leading-[1.75]">
              {text}
            </pre>
          </article>
        ) : (
          <article className="py-10 font-serif text-lg text-slate-200 leading-[1.75] [text-wrap:pretty]">
            {paragraphs.map((p, i) => {
              if (p.includes('\n')) {
                return (
                  <pre
                    key={i}
                    className="font-serif whitespace-pre-wrap text-lg text-slate-200 leading-[1.75] mb-6"
                  >
                    {p}
                  </pre>
                );
              }
              return (
                <p key={i} className="mb-6">
                  {p}
                </p>
              );
            })}
          </article>
        )}

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
