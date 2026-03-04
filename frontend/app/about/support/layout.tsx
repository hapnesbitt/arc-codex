import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'The A.R.C. Codex | Deep Tech Specs',
  description: 'Deep dive into the A.R.C. Framework: Sentinel forensic analysis, 48 eristic patterns, and the system architecture of Arc Codex.',
  keywords: [
    'System Architecture',
    'Sentinel Forensics',
    'AI Detection Algorithms',
    'Cognitive Anti-patterns',
    'Redis Streams',
    'Ollama',
    'Solr Search',
    'ETL Pipeline'
  ],
  openGraph: {
    title: 'The A.R.C. Codex: Engineering Resilience',
    description: 'Technical specifications and philosophical foundations of the Argumentative Resilience Codex.',
    type: 'article',
    images: [{ url: '/og-tech-redpill.png' }],
  },
};

export default function TechLayout({ children }: { children: ReactNode }) {
  return <div className="tech-theme-wrapper">{children}</div>;
}
