// Filename: /frontend/app/about/layout.tsx
// A.R.C. Codex v4.0 metadata — converted from .js to .tsx

import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'The A.R.C. Codex v4.0 | Arc Codex',
  description: 'Argumentative Resilience Codex: AI content detection, multi-perspective analysis, cognitive pattern recognition, and tools for independent thinking.',
  keywords: [
    'A.R.C. Codex',
    'Argumentative Resilience',
    'AI content detection',
    'sentinel',
    'cognitive patterns',
    'Watchline Operator',
    'Arc Codex',
    'media literacy',
    'civil discourse',
    'Schopenhauer stratagems',
    'steelmanning',
    'bridge-building',
    'Blue Team',
    'Red Team',
    'Purple Team',
    'counter-analyst',
    'news search',
  ],
  robots: 'index, follow',
  openGraph: {
    title: 'The A.R.C. Codex v4.0 | Arc Codex',
    description: 'AI forensics, multi-perspective analysis, and 48 patterns for cognitive resilience.',
    type: 'website',
  },
};

export default function AboutLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
