import React from 'react';
import Link from 'next/link';
import { ArrowLeft, ShieldAlert, Play } from 'lucide-react';
import IntelligenceCard from '@/components/IntelligenceCard';
import CopyAllButton from '@/components/CopyAllButton';
import BackButton from '@/components/BackButton';
import type { Article, Comment, Dossier } from '@/lib/types';
import type { Metadata } from 'next';

interface PageProps {
  params: Promise<{
    slug: string;
  }>;
  searchParams: Promise<{ lang?: string }>;
}

// --- DATA FETCHING ---
const serverBackendUrl = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

async function getArticleData(articleId: string): Promise<Article | null> {
  try {
    const res = await fetch(
      `${serverBackendUrl}/api/article/${articleId}`,
      { next: { revalidate: 300 } } // 5 min cache
    );
    
    if (res.ok) {
      return await res.json();
    }
    
    // Only log 404s once 
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
      { next: { revalidate: 60 } } // 1 min cache
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

  // Parse dossier if it's a string 
  let dossier: Dossier = {};
  if (article.dossier) {
    dossier = typeof article.dossier === 'string' 
      ? JSON.parse(article.dossier) 
      : article.dossier;
  }

  const score = dossier.chimera_score || dossier.sentiment || 0;
  const formattedScore = Math.round(score * 100);

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
          height: 630,
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

// --- NOT FOUND COMPONENT ---
function ArticleNotFound() {
  return (
    <div className="min-h-screen bg-[#050505] text-slate-200 flex flex-col items-center justify-center px-4">
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <div className="p-4 rounded-full bg-red-500/10 border border-red-500/20 animate-pulse">
            <ShieldAlert className="h-12 w-12 text-red-500" />
          </div>
        </div>
        <div>
          <h1 className="text-2xl font-black uppercase tracking-[0.2em] text-white mb-2">
            Intelligence Missing
          </h1>
          <p className="text-slate-500 text-sm max-w-xs mx-auto leading-relaxed">
            The requested slug does not exist in the current repository or has been purged.
          </p>
        </div>
        <Link 
          href="/" 
          className="inline-flex items-center gap-2 px-6 py-3 bg-white/5 hover:bg-white/10 border border-white/10 text-white rounded-xl transition-all font-bold text-xs uppercase tracking-widest"
        >
          <ArrowLeft className="h-4 w-4" />
          Return to Nexus
        </Link>
      </div>
    </div>
  );
}

// --- MAIN PAGE COMPONENT ---
export default async function ArticlePage(props: PageProps) {
  const params = await props.params;
  const searchParams = await props.searchParams;
  const initialLang = searchParams.lang || null;

  // Fetch article and comments in parallel 
  const [article, comments] = await Promise.all([
    getArticleData(params.slug),
    getArticleComments(params.slug)
  ]);

  if (!article) {
    return <ArticleNotFound />;
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
          <IntelligenceCard
            card={article}
            comments={comments}
            isCompact={false}
            initialLang={initialLang}
            defaultExpandedSection="purpleTeam"
            fullyExpanded
          />
        </article>

        {/* Vertical alignment guide / footer spacer */}
        <footer className="h-24 flex items-center justify-center opacity-20 print:hidden">
           <div className="w-0.5 bg-gradient-to-b from-amber-500 to-transparent h-full rounded-full" />
        </footer>
      </main>
    </div>
  );
}
