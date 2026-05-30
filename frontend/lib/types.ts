// Filename: /frontend/lib/types.ts
// Shared type definitions — single source of truth for Arc Codex frontend.
// Used by: FeedClient, IntelligenceCard, CommentSection, article/[slug]/page.tsx

export interface Dossier {
  chimera_score?: number;
  reading_label?: string;
  sentiment?: number;
  subjectivity?: number;
  objectivity_score?: number;
  readability_grade?: number;
  reading_level?: string;
  talking_points?: string[];
  deep_analysis_summary?: string;
  entities_found?: string[];
}

export interface Article {
  id: string;
  title: string;
  source?: string;
  source_name?: string;  // Preferred field from API
  sourceUrl?: string;
  imageUrl?: string;
  original_text: string;
  timestamp: string;
  directive: string;
  category?: string;
  origin?: string;       // 'video' for LightBox submissions; absent on standard articles
  description?: string;  // video article description
  blue_team_analysis?: string;
  red_team_analysis?: string;
  purple_team_analysis?: string;
  sentinel_analysis?: string;
  dossier?: Dossier | string;
  reading_label?: string;
}

export interface Comment {
  id: string;
  article_id: string;
  text: string;
  timestamp: string;
  author?: string;
  parent_id?: string;
  reactions?: Record<string, number>;
}
