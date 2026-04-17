import React from 'react';
import { readFileSync } from 'fs';
import { join } from 'path';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import type { Metadata } from 'next';
import { Flashlight } from 'lucide-react';

interface WikiArticle {
  id: string;
  title: string;
  source_name: string;
  timestamp: string;
  sourceUrl: string;
  purple_team_analysis: string;
  chimera_score: number;
}

interface DirectiveEntry {
  name: string;
}

interface TopicGroup {
  topic: string;
  directives: DirectiveEntry[];
}

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
    const res = await fetch(
      `${BACKEND}/api/wiki/${encodeURIComponent(directiveName)}`,
      { next: { revalidate: 300 } }
    );
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const { slug } = await props.params;
  const resolved = resolveDirective(slug);
  if (!resolved) return { title: '404 — Arc Codex Wiki' };
  return {
    title: `${resolved.name} — Arc Codex Wiki`,
    description: `Arc Codex analysis on ${resolved.name}: AI-powered intelligence synthesis.`,
    alternates: { canonical: `https://arc-codex.com/wiki/${slug}` },
    openGraph: {
      title: `${resolved.name} — Arc Codex Wiki`,
      description: `Arc Codex analysis on ${resolved.name}: AI-powered intelligence synthesis.`,
      url: `https://arc-codex.com/wiki/${slug}`,
      siteName: 'Arc Codex',
    },
  };
}

export default async function WikiDirectivePage(props: PageProps) {
  const { slug } = await props.params;
  const resolved = resolveDirective(slug);
  if (!resolved) notFound();

  const articles = await getWikiArticles(resolved.name);

  return (
    <div className="min-h-screen bg-[#050505] text-slate-200">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <nav aria-label="Breadcrumb" className="mb-6 flex items-center gap-2 text-sm text-slate-500 flex-wrap">
          <Link href="/" className="hover:text-amber-400 transition-colors">Home</Link>
          <span>/</span>
          <Link href="/wiki" className="hover:text-amber-400 transition-colors">Wiki</Link>
          <span>/</span>
          <span className="text-slate-400">{resolved.topic}</span>
          <span>/</span>
          <span className="text-slate-200">{resolved.name}</span>
        </nav>

        <header className="mb-8">
          <h1 className="font-serif text-3xl font-bold text-slate-50 mb-2">{resolved.name}</h1>
          <p className="text-slate-500 text-sm">
            {articles.length} article{articles.length !== 1 ? 's' : ''} with A.R.C. analysis — newest first
          </p>
        </header>

        {articles.length === 0 ? (
          <p className="text-slate-500 italic text-sm">No analyzed articles in this directive yet.</p>
        ) : (
          <ol className="space-y-5">
            {articles.map(article => (
              <li
                key={article.id}
                id={`article-${article.id}`}
                className="border border-slate-700/60 rounded-xl p-5 bg-slate-900/30 hover:border-slate-600/60 transition-colors"
              >
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <Link
                      href={`/article/${article.id}`}
                      className="font-serif text-lg font-semibold text-slate-100 hover:text-amber-300 transition-colors leading-snug"
                    >
                      {article.title}
                    </Link>

                    <p className="text-xs text-slate-500 mt-1">
                      {article.source_name || 'Unknown source'}
                      {article.timestamp && (
                        <>
                          {' · '}
                          <time dateTime={article.timestamp}>
                            {new Date(article.timestamp).toLocaleDateString([], {
                              year: 'numeric', month: 'short', day: 'numeric',
                            })}
                          </time>
                        </>
                      )}
                    </p>

                    {article.purple_team_analysis && (
                      <>
                        <p className="text-slate-400 text-sm mt-3 leading-relaxed line-clamp-3">
                          {article.purple_team_analysis.slice(0, 300)}
                        </p>
                        {/* Full text in <details> for search engine indexing */}
                        <details className="mt-2">
                          <summary className="text-xs text-slate-600 hover:text-slate-400 cursor-pointer transition-colors select-none">
                            Full analysis ▸
                          </summary>
                          <p className="text-slate-500 text-sm mt-2 leading-relaxed whitespace-pre-line">
                            {article.purple_team_analysis}
                          </p>
                        </details>
                      </>
                    )}
                  </div>

                  <a
                    href={`/article/${article.id}`}
                    aria-label={`Full take — open full analysis for ${article.title}`}
                    title="Full Take"
                    className="flex-shrink-0 inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-500 hover:text-purple-400 hover:bg-white/5 transition-all mt-0.5"
                  >
                    <Flashlight className="h-4 w-4" aria-hidden="true" />
                  </a>
                </div>
              </li>
            ))}
          </ol>
        )}
      </main>
    </div>
  );
}
