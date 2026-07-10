// Filename: /frontend/app/sources/page.tsx
// Sources — The Corpus (bibliography of ingested feeds)
// Librarian aesthetic: alphabetized, collapsible <details> sections.
// Crawlers index <details> body content even when collapsed.

import React from 'react';
import type { Metadata } from 'next';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Sources — Arc Codex',
  description: 'The corpus of publications and feeds powering the Arc Codex.',
};

export const revalidate = 3600;

interface Source {
  name: string;
  url: string;
  category: string;
}

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

/**
 * Strips RSS paths and returns only the publication's homepage so users land
 * on a human page instead of an XML feed download.
 */
function getPublicationHome(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    return `${url.protocol}//${url.hostname}`;
  } catch {
    return rawUrl;
  }
}

function getDomain(rawUrl: string): string {
  try {
    return new URL(rawUrl).hostname.replace(/^www\./, '');
  } catch {
    return rawUrl;
  }
}

async function getSources(): Promise<Source[]> {
  try {
    const res = await fetch(`${BACKEND}/api/sources`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export default async function SourcesPage() {
  const sources = await getSources();

  const grouped = new Map<string, Source[]>();
  for (const src of sources) {
    const cat = src.category || 'Uncategorized';
    if (!grouped.has(cat)) grouped.set(cat, []);
    grouped.get(cat)!.push(src);
  }

  const categories = Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([cat, srcs]) => ({
      name: cat,
      sources: srcs.slice().sort((a, b) => a.name.localeCompare(b.name)),
    }));

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            The Corpus
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Sources
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
            The {sources.length.toLocaleString()} origins of intelligence indexed by Arc Codex, organized across {categories.length} analytical {categories.length === 1 ? 'category' : 'categories'}.
          </p>
          <div className="flex items-center justify-center gap-4 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            <span>{sources.length.toLocaleString()} {sources.length === 1 ? 'Source' : 'Sources'}</span>
            <span aria-hidden="true">·</span>
            <span>{categories.length} {categories.length === 1 ? 'Category' : 'Categories'}</span>
          </div>
        </header>

        {/* Categories */}
        {categories.length === 0 ? (
          <div className="py-16 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            No sources currently indexed.
          </div>
        ) : (
          categories.map(({ name, sources: catSources }) => (
            <details
              key={name}
              open
              className="group/cat py-6 border-b border-slate-800/60"
            >
              <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer flex items-center justify-between gap-4 px-2 -mx-2 py-2 rounded-sm hover:bg-slate-800/30 transition-colors ring-focus">
                <div className="flex items-center gap-3">
                  <ChevronRight
                    className="h-3 w-3 text-slate-500 group-open/cat:rotate-90 transition-transform"
                    aria-hidden="true"
                  />
                  <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
                    {name}
                  </h2>
                </div>
                <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                  {catSources.length} {catSources.length === 1 ? 'Source' : 'Sources'}
                </span>
              </summary>

              <ul className="mt-4 border-t border-slate-800/40">
                {catSources.map((src) => {
                  const homeUrl = getPublicationHome(src.url);
                  const displayDomain = getDomain(homeUrl);
                  return (
                    <li key={src.url} className="border-b border-slate-800/40">
                      <a
                        href={homeUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex flex-col gap-1 py-4 px-3 -mx-3 hover:bg-slate-800/30 transition-colors rounded-sm ring-focus"
                      >
                        <h3 className="font-serif text-lg text-slate-100 leading-snug">
                          {src.name}
                        </h3>
                        <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                          {displayDomain}
                        </span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            </details>
          ))
        )}

        {/* Footer */}
        <footer className="text-center pt-12 pb-6 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 space-y-2">
          <p>A.R.C. Ingestion · {sources.length.toLocaleString()} active {sources.length === 1 ? 'voice' : 'voices'}</p>
          <p className="text-slate-600">Last sync · {new Date().toLocaleDateString()}</p>
        </footer>
      </main>
    </div>
  );
}
