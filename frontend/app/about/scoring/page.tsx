// Filename: /frontend/app/about/scoring/page.tsx
// Reading Score — reader-facing explainer for the reading-difficulty dial and
// the companion objectivity score. Plain language, no jargon. Librarian
// aesthetic; matches sibling pages (see transparency/page.tsx).

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight, ExternalLink } from 'lucide-react';

export const metadata: Metadata = {
  title: 'The Reading Score — Arc Codex',
  description:
    'What the reading score measures, how Arc Codex derives it, and what it does and does not tell you about an article.',
};

const OBJECTIVITY_DASHBOARD_URL =
  'https://grafana.arc-codex.com/d/corpus-intelligence-v2/corpus-intelligence?var-site=arc';

const LABELS = [
  'High School',
  'College',
  'Academic',
  'Graduate',
  'Expert',
];

export default function ScoringPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            The Reading Score
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            How hard is this to read?
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            A number for the prose, not a verdict on the piece. Here is exactly what it measures and what it doesn&apos;t.
          </p>
        </header>

        {/* I · What it is */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            I · The number
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            What the reading score is
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The reading score is a readability index from 0 to 100, shown with a plain-language label — {LABELS.join(', ')}. Higher means harder to read: longer sentences, denser vocabulary, more clauses to hold in your head at once. A low score reads like a newspaper brief; a high score reads like a journal article.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The label and the number say the same thing two ways. They&apos;re a heads-up about the effort a piece will ask of you — nothing more.
          </p>
        </section>

        {/* II · How it's derived */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            II · Derivation
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            How it&apos;s derived
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex averages four standard readability metrics — Flesch-Kincaid, Coleman-Liau, SMOG, and Dale-Chall — and projects that average onto the 0–100 scale. Four measures instead of one smooths out the quirks any single formula has with a given kind of writing.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            One honest caveat about our sibling site, <span className="text-slate-100">Huntaegis</span>: it projects a single Flesch-Kincaid grade onto the same 0–100 scale rather than averaging four. The labels mean the same thing on both sites — the inputs behind them differ. We&apos;d rather tell you than let you assume the two numbers are computed identically.
          </p>
        </section>

        {/* III · What it's for */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            III · What it means
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            What it&apos;s for — and what it isn&apos;t
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The reading score describes the writing, not the reporting. It says nothing about whether an article is accurate, fair, important, or true. A dense, high-scoring piece is not better journalism than a plain one — it&apos;s just harder to read. A simple, low-scoring piece can be the more careful and more honest of the two.
          </p>
          <blockquote className="border-l border-slate-700 pl-4 font-serif text-base italic text-slate-100 leading-relaxed">
            A high score means dense prose. It never means better journalism.
          </blockquote>
        </section>

        {/* IV · Objectivity */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            IV · A separate measure
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            The objectivity score
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Alongside the reading score sits a separate 0–100 objectivity score. It measures how far the language leans toward opinion versus neutral description — a piece thick with loaded, persuasive wording scores low; one that mostly reports plainly scores high. Like the reading score, it annotates the prose and decides nothing about what you get to read. For corpus-wide patterns across everything Arc Codex has measured, see the live dashboard.
          </p>
          <a
            href={OBJECTIVITY_DASHBOARD_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Open the corpus intelligence dashboard (opens in new tab)"
            className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors ring-focus rounded-sm"
          >
            View the live dashboard
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        </section>

        {/* Back to landing */}
        <section className="py-10 border-b border-slate-800/60 text-center">
          <Link
            href="/about"
            className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors ring-focus rounded-sm"
          >
            Return to About
            <ChevronRight className="h-3 w-3" aria-hidden="true" />
          </Link>
        </section>

        {/* Footer — identifier block */}
        <footer className="text-center pt-12 pb-6 space-y-1 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-600">
          <p>Harold Edwin Ross Nesbitt III</p>
          <p>Fort Collins, CO · 40.5853° N, 105.0844° W</p>
          <p>A.R.C. Framework v7.14 · Connection Secure</p>
        </footer>
      </main>
    </div>
  );
}
