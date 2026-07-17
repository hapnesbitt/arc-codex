'use client';

import { useSearchParams } from 'next/navigation';
import IntelligenceCard from '@/components/IntelligenceCard';
import type { Article, Comment } from '@/lib/types';

interface Props {
  article: Article;
  comments: Comment[];
}

// Thin client wrapper: reads `?lang=` from the URL so the server render can be
// ISR-cached (server side never touches searchParams). The extracted lang is
// passed straight to IntelligenceCard's existing initialLang path.
export default function ArticleView({ article, comments }: Props) {
  const searchParams = useSearchParams();
  const initialLang = searchParams?.get('lang') || null;

  return (
    <IntelligenceCard
      card={article}
      comments={comments}
      isCompact={false}
      initialLang={initialLang}
      defaultExpandedSection="purpleTeam"
      fullyExpanded
      priority
    />
  );
}
