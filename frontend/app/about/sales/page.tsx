// Filename: /frontend/app/about/sales/page.tsx
// Vision & Doctrine — Arc Codex platform overview.
// Librarian aesthetic. Reconstructed from page.tsx.Apr20 substantive content
// (mission, how-it-works, Huntaegis, deployment, integrity) plus the Chimera
// scorecard from the prior poetic redesign.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight, ExternalLink } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Vision & Doctrine — Arc Codex',
  description: 'AI for the Independent Mind — intelligence infrastructure for individuals, researchers, and specialized platforms.',
};

const STATS = [
  '2,088 Sources',
  '162 Languages',
  '48 A.R.C. Patterns',
  'Docker-Ready',
];

const PASSES = [
  {
    label: 'I · Facts Only',
    body: 'Verifiable facts only. Who, what, when, where. No interpretation.',
  },
  {
    label: 'II · Executive Summary',
    body: 'Balanced, journalist-style summary written for educated readers.',
  },
  {
    label: 'III · Full Take',
    body: 'Deep cognitive analysis — steelman, 48 A.R.C. anti-patterns, root cause, implications.',
  },
];

const CHIMERA_METRICS = [
  { name: 'Flesch–Kincaid', body: 'Architectural complexity.' },
  { name: 'Coleman–Liau', body: 'Character density.' },
  { name: 'SMOG', body: 'Polysyllabic gravity.' },
  { name: 'Dale–Chall', body: 'Lexical rarity.' },
];

const DEPLOYMENT = [
  {
    name: 'Self-Hosted',
    body: 'Run on your own hardware — a single workstation or server is sufficient. All inference stays local; zero cloud dependency.',
  },
  {
    name: 'Customized for Your Domain',
    body: 'Swap sources, directives, branding, and palette. Huntaegis went from Arc Codex to a fully branded security platform in a single session.',
  },
];

export default function SalesPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Vision &amp; Doctrine
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            AI for the Independent Mind
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            Intelligence infrastructure for individuals, researchers, and specialized platforms.
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

        {/* Mission */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Mission · Empowering the 100%
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            In a world where AI is often kept behind the gates of massive corporations, Arc Codex is built as a public utility for intelligence. Our mission is to take the most sophisticated analytical tools on the planet and place them directly into the hands of the individuals who need them most: creators, researchers, small business owners, and local leaders.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            We don&apos;t just provide software; we provide clarity. The A.R.C. (Argumentative Resilience Codex) framework transforms raw, overwhelming data into structured, multi-perspective insight — so you can compete at the highest level without the corporate overhead.
          </p>
        </section>

        {/* How It Works */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            How It Works
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex monitors over 2,088 RSS sources across 162 languages in real time. Every article is automatically fetched, scored for reading difficulty, and run through three independent AI analytical passes:
          </p>
          <ul className="border-t border-slate-800/40">
            {PASSES.map((p) => (
              <li key={p.label} className="py-4 border-b border-slate-800/40 space-y-1">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{p.label}</div>
                <p className="font-serif text-base text-slate-200 leading-relaxed">{p.body}</p>
              </li>
            ))}
          </ul>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Every article also gets a Sentinel forensic pass for AI-generated content detection, a Counter-Analyst adversarial comment, and a Chimera Difficulty Score synthesizing four readability metrics. Translation into any of 162 languages is one click away.
          </p>
        </section>

        {/* Chimera Difficulty Score */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Chimera Difficulty Score
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            A rigorous synthesis of four readability metrics, designed to measure the cognitive load of truth.
          </p>
          <ul className="border-t border-slate-800/40">
            {CHIMERA_METRICS.map((m) => (
              <li key={m.name} className="py-4 border-b border-slate-800/40 flex items-baseline gap-4 flex-wrap">
                <span className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400 min-w-[140px]">{m.name}</span>
                <span className="font-serif text-base text-slate-200 leading-relaxed">{m.body}</span>
              </li>
            ))}
          </ul>
          <p className="font-serif text-sm text-slate-400 italic leading-relaxed pt-2">
            We do not build for the soundbite. We build for the resilient narrative.
          </p>
        </section>

        {/* Success Story — Huntaegis */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Success Story · Huntaegis
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <a
              href="https://huntaegis.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-100 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2"
            >
              Huntaegis.com
            </a>{' '}
            is a purpose-built cybersecurity intelligence platform deployed on the Arc Codex engine — fully customized for a professional penetration tester.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Where Arc Codex monitors general world news, Huntaegis is focused exclusively on threat intelligence: active ransomware campaigns, critical CVEs, state-sponsored cyber operations, DFIR developments, and law enforcement cybercrime actions. It ingests from 51 security-specialist sources including Krebs on Security, Google Project Zero, CISA, Mandiant, Unit 42, and Cisco Talos.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The same A.R.C. cognitive analysis engine runs on every threat report — giving security professionals not just the news, but the angle, the context, and the counter-argument. A dedicated terminal aesthetic makes it feel at home in a SOC environment.
          </p>
          <a
            href="https://huntaegis.com"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Visit Huntaegis (opens in new tab)"
            className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
          >
            Visit Huntaegis
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        </section>

        {/* Deploy Your Own */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Deploy Your Own
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex is available as a Docker-based deployment. The full stack — Flask API, Next.js frontend, Redis, Apache Solr, and all background workers — ships as a single{' '}
            <code className="font-mono text-sm text-slate-300 bg-slate-900 border border-slate-800 rounded-sm px-1.5 py-0.5">docker-compose.yml</code>. AI inference runs locally via Ollama, keeping your data on your hardware.
          </p>
          <ul className="border-t border-slate-800/40">
            {DEPLOYMENT.map((d) => (
              <li key={d.name} className="py-4 border-b border-slate-800/40 space-y-1">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{d.name}</div>
                <p className="font-serif text-base text-slate-200 leading-relaxed">{d.body}</p>
              </li>
            ))}
          </ul>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Interested in a custom deployment? Reach out — Arc Codex has been deployed for general news intelligence, cybersecurity operations, and domain-specific research platforms.
          </p>
        </section>

        {/* Information Integrity */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Information Integrity by Design
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The digital landscape is flooded with synthetic content and manufactured consensus. Arc Codex works tirelessly to verify, validate, and challenge every piece of information you see.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The A.R.C. framework applies Chimera difficulty scoring, Sentinel forensic detection, and Socratic counter-dialogue to every article — stripping away the noise and leaving you with the signal that actually matters. No ads, no tracking, no paywalls.
          </p>
          <blockquote className="border-l border-slate-700 pl-4 font-serif text-base italic text-slate-300 leading-relaxed">
            Our technology doesn&apos;t just process information — it defends the human element in information.
          </blockquote>
        </section>

        {/* CTA */}
        <section className="py-10 border-b border-slate-800/60 space-y-6 text-center">
          <h2 className="font-serif text-3xl font-semibold tracking-tight text-slate-50">
            Stop reacting. Start analyzing.
          </h2>
          <p className="font-serif text-base text-slate-300 italic leading-relaxed max-w-xl mx-auto">
            Read the feed, deploy your own instance, or reach out to discuss a custom platform.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <Link
              href="/about/support"
              className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-slate-50 font-sans text-xs uppercase tracking-[0.25em] font-semibold rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-300"
            >
              How to Use Arc Codex
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </Link>
            <a
              href="mailto:ross@arc-codex.com"
              aria-label="Email ross@arc-codex.com"
              className="inline-flex items-center gap-2 px-6 py-3 border border-slate-700 hover:border-slate-500 text-slate-300 hover:text-slate-100 font-sans text-xs uppercase tracking-[0.25em] rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40"
            >
              ross@arc-codex.com
            </a>
          </div>
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
