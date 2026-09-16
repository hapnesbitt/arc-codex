// cardConfig.ts — per-site configuration for the unified IntelligenceCard.
//
// This module is the ONE thing that differs between Arc and Hunt for the card:
// the component file itself is byte-identical across stacks and reads every
// site-specific value (capability flags, URLs, copy) from here. Do NOT thread
// these as props from callers or fork the component — that is exactly how the
// two copies drifted before.
//
// Identity primitives (siteName, baseUrlFallback) now read from lib/site.ts,
// which reads them in turn from NEXT_PUBLIC_SITE_* build-time env vars. Every
// other value here (feature flags, external service URLs like the quiz
// deeplink and objectivity dashboard, per-stack topic-link mode) stays
// explicit — those ARE the per-site product decisions this file exists to
// carry.
//
// Flag hygiene: every flag that is `false` carries a comment saying whether it
// is off BY CHOICE (a product decision) or off because UNBUILT (a debt). Six
// months out that distinction is invisible without the comment.

import { site } from '@/lib/site';

export interface CardConfig {
  siteName: string;                 // used in tooltips / share copy
  baseUrlFallback: string;          // used only when NEXT_PUBLIC_BACKEND_URL is unset
  videoDomainFallback: string;

  // Scores
  readingScore: boolean;            // reading-difficulty dial (readability_index + reading_label)
  scoringExplainerUrl: string;      // reading dial links here; '' → dial renders as plain text
  objectivityScore: boolean;        // objectivity dial (objectivity_score)
  objectivityDashboardUrl: string;  // '' → dial renders without a dashboard link

  // Actions / affordances
  research: boolean;
  share: boolean;
  translation: boolean;
  permalink: boolean;
  copyLink: boolean;
  print: boolean;
  video: boolean;
  sentinel: boolean;
  counterAnalyst: boolean;
  comments: boolean;
  privateArticles: boolean;

  topicLink: 'wiki' | 'directiveFilter' | 'off';  // "Full take" target
  quiz: boolean;
  quizUrlTemplate: string;          // {id} placeholder; '' when quiz is off
  badges: boolean;
}

export const cardConfig: CardConfig = {
  siteName: site.name,
  baseUrlFallback: site.baseUrl,
  videoDomainFallback: 'vid.arc-codex.com',

  readingScore: true,
  // Reader-facing explainer for the reading score (see /about/scoring).
  scoringExplainerUrl: '/about/scoring',
  objectivityScore: true,
  // Site-scoped view of the shared corpus-intelligence-v2 dashboard.
  objectivityDashboardUrl: 'https://grafana.arc-codex.com/d/corpus-intelligence-v2/corpus-intelligence?var-site=arc',

  research: true,
  share: true,
  translation: true,
  permalink: true,
  copyLink: true,
  print: true,
  video: true,
  sentinel: true,
  counterAnalyst: true,
  comments: true,
  privateArticles: true,

  topicLink: 'wiki',                // Arc has /wiki/{slug} directive pages
  quiz: true,
  quizUrlTemplate: 'https://soc.arc-codex.com/course/quiz-me/article/{id}',
  badges: false,                    // OFF BY CHOICE — the reading badge lives in
                                    // School of Chat, reached via the quiz link;
                                    // Arc has no first-party badge surface.
};
