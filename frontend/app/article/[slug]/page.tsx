import React, { Suspense } from 'react';
import { notFound } from 'next/navigation';
import { Play } from 'lucide-react';
import ArticleView from '@/components/ArticleView';
import CopyAllButton from '@/components/CopyAllButton';
import BackButton from '@/components/BackButton';
import type { Article, Comment, Dossier } from '@/lib/types';
import type { Metadata } from 'next';

// Anonymous ISR: same HTML for every visitor. searchParams (`?lang=`) reading
// moved to the client wrapper so this render is not forced dynamic.
export const revalidate = 60;

interface PageProps {
  params: Promise<{
    slug: string;
  }>;
}

// --- DATA FETCHING ---
const serverBackendUrl = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

async function getArticleData(articleId: string): Promise<Article | null> {
  try {
    const res = await fetch(
      `${serverBackendUrl}/api/article/${articleId}`,
      { next: { revalidate: 60 } },
    );

    if (res.ok) {
      return await res.json();
    }

    if (res.status === 404) {
      return null;
    }

    console.error(`API error ${res.status} for article ${articleId}`);
    return null;
  } catch (error) {
    console.error(`Failed to fetch article ${articleId}:`, error);
    return null;
  }
}

async function getArticleComments(articleId: string): Promise<Comment[]> {
  try {
    const res = await fetch(
      `${serverBackendUrl}/api/article/${articleId}/comments`,
      { next: { revalidate: 60 } },
    );

    if (res.ok) {
      return await res.json();
    }

    return [];
  } catch (error) {
    console.error(`Failed to fetch comments for ${articleId}:`, error);
    return [];
  }
}

// --- METADATA GENERATION ---
export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const params = await props.params;
  const article = await getArticleData(params.slug);

  if (!article) {
    return {
      title: "404 | Intelligence Missing",
      description: "The requested article could not be found.",
      robots: 'noindex'
    };
  }

  let dossier: Dossier = {};
  if (article.dossier) {
    dossier = typeof article.dossier === 'string'
      ? JSON.parse(article.dossier)
      : article.dossier;
  }

  // chimera_score is already 0-100 (Arc's readability composite) — do not
  // *100 it. sentiment is VADER's -1..1 compound score, which does need
  // the *100 to read as a rough percentage. These are different scales;
  // blending them through one shared `* 100` (as this used to) rendered
  // "Chimera Score: 6900/100" whenever chimera_score was present. See
  // ops/RUNBOOK.md 2026-08-27.
  const formattedScore = dossier.chimera_score != null
    ? Math.round(dossier.chimera_score)
    : Math.round((dossier.sentiment ?? 0) * 100);

  const stripMd = (text: string) =>
    text.replace(/^#{1,6}\s+/gm, '').replace(/\*{1,3}(.*?)\*{1,3}/g, '$1')
        .replace(/^[-*]\s+/gm, '').replace(/^>\s+/gm, '').replace(/^---+$/gm, '').trim();

  const rawDesc =
    article.purple_team_analysis ||
    article.blue_team_analysis ||
    article.original_text ||
    `Arc Codex Intelligence Analysis - A.R.C. Score: ${formattedScore}/100`;

  const description = stripMd(rawDesc).substring(0, 155);

  return {
    title: `${article.title} — Arc Codex`,
    description,
    alternates: {
      canonical: `https://arc-codex.com/article/${params.slug}`,
    },
    openGraph: {
      title: article.title,
      description,
      url: `https://arc-codex.com/article/${params.slug}`,
      siteName: 'Arc Codex',
      images: [
        {
          url: article.imageUrl || 'https://arc-codex.com/default-article-image.jpg',
          width: 1200,
          height: 675,
          alt: article.title,
        }
      ],
      type: 'article',
      publishedTime: article.timestamp,
    },
    twitter: {
      card: 'summary_large_image',
      title: article.title,
      description,
      images: [article.imageUrl || 'https://arc-codex.com/default-article-image.jpg'],
    },
  };
}

// --- MAIN PAGE COMPONENT ---
export default async function ArticlePage(props: PageProps) {
  const params = await props.params;

  const [article, comments] = await Promise.all([
    getArticleData(params.slug),
    getArticleComments(params.slug)
  ]);

  if (!article) {
    notFound();
  }

  return (
    <div className="min-h-screen bg-[#050505] bg-[radial-gradient(circle_at_top,_var(--tw-gradient-stops))] from-amber-900/10 via-transparent to-transparent text-slate-200">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Navigation Bar */}
        <nav
          aria-label="Article navigation"
          className="mb-10 flex items-center justify-between print:hidden"
        >
          <BackButton />

          <div className="flex items-center gap-3">
            {article.sourceUrl?.includes('vid.arc-codex.com') && (
              <a
                href={article.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500/10 border border-blue-500/30 text-blue-300 hover:bg-blue-500/20 hover:border-blue-400/50 transition-all duration-300 text-[10px] font-black uppercase tracking-widest"
              >
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                Watch on LightBox
              </a>
            )}
            <CopyAllButton article={article} comments={comments} />
          </div>
        </nav>

        {/* Intelligence Container */}
        <article className="animate-in fade-in slide-in-from-bottom-4 duration-700">
          <Suspense fallback={null}>
            <ArticleView article={article} comments={comments} />
          </Suspense>
        </article>

        {/* Vertical alignment guide / footer spacer */}
        <footer className="h-24 flex items-center justify-center opacity-20 print:hidden">
           <div className="w-0.5 bg-gradient-to-b from-amber-500 to-transparent h-full rounded-full" />
        </footer>
      </main>
    </div>
  );
}
