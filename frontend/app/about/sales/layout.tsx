import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'AI for the Independent Mind | Our Mission',
  description: 'Discover how Arc Codex is unlocking the power of AI for creators, small teams, and independent thinkers everywhere.',
  keywords: [
    'Accessible AI',
    'AI for Creators',
    'Independent Thinking',
    'Small Business AI Tools',
    'Media Democracy',
    'Cognitive Freedom',
    'Human-Centric AI',
    'Innovation for Everyone'
  ],
  openGraph: {
    title: 'Unlocking AI for Everyone | Arc Codex',
    description: 'Bridging the gap between elite technology and human-scale innovation. Join the expedition.',
    type: 'website',
    images: [{ url: '/og-mission-bluepill.png' }],
  },
};

export default function SimpleLayout({ children }: { children: ReactNode }) {
  return <div className="mission-theme-wrapper">{children}</div>;
}
