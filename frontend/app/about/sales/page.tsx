// Filename: /frontend/app/about/sales/page.tsx
// Vision & Doctrine — Arc Codex platform overview.
// Librarian aesthetic. Structure follows the four-tier framing (base /
// first-week / sprint / separate products) settled in the 2026-09-16
// parity audit; Huntaegis case study kept near-verbatim.

import React from 'react';
import type { Metadata } from 'next';
import { ARC_FRAMEWORK_VERSION } from '@/lib/version';
import Link from 'next/link';
import { ChevronRight, ExternalLink } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Vision & Doctrine — Arc Codex',
  description: 'AI for the Independent Mind — intelligence infrastructure for individuals, researchers, and specialized platforms.',
};

const STATS = [
  '2,300+ Sources',
  'Multilingual',
  '48 A.R.C. Patterns',
  'Self-Hosted',
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

// Base = what a Hunt-shaped instance is today, on day one, without add-ons.
const BASE = [
  'RSS ingestion at your chosen cadence — your sources, your taxonomy.',
  'Three-pass A.R.C. analysis on every article: Facts, Summary, Full Take.',
  'Sentinel AI-content detection and Counter-Analyst adversarial comment.',
  'Chimera four-metric readability scoring.',
  'One-click translation into many languages.',
  'Comment moderation with hostility gating.',
  'Bluesky, Mastodon, and Facebook auto-posting.',
  'Weekly opt-in email digest, ranked by readability.',
  'Your own domain, palette, branding, and social accounts.',
];

// First week = what a single engineer can genuinely add in five days,
// after absorbing the shared-codebase porting drift.
const FIRST_WEEK = [
  { name: 'Wiki directory', body: 'Read-only intelligence directory grouped by your directives. Layers over existing article storage — no separate database.' },
  { name: 'Sources page', body: 'Public listing of the feeds you monitor, generated from your sources file.' },
  { name: 'YouTube ingestion', body: 'Metadata-only ingest of YouTube URLs alongside RSS.' },
  { name: 'Prompt-to-article', body: 'Generate a publish-ready article from a user prompt.' },
  { name: 'Grade endpoints', body: 'Structured grading pass on top of the three-pass analysis.' },
  { name: 'Playwright fallback', body: 'A stealth-browser tier for feeds behind aggressive bot protection.' },
];

// Sprint = real work, but achievable extensions.
const SPRINT_ADDONS = [
  { name: 'Weekly Quiz', body: 'Auto-generated multiple-choice quizzes from the week\'s articles. Requires site-scoped Redis keys and an optional deeplink into a companion learning platform.' },
  { name: 'Synthetic Reporters', body: 'Persistent character pages with lectures, assignments, and text-to-speech playback. Requires a companion Faculty Directory service.' },
  { name: 'Reading Library', body: 'A corpus-backed reader with translation cache and curated shelves. Requires you to decide the corpus and provide storage.' },
];

// Separate products = sibling stacks, not modules.
const SIBLING_PRODUCTS = [
  { name: 'Newsradio', body: 'Long-form narrated shows built from analyzed articles. A Kokoro-narrated audio stack that runs alongside Arc.' },
  { name: 'LightBox', body: 'Video ingestion and analysis. A separate stack with its own hardware footprint.' },
  { name: 'School of Chat', body: 'The Faculty Directory service that anchors Reporters. A distinct product with its own doctrine and roadmap.' },
];

const DEPLOYMENT_POSTURE = [
  {
    name: 'Self-Hosted',
    body: 'Runs on infrastructure you control. Flask, Next.js, Redis, and Solr fit on one workstation-class server; Ollama runs on whatever LAN host you assign to it.',
  },
  {
    name: 'Inference On Your Hardware',
    body: 'Every analysis path except the optional cloud escalation runs locally by default: council, translation, and broadcast script are local-only, and the analyzer runs local-first with a gated escalation. A local-only mode disables cloud entirely for buyers who require it.',
  },
  {
    name: 'Delivered in a Week',
    body: 'One pre-sales engineer with AI assistance stands up a code-shared instance in five business days — your sources, your taxonomy, your branding, your social accounts, your database. Any tier-one and tier-two features you\'ve chosen are wired in the same window.',
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
            Arc Codex monitors over 2,300 RSS sources in many languages in real time. Every article is automatically fetched, scored for reading difficulty, and run through three independent AI analytical passes:
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
            Every article also gets a Sentinel forensic pass for AI-generated content detection, a Counter-Analyst adversarial comment, and a Chimera Difficulty Score synthesizing four readability metrics. Translation into many languages is one click away.
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

        {/* What You Get — the four tiers */}
        <section className="py-10 border-b border-slate-800/60 space-y-8">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            What You Get
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex is sold as a base product with named extensions. Everything below is either running in a live instance today or has a defined path from one to the other. Nothing on this page describes architecture we do not have.
          </p>

          {/* Tier 1 — Base */}
          <div className="space-y-4">
            <h3 className="font-sans text-[11px] uppercase tracking-[0.3em] font-semibold text-emerald-300/90">
              Base · What Ships On Day One
            </h3>
            <p className="font-serif text-sm text-slate-300 italic leading-relaxed">
              The full working instance. What Huntaegis has been running continuously since its launch.
            </p>
            <ul className="border-t border-slate-800/40">
              {BASE.map((line) => (
                <li key={line} className="py-3 border-b border-slate-800/40 font-serif text-base text-slate-200 leading-relaxed">
                  {line}
                </li>
              ))}
            </ul>
          </div>

          {/* Tier 2 — First week */}
          <div className="space-y-4">
            <h3 className="font-sans text-[11px] uppercase tracking-[0.3em] font-semibold text-amber-300/90">
              First Week · Add-Ons In The Deployment Window
            </h3>
            <p className="font-serif text-sm text-slate-300 italic leading-relaxed">
              Wired in during the same five-day setup window as the base. Assumes the engineer is also carrying across recent improvements from the shared codebase — a real cost, budgeted into the week.
            </p>
            <ul className="border-t border-slate-800/40">
              {FIRST_WEEK.map((m) => (
                <li key={m.name} className="py-4 border-b border-slate-800/40 space-y-1">
                  <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{m.name}</div>
                  <p className="font-serif text-base text-slate-200 leading-relaxed">{m.body}</p>
                </li>
              ))}
            </ul>
          </div>

          {/* Tier 3 — Sprint */}
          <div className="space-y-4">
            <h3 className="font-sans text-[11px] uppercase tracking-[0.3em] font-semibold text-sky-300/90">
              Sprint Add-Ons · Discrete Engagements
            </h3>
            <p className="font-serif text-sm text-slate-300 italic leading-relaxed">
              Substantial features with their own dependencies. Each is a defined engagement, not part of the initial week.
            </p>
            <ul className="border-t border-slate-800/40">
              {SPRINT_ADDONS.map((m) => (
                <li key={m.name} className="py-4 border-b border-slate-800/40 space-y-1">
                  <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{m.name}</div>
                  <p className="font-serif text-base text-slate-200 leading-relaxed">{m.body}</p>
                </li>
              ))}
            </ul>
          </div>

          {/* Tier 4 — Sibling products */}
          <div className="space-y-4">
            <h3 className="font-sans text-[11px] uppercase tracking-[0.3em] font-semibold text-slate-400">
              Sibling Products · Named Separately
            </h3>
            <p className="font-serif text-sm text-slate-300 italic leading-relaxed">
              Distinct products that run alongside Arc, not modules of it. Named here so buyers know they exist; scoped and quoted separately.
            </p>
            <ul className="border-t border-slate-800/40">
              {SIBLING_PRODUCTS.map((m) => (
                <li key={m.name} className="py-4 border-b border-slate-800/40 space-y-1">
                  <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{m.name}</div>
                  <p className="font-serif text-base text-slate-200 leading-relaxed">{m.body}</p>
                </li>
              ))}
            </ul>
          </div>
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
            is a purpose-built cybersecurity intelligence platform running the Arc Codex codebase — fully rebranded, with its own database, taxonomy, and social accounts.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Where Arc Codex monitors general world news, Huntaegis is focused exclusively on threat intelligence: active ransomware campaigns, critical CVEs, state-sponsored cyber operations, DFIR developments, and law enforcement cybercrime actions. It ingests from 284 security-specialist sources including Krebs on Security, Google Project Zero, CISA, Mandiant, Unit 42, and Cisco Talos.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The same A.R.C. cognitive analysis engine runs on every threat report — giving security professionals not just the news, but the angle, the context, and the counter-argument. A dedicated terminal aesthetic makes it feel at home in a SOC environment.
          </p>
          <p className="font-serif text-sm text-slate-400 italic leading-relaxed">
            Huntaegis is the proof point for everything above: a live second instance, code-shared with Arc Codex, run continuously with its own sources, directives, branding, and social accounts.
          </p>
          <a
            href="https://huntaegis.com"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Visit Huntaegis (opens in new tab)"
            className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors ring-focus rounded-sm"
          >
            Visit Huntaegis
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        </section>

        {/* How It's Delivered */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            How It&apos;s Delivered
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            One pre-sales engineer, working with AI assistance, delivers the setup. No sprint teams, no consulting layers, no seven-figure statement of work.
          </p>
          <ul className="border-t border-slate-800/40">
            {DEPLOYMENT_POSTURE.map((d) => (
              <li key={d.name} className="py-4 border-b border-slate-800/40 space-y-1">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{d.name}</div>
                <p className="font-serif text-base text-slate-200 leading-relaxed">{d.body}</p>
              </li>
            ))}
          </ul>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Interested in a deployment? Reach out — the engagement starts with a scoping call to fix the source list, taxonomy, and first-week add-ons.
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
              className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-slate-50 font-sans text-xs uppercase tracking-[0.25em] font-semibold rounded-sm transition-colors ring-focus"
            >
              How to Use Arc Codex
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </Link>
            <a
              href="mailto:ross@arc-codex.com"
              aria-label="Email ross@arc-codex.com"
              className="inline-flex items-center gap-2 px-6 py-3 border border-slate-700 hover:border-slate-500 text-slate-300 hover:text-slate-100 font-sans text-xs uppercase tracking-[0.25em] rounded-sm transition-colors ring-focus"
            >
              ross@arc-codex.com
            </a>
          </div>
        </section>

        {/* Footer — identifier block */}
        <footer className="text-center pt-12 pb-6 space-y-1 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-600">
          <p>Harold Edwin Ross Nesbitt III</p>
          <p>Fort Collins, CO · 40.5853° N, 105.0844° W</p>
          <p>A.R.C. Framework {ARC_FRAMEWORK_VERSION} · Connection Secure</p>
        </footer>
      </main>
    </div>
  );
}
