// Filename: /frontend/app/about/layout.tsx
// A.R.C. Codex about-section metadata.
//
// The title no longer carries a version. The framework version lives in every
// page footer (via ARC_FRAMEWORK_VERSION); duplicating it here — even
// dynamically — is one stale import away from the same drift the hardcoded
// "v4.0" was.

import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'The A.R.C. Codex | Arc Codex',
  description: 'Argumentative Resilience Codex: AI content detection, multi-perspective analysis, cognitive pattern recognition, and tools for independent thinking.',
  keywords: [
    'A.R.C. Codex',
    'Argumentative Resilience',
    'AI content detection',
    'sentinel',
    'cognitive patterns',
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
    title: 'The A.R.C. Codex | Arc Codex',
    description: 'AI forensics, multi-perspective analysis, and 48 patterns for cognitive resilience.',
    type: 'website',
  },
};

export default function AboutLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
