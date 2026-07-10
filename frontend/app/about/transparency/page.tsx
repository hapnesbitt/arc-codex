// Filename: /frontend/app/about/transparency/page.tsx
// The Open Ledger — Editorial neutrality, the "scores annotate, never gate"
// principle, and the two sanctioned exceptions. Renders the staged copy at
// ~/about_copy_final.md verbatim. Librarian aesthetic; matches sibling pages.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight, ExternalLink } from 'lucide-react';

export const metadata: Metadata = {
  title: 'The Open Ledger — Arc Codex',
  description:
    'How Arc Codex scores without judging — and why every rule that shapes what you see is a line of code you can read and change.',
};

const STATS = [
  'Scores annotate, never gate',
  'Chronological feed',
  '48 A.R.C. patterns',
  'Open source',
];

const EXCEPTIONS = [
  {
    label: 'I · Comments — Moderated for Hostility',
    lead: 'Comments are moderated for hostility.',
    body:
      'A comment scoring past a high threshold for slurs, threats, or overt aggression is rejected. The line is set to catch abuse, not disagreement — sharp criticism, theological argument, and unhappy dissent are meant to pass, and borderline cases are kept. It’s the one place a tone measurement acts as a gate, and it acts only on comments, never on articles.',
  },
  {
    label: 'II · The Optional Email Digest — Ranked',
    lead: 'The optional email digest is ranked.',
    body:
      'If you subscribe to the daily email, the handful of pieces it sends are chosen by readability score, not recency — a deliberate lean toward denser, more substantial writing. The main feed isn’t touched by this; it stays chronological. The ranking only shapes the opt-in email.',
  },
];

const REPO_URL = 'https://github.com/hapnesbitt/arc-codex';

export default function TransparencyPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            The Open Ledger
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Candor
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            The Standing Audit. Every score that shapes the feed — and every line of code that could — recorded in the open, available for inspection.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            {STATS.map((stat, i) => (
              <React.Fragment key={stat}>
                <span>{stat}</span>
                {i < STATS.length - 1 && <span aria-hidden="true">·</span>}
              </React.Fragment>
            ))}
          </div>
        </header>

        {/* I · What this is */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            I · Premise
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            What this is
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex is a collection, not a curator.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            It watches the infosphere and writes down what it sees. It measures everything it can measure — readability, tone, named entities, signs of AI authorship, and a set of rhetorical manipulation patterns — and it attaches those measurements to what you&apos;re reading. Then it gets out of the way.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The feed is chronological. Newest first, the same for everyone, the same collection in the same order — modulo private posts that owners see in their own feed. There is no algorithm deciding what you should see, no personalization, no engagement ranking, no &ldquo;for you.&rdquo; Two people loading Arc Codex see the same public collection in the same order. The only things that change what <em>you</em> see are filters <em>you</em> choose.
          </p>
        </section>

        {/* II · Measure, don't judge */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            II · Principle
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Measure, don&apos;t judge
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex scores things. Every article carries a readability grade, a sentiment reading, an AI-authorship assessment, and flags for any of 48 manipulation patterns it detects.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Here is the rule those scores live under:
          </p>
          <blockquote className="border-l border-slate-700 pl-4 font-serif text-base italic text-slate-100 leading-relaxed">
            They annotate. They do not gate.
          </blockquote>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            A score tells you something about what you&apos;re reading. It never decides <em>whether</em> you get to read it, or <em>where it ranks</em>. A manipulation flag doesn&apos;t bury an article — it labels it, in the open, and lets you judge. We don&apos;t hide the propaganda; we point at the technique and let you see it working. An article flagged as possibly AI-written still publishes, with the flag visible. A grim, hostile, or unflattering piece sits in the feed next to a cheerful one, in the order it arrived, because a collection doesn&apos;t rank its shelves by mood.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            There&apos;s a built-in dissent, too. Every published article carries a Counter-Analyst note — a standing devil&apos;s advocate that argues with Arc Codex&apos;s own read, on everything. The system disagrees with itself in front of you, on purpose.
          </p>
        </section>

        {/* III · The exceptions, named out loud */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            III · Exceptions
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            The exceptions, named out loud
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Two places don&apos;t follow &ldquo;measure, don&apos;t judge.&rdquo; We&apos;d rather tell you than have you find them.
          </p>
          <ul className="border-t border-slate-800/40">
            {EXCEPTIONS.map((ex) => (
              <li key={ex.label} className="py-4 border-b border-slate-800/40 space-y-2">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">
                  {ex.label}
                </div>
                <p className="font-serif text-base text-slate-200 leading-relaxed">
                  <strong className="font-semibold text-slate-100">{ex.lead}</strong> {ex.body}
                </p>
              </li>
            ))}
          </ul>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            That&apos;s the complete list. If we ever add another, it goes here.
          </p>
        </section>

        {/* IV · Don't trust us — read the code */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            IV · Verification
          </div>
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Don&apos;t trust us — read the code
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The strongest thing we can say about any of this isn&apos;t a promise. It&apos;s that the whole system is open source.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Every threshold on this page is a line of code you can read. Disagree with where the comment moderation sits? It&apos;s a number in a file; change it. Think the email shouldn&apos;t rank at all? Delete the sort. Want a fork that gates on something we&apos;d never gate on, for your own private deployment? It&apos;s yours to build.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            A system that quietly distorts what you see has to be opaque to do it. This one isn&apos;t. You don&apos;t have to believe we&apos;re neutral — you can verify it, and you can override it.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            That&apos;s the whole idea. A collection you can audit, running in the open, that shows you what it sees and trusts you to make up your own mind.
          </p>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Read the source on GitHub (opens in new tab)"
            className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors ring-focus rounded-sm"
          >
            Read the source
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
