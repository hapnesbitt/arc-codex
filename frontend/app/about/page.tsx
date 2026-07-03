// Filename: /frontend/app/about/page.tsx
// About — Front matter for Arc Codex.
// Librarian aesthetic: serif body, sans-serif metadata, hairline-separated
// sections, no card chrome. Server component — SEO-friendly.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'About — Arc Codex',
  description: 'An instrument for stewarding the process of knowing — A.R.C. cognitive analysis applied to news and discourse.',
  alternates: {
    canonical: 'https://arc-codex.com/about',
    types: {
      'application/opensearchdescription+xml': '/opensearch.xml',
      'application/rss+xml': '/rss.xml',
    },
  },
};

type Pillar = {
  href: string;
  title: string;
  description: string;
  kicker?: string;
};

const PILLARS: Pillar[] = [
  {
    href: '/about/sales',
    title: 'Vision & Doctrine',
    description: 'The Vigil of the Refined Mind. An exploration of the duty to steward the process of knowing.',
  },
  {
    href: '/about/support',
    title: 'The Art of Discernment',
    description: 'User guidelines for navigating the analytical triad and the 48 A.R.C. patterns of interference.',
  },
  {
    href: '/about/developer',
    title: 'Infrastructure of Meaning',
    description: 'The Z230 Blueprint. Technical specifications for the Scribe and the architecture of intent.',
  },
  {
    href: '/about/contact',
    title: 'Stewardship',
    description: 'Professional consulting on cognitive resilience and high-fidelity systems architecture.',
  },
  {
    href: '/about/transparency',
    title: 'The Open Ledger',
    kicker: 'Candor',
    description: 'The Standing Audit. Every score that shapes the feed — and every line of code that could — recorded in the open, available for inspection.',
  },
];

const UTILITY_NAV = [
  { href: '/about/sales', label: 'Vision' },
  { href: '/about/support', label: 'Support' },
  { href: '/about/developer', label: 'Developer' },
  { href: '/about/contact', label: 'Contact' },
  { href: '/about/privacy', label: 'Privacy' },
  { href: '/about/terms', label: 'Terms' },
  { href: '/about/transparency', label: 'Transparency' },
];

export default function AboutGateway() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header — front matter */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Argumentative Resilience Codex
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Arc Codex
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
            An instrument for stewarding the process of knowing — A.R.C. cognitive analysis applied to news and discourse.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500 pt-2">
            Civility · Integrity · Availability
          </div>
        </header>

        {/* Pillars — written sections, not tiles */}
        {PILLARS.map((pillar) => (
          <section key={pillar.href} className="py-10 border-b border-slate-800/60 space-y-4">
            <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
              Protocol · {pillar.kicker || pillar.title.split(' ')[0]}
            </div>
            <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
              {pillar.title}
            </h2>
            <p className="font-serif text-lg text-slate-200 leading-relaxed max-w-2xl">
              {pillar.description}
            </p>
            <Link
              href={pillar.href}
              className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
            >
              Enter Archive
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </Link>
          </section>
        ))}

        {/* Utility nav — quiet footer-style row across all sub-pages */}
        <nav
          aria-label="About sections"
          className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3 py-8 border-b border-slate-800/60"
        >
          {UTILITY_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Footer — identifier, metrics + sources, framework version */}
        <footer className="text-center pt-12 pb-6 space-y-4 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-2">
            <a
              href="https://grafana.arc-codex.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
            >
              ◈ Corpus Metrics
            </a>
            <Link
              href="/sources"
              className="hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
            >
              ◈ Sources
            </Link>
          </div>

          <div className="space-y-1 pt-4 text-slate-600">
            <p>Harold Edwin Ross Nesbitt III</p>
            <p>Fort Collins, CO · 40.5853° N, 105.0844° W</p>
            <p>A.R.C. Framework v7.14 · Connection Secure</p>
          </div>
        </footer>
      </main>
    </div>
  );
}
