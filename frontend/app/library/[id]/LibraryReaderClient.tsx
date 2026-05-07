// Filename: /frontend/app/library/[id]/LibraryReaderClient.tsx
// Library reader — pills, translation banner, and body text.
// Client component. Reads ?lang=<code> from the URL and fetches the
// translation client-side, leaving the parent Server Component free to
// render English only (so Next.js ISR regeneration doesn't fan out into
// translation requests on every cache miss).

'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

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

const LANG_PILLS: { code: string; label: string }[] = [
  { code: 'de', label: 'Deutsch' },
  { code: 'fr', label: 'Français' },
  { code: 'es', label: 'Español' },
  { code: 'pt-br', label: 'Português (BR)' },
];

const LANG_CODE_RE = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$/i;

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

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

export default function LibraryReaderClient({ work }: { work: WorkResponse }) {
  const id = work.gutenberg_id;
  const workIsEnglish = (work.language || '').trim().toLowerCase() === 'en';

  const searchParams = useSearchParams();
  const rawLang = (searchParams.get('lang') || 'en').toLowerCase().trim();
  const requestedLang = LANG_CODE_RE.test(rawLang) ? rawLang : 'en';
  const effectiveLang: string = workIsEnglish ? requestedLang : 'en';

  const [translated, setTranslated] = useState<WorkResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (effectiveLang === 'en') {
      setTranslated(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(
      `${BACKEND}/api/library/${encodeURIComponent(id)}?lang=${encodeURIComponent(effectiveLang)}`,
    )
      .then((res) =>
        res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`)),
      )
      .then((data: WorkResponse) => {
        if (!cancelled) setTranslated(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Translation unavailable');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [effectiveLang, id]);

  const active: WorkResponse = translated ?? work;
  const isTranslated = !!translated?.is_translated && effectiveLang !== 'en';
  const isPreview = isTranslated && !!translated?.is_preview;
  const previewLangName =
    translated?.language_name ||
    LANG_PILLS.find((p) => p.code === effectiveLang)?.label ||
    effectiveLang;

  const text = active.text || '';
  const paragraphs = paragraphize(text);
  const lineLengths = text.split('\n').map((l) => l.length).filter((n) => n > 0);
  const avgLineLen =
    lineLengths.length > 0
      ? lineLengths.reduce((a, b) => a + b, 0) / lineLengths.length
      : 0;
  const renderAsVerse = lineLengths.length > 4 && avgLineLen > 0 && avgLineLen < 60;

  return (
    <>
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
            const isActive = effectiveLang === p.code;
            return (
              <Link
                key={p.code}
                href={buildHref(id, p.code)}
                className={
                  isActive
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

      {loading && (
        <p className="pt-6 font-serif italic text-sm text-slate-400 text-center">
          Translating to {previewLangName}…
        </p>
      )}

      {error && !translated && (
        <p className="pt-6 font-serif italic text-sm text-slate-400 text-center">
          Translation unavailable. Showing original English.
        </p>
      )}

      {active.translation_error && (
        <p className="pt-6 font-serif italic text-sm text-slate-400 text-center">
          Translation unavailable. Showing original English.
        </p>
      )}

      {isTranslated && (
        <p className="pt-6 font-serif italic text-sm text-slate-400 text-center">
          Translated from English. Translation by TranslateGemma 4B.
        </p>
      )}

      {isPreview && (
        <p className="max-w-prose mx-auto mt-8 mb-6 font-sans italic text-sm text-slate-400 text-center">
          Showing first ~8,000 characters in {previewLangName}. Switch to English for the complete text.
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
    </>
  );
}
