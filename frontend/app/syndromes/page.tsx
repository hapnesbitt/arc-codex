// Filename: /frontend/app/syndromes/page.tsx
// Syndromes index — curated table of contents over arc-codex condition pages.
// Uses the same catalog pattern as /plants; per-condition pages (e.g. /syndromes/eds)
// remain hand-authored and are linked from here.
//
// NOTE: The bg/breadcrumb/<main> wrapper come from /syndromes/layout.tsx,
// so this page only renders the inner content.

import type { Metadata } from 'next';
import Link from 'next/link';
import { Microscope } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Syndromes',
  description:
    'Research notes on conditions worth understanding — an index of condition-specific intelligence units in Arc Codex.',
};

// 5-minute revalidation matches the backend cache window.
export const revalidate = 300;

interface SyndromeEntry {
  common: string;
  classification: string;
  url: string;
}

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  'https://arc-codex.com';

async function getSyndromes(): Promise<SyndromeEntry[]> {
  try {
    const res = await fetch(`${BACKEND}/api/syndromes`, { next: { revalidate: 300 } });
    if (!res.ok) return [];
    const data = await res.json();
    return data.syndromes ?? [];
  } catch {
    return [];
  }
}

function SyndromeRow({ entry }: { entry: SyndromeEntry }) {
  return (
    <li className="border-b border-slate-800/40">
      <Link
        href={entry.url}
        className="group flex items-baseline gap-3 py-3 px-3 -mx-3 rounded-sm hover:bg-slate-800/40 transition-colors ring-focus"
      >
        <span className="font-serif text-base sm:text-lg font-semibold text-amber-300 group-hover:text-amber-200 transition-colors leading-snug">
          {entry.common}
        </span>
        <span className="font-serif italic text-sm text-slate-400 group-hover:text-slate-300 transition-colors leading-snug truncate">
          {entry.classification}
        </span>
      </Link>
    </li>
  );
}

export default async function SyndromesIndex() {
  const syndromes = await getSyndromes();

  return (
    <>
      <header className="text-center py-10 border-b border-slate-800/60 space-y-4">
        <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
          Condition Intelligence
        </div>
        <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
          Syndromes
        </h1>
        <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
          Research notes on conditions worth understanding.
        </p>
      </header>

      <section className="py-8 border-b border-slate-800/60">
        <header className="flex items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            <Microscope className="h-3.5 w-3.5 text-amber-400/70" aria-hidden="true" />
            <h2 className="font-sans text-xs uppercase tracking-[0.4em] font-semibold text-slate-300">
              Available
            </h2>
          </div>
          <span className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            {syndromes.length} {syndromes.length === 1 ? 'entry' : 'entries'}
          </span>
        </header>

        {syndromes.length === 0 ? (
          <p className="py-10 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            Catalog unavailable.
          </p>
        ) : (
          <ul className="border-t border-slate-800/40">
            {syndromes.map((s) => (
              <SyndromeRow key={s.url} entry={s} />
            ))}
          </ul>
        )}
      </section>

      <footer className="text-center pt-10 pb-4 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 space-y-2">
        <p>
          {syndromes.length} {syndromes.length === 1 ? 'syndrome' : 'syndromes'} · more coming
        </p>
        <p className="text-slate-600">A.R.C. Condition Registry · {new Date().getFullYear()}</p>
      </footer>
    </>
  );
}
