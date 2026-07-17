// Filename: /frontend/app/wiki/[slug]/page.tsx
// Wiki — Single Directive Page
// Librarian aesthetic: hairline-separated stack of articles. Each <li> carries
// id="article-{id}" and the full purple_team_analysis sits inside <details> so
// crawlers index the body even while users see a quiet preview.

import React from 'react';
import { readFileSync } from 'fs';
import { join } from 'path';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import type { Metadata } from 'next';
import { Flashlight, ChevronLeft } from 'lucide-react';

interface WikiArticle {
  id: string;
  title: string;
  source_name: string;
  timestamp: string;
  sourceUrl: string;
  purple_team_analysis: string;
  chimera_score: number;
}

interface DirectiveEntry { name: string; }
interface TopicGroup { topic: string; directives: DirectiveEntry[]; }

// Anonymous ISR — public directive index, no per-user personalization.
// Backend already filters visibility != 'private' (main.py /api/wiki route).
export const revalidate = 300;

const toSlug = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

function resolveDirective(slug: string): { name: string; topic: string } | null {
  const directivesPath = join(process.cwd(), 'public', 'directives.json');
  const groups: TopicGroup[] = JSON.parse(readFileSync(directivesPath, 'utf-8'));
  for (const group of groups) {
    if (group.topic === 'System Directives') continue;
    for (const d of group.directives) {
      if (toSlug(d.name) === slug) return { name: d.name, topic: group.topic };
    }
  }
  return null;
}

async function getWikiArticles(directiveName: string): Promise<WikiArticle[]> {
  try {
    const res = await fetch(`${BACKEND}/api/wiki/${encodeURIComponent(directiveName)}`, { next: { revalidate: 300 } });
    return res.ok ? await res.json() : [];
  } catch { return []; }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const resolved = resolveDirective(slug);
  if (!resolved) return { title: '404 — Arc Codex Wiki' };
  return {
    title: `${resolved.name} — Arc Codex Library`,
    description: `Intelligence entries classified under ${resolved.name} within the A.R.C. Framework.`,
    alternates: {
      canonical: `https://arc-codex.com/wiki/${slug}`,
      types: {
        'application/opensearchdescription+xml': '/opensearch.xml',
        'application/rss+xml': '/rss.xml',
      },
    },
  };
}

export default async function WikiDirectivePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const resolved = resolveDirective(slug);
  if (!resolved) notFound();

  const articles = await getWikiArticles(resolved.name);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* Breadcrumb */}
        <nav
          aria-label="Breadcrumb"
          className="mb-12 flex items-center gap-3 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500"
        >
          <Link
            href="/wiki"
            className="flex items-center gap-1.5 hover:text-slate-200 transition-colors ring-focus rounded-sm"
          >
            <ChevronLeft className="h-3 w-3" aria-hidden="true" />
            Library
          </Link>
          <span aria-hidden="true">/</span>
          <span className="text-slate-300">{resolved.topic}</span>
        </nav>

        {/* Directive header */}
        <header className="pb-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.3em] text-slate-500">
            Directive
          </div>
          <h1 className="font-serif text-4xl sm:text-5xl font-semibold tracking-tight text-slate-50 leading-tight">
            {resolved.name}
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl">
            Forensic ledger of intelligence entries classified under this directive — filtered through the A.R.C. Analytical Triad.
          </p>
          <div className="flex items-center gap-4 pt-2 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
            <span>{articles.length} {articles.length === 1 ? 'Entry' : 'Entries'}</span>
            <span aria-hidden="true">·</span>
            <span>{resolved.topic}</span>
          </div>
        </header>

        {/* Articles */}
        {articles.length === 0 ? (
          <div className="py-16 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            No entries currently recorded under this directive.
          </div>
        ) : (
          <ul>
            {articles.map((article) => {
              const preview = article.purple_team_analysis
                ? `${article.purple_team_analysis.slice(0, 320)}…`
                : 'No purple-team analysis available.';
              const chimera = typeof article.chimera_score === 'number' ? Math.round(article.chimera_score) : null;
              return (
                <li
                  key={article.id}
                  id={`article-${article.id}`}
                  className="py-10 border-b border-slate-800/60"
                >
                  <article className="space-y-4">
                    <div className="flex items-center gap-3 flex-wrap font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                      <span>{article.source_name || 'Unknown Source'}</span>
                      <span aria-hidden="true">·</span>
                      <time dateTime={article.timestamp}>
                        {new Date(article.timestamp).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}
                      </time>
                      {chimera !== null && chimera > 0 && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>Chimera {chimera}</span>
                        </>
                      )}
                    </div>

                    <Link
                      href={`/article/${article.id}`}
                      className="block group ring-focus rounded-sm"
                    >
                      <h2 className="font-serif text-2xl sm:text-3xl font-semibold tracking-tight text-slate-50 leading-snug group-hover:text-slate-100 transition-colors">
                        {article.title}
                      </h2>
                    </Link>

                    <p className="font-serif text-base text-slate-300 italic line-clamp-3 leading-relaxed">
                      {preview}
                    </p>

                    {article.purple_team_analysis && (
                      <details className="font-serif">
                        <summary className="list-none cursor-pointer inline-flex items-center gap-2 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 hover:text-slate-200 transition-colors marker:hidden ring-focus rounded-sm">
                          Read full analysis
                        </summary>
                        <div className="mt-4 text-base text-slate-300 leading-relaxed whitespace-pre-line">
                          {article.purple_team_analysis}
                        </div>
                      </details>
                    )}

                    <div className="pt-1">
                      <Link
                        href={`/article/${article.id}`}
                        className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors ring-focus rounded-sm"
                      >
                        <Flashlight className="h-3 w-3" aria-hidden="true" />
                        Full take
                      </Link>
                    </div>
                  </article>
                </li>
              );
            })}
          </ul>
        )}

        {/* Footer */}
        <footer className="text-center pt-12 pb-6 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <p>A.R.C. Codex · {resolved.topic}</p>
        </footer>
      </main>
    </div>
  );
}
