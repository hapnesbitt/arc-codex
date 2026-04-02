import React from 'react';
import Link from 'next/link';
import { ArrowLeft, Home, ShieldAlert } from 'lucide-react';
import IntelligenceCard from '@/components/IntelligenceCard';
import CopyAllButton from '@/components/CopyAllButton';
import type { Article, Comment, Dossier } from '@/lib/types';
import type { Metadata } from 'next';

interface PageProps {
  params: Promise<{
    slug: string;
  }>;
  searchParams: Promise<{ lang?: string }>;
}

// --- DATA FETCHING ---
async function getArticleData(articleId: string): Promise<Article | null> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/article/${articleId}`,
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
      `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/article/${articleId}/comments`,
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

  // Use purple team for description 
  const description = 
    article.purple_team_analysis?.substring(0, 160) ||
    article.blue_team_analysis?.substring(0, 160) || 
    article.original_text?.substring(0, 160) ||
    `Arc Codex Intelligence Analysis - A.R.C. Score: ${formattedScore}/100`;

  return { 
    title: `${article.title} | Arc Codex`,
    description,
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
          className="mb-10 flex items-center justify-between"
        >
          <Link 
            href="/" 
            className="group flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/5 text-slate-400 hover:text-amber-400 hover:border-amber-500/30 transition-all duration-300"
          >
            <Home className="h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
            <span className="text-[10px] font-black uppercase tracking-widest">Home</span>
          </Link>
          
          <div className="flex items-center gap-3">
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
          />
        </article>

        {/* Vertical alignment guide / footer spacer */}
        <footer className="h-24 flex items-center justify-center opacity-20">
           <div className="w-0.5 bg-gradient-to-b from-amber-500 to-transparent h-full rounded-full" />
        </footer>
      </main>
    </div>
  );
}
