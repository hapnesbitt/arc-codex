// Filename: /frontend/app/about/developer/page.tsx
// Infrastructure of Meaning — Developer Documentation.
// Librarian aesthetic. Public page: describes capabilities and design, NOT
// operational coordinates (ports, hosts, paths, internal schemas, routing
// tables live in ops/RUNBOOK.md — see 2026-07-18 relocation entry). Server component.

import React from 'react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Developer Documentation — Arc Codex',
  description: 'Architecture, design choices, and the philosophy behind Arc Codex.',
};

// ── helpers ───────────────────────────────────────────────────────────────────
const SectionShell: React.FC<{ id?: string; eyebrow: string; heading: string; children: React.ReactNode }> = ({
  id, eyebrow, heading, children,
}) => (
  <section id={id} className="py-10 border-b border-slate-800/60 space-y-6">
    <div className="space-y-2">
      <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">{eyebrow}</div>
      <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">{heading}</h2>
    </div>
    {children}
  </section>
);

const Code: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <code className="font-mono text-sm text-slate-300 bg-slate-900 border border-slate-800 rounded-sm px-1.5 py-0.5">
    {children}
  </code>
);

const Warn: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p role="note" className="font-serif text-sm text-slate-300 italic leading-relaxed flex items-start gap-2 not-prose">
    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" aria-hidden="true" />
    <span>{children}</span>
  </p>
);

const Panel: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <details className="group/p border-b border-slate-800/40">
    <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer flex items-center justify-between gap-4 py-3 px-2 -mx-2 rounded-sm hover:bg-slate-800/30 transition-colors ring-focus">
      <span className="font-mono text-sm text-slate-300">{label}</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 group-open/p:hidden">expand</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 hidden group-open/p:inline">collapse</span>
    </summary>
    <div className="pt-2 pb-4 px-2 space-y-3 text-slate-300 font-serif text-base leading-relaxed">
      {children}
    </div>
  </details>
);

// ── page ──────────────────────────────────────────────────────────────────────
export default function DeveloperPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Infrastructure of Meaning
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Developer Documentation
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            The architecture and design choices behind Arc Codex.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            <span>Flask + Next.js</span>
            <span aria-hidden="true">·</span>
            <span>Redis + Solr</span>
            <span aria-hidden="true">·</span>
            <span>Local + cloud inference</span>
            <span aria-hidden="true">·</span>
            <span>Local speech synthesis</span>
          </div>
        </header>

        {/* Stack Overview */}
        <SectionShell id="stack" eyebrow="I" heading="Stack Overview">
          <dl className="grid sm:grid-cols-2 gap-x-6">
            {[
              { label: 'Backend', value: 'Python / Flask / gunicorn' },
              { label: 'Frontend', value: 'Next.js 16.2.12 / React 19 / TypeScript' },
              { label: 'Database', value: 'Redis (in-memory store + work streams)' },
              { label: 'Library DB', value: 'SQLite (public-domain book corpus)' },
              { label: 'Search', value: 'Apache Solr (full-text)' },
              { label: 'AI Inference', value: 'Ollama — local model + cloud escalation' },
              { label: 'Speech', value: 'Kokoro neural TTS — local synthesis, MP3 output' },
              { label: 'Metrics', value: 'Prometheus + Grafana (corpus and pipeline telemetry)' },
              { label: 'Auth', value: 'Auth.js v5 beta — Google + GitHub OAuth, JWT sessions' },
              { label: 'Proxy', value: "Caddy (automatic TLS via Let's Encrypt)" },
              { label: 'Process Mgr', value: 'arc.sh + systemd (auto-starts on boot)' },
            ].map(({ label, value }) => (
              <div key={label} className="py-3 border-b border-slate-800/40">
                <dt className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{label}</dt>
                <dd className="font-mono text-sm text-slate-200 break-words">{value}</dd>
              </div>
            ))}
          </dl>
        </SectionShell>

        {/* Services */}
        <SectionShell id="services" eyebrow="II" heading="Services & Supervision">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The stack is managed by a single control script and <strong>auto-starts on boot</strong>.
            A <strong>watchdog</strong> supervises the services at runtime and restarts any that
            crash, distinguishing a deliberately-stopped service from a failed one.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            What runs: RSS ingestion and the full A.R.C. analysis pipeline (the <em>Scribe</em>);
            on-demand and manual publishing of user submissions; background analysis workers;
            automated posting to Bluesky, Mastodon, and Facebook (each toggleable at runtime with
            no restart); an email digest; and the Next.js frontend.
          </p>
          <Warn>
            <span><strong className="not-italic">Posting is fail-safe, not fire-and-forget:</strong> the posters
            track which articles they have published separately, so a mid-publish failure re-tries on the
            next cycle rather than double-posting or silently dropping.</span>
          </Warn>
        </SectionShell>

        {/* Reverse proxy */}
        <SectionShell id="proxy" eyebrow="III" heading="Reverse Proxy">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            A Caddy reverse proxy terminates TLS and routes requests: authentication and
            user-preference calls are handled by the Next.js application server, and the remaining
            API traffic goes to the Flask backend. Everything else renders from Next.js. Automatic
            certificate management is handled by Caddy.
          </p>
        </SectionShell>

        {/* Public API */}
        <SectionShell id="api" eyebrow="IV" heading="Public API">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex exposes a read-only public HTTP API over the same domain. It serves the
            article feed, individual articles with their full analysis, full-text search, an RSS
            feed, the wiki directive pages, the public-domain library, and the machine-readable
            sitemap. Signed-in users can additionally submit content for processing and manage
            their own preferences.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Machine-readable discovery surfaces — <Code>/rss.xml</Code>, <Code>/sitemap.xml</Code>,
            <Code>/news-sitemap.xml</Code>, and <Code>/opensearch.xml</Code> — are published and kept
            current automatically.
          </p>
        </SectionShell>

        {/* Data model */}
        <SectionShell id="data" eyebrow="V" heading="Data Model">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Live application data is held in Redis for speed; the public-domain book corpus behind the
            Library lives in SQLite; and full-text search is served from Solr. At a conceptual level the
            system stores:
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="Articles">
              Each article carries its source text, metadata, editorial directive, a reading-difficulty
              score, the three A.R.C. analyses, and an AI-content verdict. Articles are typed as either
              rolling <em>news</em> or durable <em>reference</em> content.
            </Panel>
            <Panel label="Comments & reactions">
              Reader comments and per-comment reaction counts. The adversarial Counter-Analyst comment
              is a first-class, distinctly-styled entry.
            </Panel>
            <Panel label="Translations">
              Per-article, per-language translations are cached for a day so a repeat request is instant.
            </Panel>
            <Panel label="Work queues">
              Analysis is handed between processes on a length-capped stream rather than an
              unbounded list. A burst of ingest cannot grow the backlog without limit, and a
              consumer that restarts resumes from where it stopped instead of replaying the
              corpus. The cap is deliberate: dropping the oldest pending work is preferable to
              exhausting memory on a machine that is also serving readers.
            </Panel>
            <Panel label="Accounts">
              A minimal profile per signed-in user — identity from the OAuth provider plus a preferred
              language. Authentication is stateless (JWT); no server-side session store is required.
            </Panel>
          </div>
        </SectionShell>

        {/* Authentication */}
        <SectionShell id="auth" eyebrow="VI" heading="Authentication">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Soft auth — the site is fully public. Signing in with Google or GitHub is optional and
            unlocks preferences, publishing, and private articles. There is no username/password
            fallback and no third-party tracking.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Sessions are JWT-based (stateless), and preference writes are accepted only from the
            application server itself — never directly from the public internet — so a user can only
            ever change their own settings.
          </p>
        </SectionShell>

        {/* AI Pipeline */}
        <SectionShell id="ai" eyebrow="VII" heading="AI Pipeline">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Inference is tiered and demand-gated: a compact local model handles the bulk of the work,
            and a larger cloud model is reached only on escalation, within a weekly budget. The
            Red / Blue / Purple analyses are computed lazily — on an article&rsquo;s first view rather
            than at ingest — so inference cost tracks readership, not ingest volume. Published articles
            are retained for roughly a month before they are pruned. Translation degrades gracefully
            when a model is unavailable: &ldquo;model unavailable&rdquo; is shown rather than a hard failure.
          </p>
          <Warn>
            <span><strong className="not-italic">Translation is a click, not an auto-fire in the feed.</strong>
            A scrolled feed holds many mounted cards; firing translation on each mount would overwhelm the
            inference tier. A preferred language is a shortcut that skips the picker — it does not translate
            the whole feed automatically.</span>
          </Warn>
        </SectionShell>

        {/* Audio & Narration */}
        <SectionShell id="audio" eyebrow="VIII" heading="Audio &amp; Narration">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Every published article is also spoken. A neural text-to-speech model
            (<Code>Kokoro</Code>) renders the article body to audio on the same hardware that
            runs the rest of the pipeline — there is no cloud speech service, no per-character
            billing, and no third party receives the text. Long pieces are split into chunks,
            synthesised in sequence, then concatenated and encoded to a compact mono MP3 sized
            for slow connections rather than for fidelity.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Narration is opportunistic rather than blocking. Publishing never waits on audio:
            a pass runs each cycle, picks the newest article still lacking a recording, and
            defers if the machine is busy. A deferred article is simply retried next time
            round. Recent narrations are also concatenated into a rolling bulletin — a single
            continuous audio stream of the day&rsquo;s reporting, intended for listeners who want
            the news without a screen.
          </p>
          <Warn>
            <span><strong className="not-italic">Synthesis yields to analysis.</strong> Speech
            generation is memory-hungry, so a pre-flight check confirms there is genuine headroom
            before a run starts. If there is not, narration steps aside rather than competing with
            the analysis pipeline for the same machine. Audio is the part of the system that can
            afford to be late.</span>
          </Warn>
        </SectionShell>

        {/* Observability */}
        <SectionShell id="observability" eyebrow="IX" heading="Observability">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The pipeline is instrumented rather than trusted. Metrics are scraped continuously
            and rendered as dashboards covering ingest rate, analysis latency, inference tiering,
            and corpus-level qualities — the average reading difficulty and objectivity of what
            has actually been published, not merely how much of it there is.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Alerting distinguishes <em>liveness</em> from <em>output</em>. A worker publishes a
            heartbeat on a short expiry, so its silence is itself the signal; that is a separate
            question from whether the day produced many articles or few. Conflating the two
            produces an alarm that fires on every quiet afternoon and is therefore ignored when
            it matters.
          </p>
          <Warn>
            <span><strong className="not-italic">An alert that cannot clear is not an alert.</strong>
            Conditions are edge-triggered and paired with an explicit all-clear, so a fault that
            resolves itself says so. Without that, a recovered incident and an ongoing one look
            identical from the outside.</span>
          </Warn>
        </SectionShell>

        {/* Frontend Gotchas */}
        <SectionShell id="gotchas" eyebrow="X" heading="Frontend Notes">
          <ul className="border-t border-slate-800/40">
            {[
              { title: 'Feed rendering',   warn: true,  text: 'The lazy-loading feed structure is load-bearing — changes are surgical, never structural.' },
              { title: 'Theme layer',       warn: true,  text: 'A single stylesheet layer is the source of truth for colours and overrides everything else.' },
              { title: 'Preferences',       warn: false, text: 'One context is the single source of truth for user preferences across the app.' },
              { title: 'App Router',         warn: false, text: 'Next.js 16 App Router with Turbopack. Not the pages router.' },
              { title: 'No ads',            warn: true,  text: 'Fully ad-free by design. No ad networks, no analytics beacons.' },
            ].map(({ title, warn, text }) => (
              <li key={title} className="py-3 border-b border-slate-800/40 flex items-start gap-3">
                {warn && (
                  <span className="mt-2 h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" aria-hidden="true" />
                )}
                {!warn && <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-700 shrink-0" aria-hidden="true" />}
                <div className="flex-1 min-w-0 space-y-1">
                  <Code>{title}</Code>
                  <p className="font-serif text-sm text-slate-300 leading-relaxed">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </SectionShell>

        {/* Search */}
        <SectionShell id="solr" eyebrow="XI" heading="Search">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Full-text search is served by Apache Solr, indexed over the article corpus (title, content,
            source, directive, and the reading-difficulty score). Search reconnects lazily so a
            restart of either the search engine or the application resolves itself without manual
            intervention.
          </p>
        </SectionShell>

        {/* Planned Features */}
        <SectionShell id="roadmap" eyebrow="XII" heading="Planned Features">
          <div className="space-y-3">
            <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">Future roadmap</div>
            <ul className="font-serif text-base text-slate-300 leading-relaxed space-y-2 list-disc ml-6">
              <li>A dedicated listening interface for the rolling audio bulletin.</li>
              <li>Backfill narration for articles published before the audio pipeline existed.</li>
              <li>Auto-translate on the single-article page (safe — one article at a time).</li>
              <li>Topic / category preferences per user.</li>
              <li>Article deduplication (SimHash / MinHash).</li>
              <li>Model auto-switching on cloud-credit exhaustion.</li>
            </ul>
          </div>
        </SectionShell>

        {/* Project context + repo */}
        <section className="py-10 border-b border-slate-800/60 text-center space-y-3 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <p>© {new Date().getFullYear()} Arc Codex</p>
          <p>
            <a
              href="https://github.com/hapnesbitt/arc-codex"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-300 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2 ring-focus rounded-sm"
            >
              github.com/hapnesbitt/arc-codex
            </a>
          </p>
        </section>

        {/* Footer — identifier block */}
        <footer className="text-center pt-12 pb-6 space-y-1 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-600">
          <p>Harold Edwin Ross Nesbitt III</p>
          <p>Fort Collins, CO · 40.5853° N, 105.0844° W</p>
          <p>A.R.C. Framework v7.38 · Connection Secure</p>
        </footer>
      </main>
    </div>
  );
}
