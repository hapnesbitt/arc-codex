// Filename: /frontend/app/about/contact/page.tsx
// Stewardship — Hap Nesbitt.
// Librarian aesthetic. Reconstructed with PRIME integration. Server component.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight, ExternalLink } from 'lucide-react';
import { ARC_FRAMEWORK_VERSION } from '@/lib/version';

export const metadata: Metadata = {
  title: 'Stewardship — Hap Nesbitt',
  description: 'Independent AI infrastructure engineer and systems architect. Builder of Arc Codex, Huntaegis, School of Chat, and Book Radio. Available for contract engagements.',
};

const EXPERTISE = [
  {
    label: 'Cognitive Security',
    body: 'Creator of the A.R.C. framework — 48 cognitive anti-patterns for detecting manipulation, disinformation, and adversarial narratives at scale.',
  },
  {
    label: 'Email Authentication',
    body: 'SPF, DKIM, DMARC, BIMI architecture and deployment. Self-hosted MTA hardening, PTR alignment, and deliverability forensics.',
  },
  {
    label: 'AI Infrastructure',
    body: 'Agentic LLM pipelines, Ollama / local inference, Redis-backed orchestration, ensemble architectures. Production systems on bare metal.',
  },
  {
    label: 'Systems Architecture',
    body: '30+ years Linux / UNIX. IAM, entitlement automation, OpenShift CI/CD. Former Proofpoint (employee #10), Wells Fargo, Morgan Stanley, J.P. Morgan Chase.',
  },
];

const LIVE_PLATFORMS = [
  { label: 'Arc Codex', body: 'News intelligence with adversarial AI analysis.' },
  { label: 'Huntaegis', body: 'The cybersecurity fork — the same platform, retargeted at threat intelligence.' },
  { label: 'School of Chat', body: 'Quiz and badge integrity, graded by AI.' },
  { label: 'Book Radio', body: 'A continuous narrated-audio stream of public-domain texts.' },
];

const CONTACTS: Array<{ label: string; value: string; href: string; external: boolean; aria: string }> = [
  {
    label: 'Direct Inquiry',
    value: 'ross@arc-codex.com',
    href: 'mailto:ross@arc-codex.com',
    external: false,
    aria: 'Send email to ross@arc-codex.com',
  },
  {
    label: 'Source · GitHub',
    value: 'hapnesbitt',
    href: 'https://github.com/hapnesbitt',
    external: true,
    aria: 'hapnesbitt on GitHub (opens in new tab)',
  },
];

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Stewardship · Founder &amp; Systems Architect
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Hap Nesbitt
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            Independent AI infrastructure engineer and systems architect. Builder of Arc Codex, Huntaegis, School of Chat, and Book Radio. Available for contract engagements.
          </p>
          <blockquote className="border-l border-slate-700 pl-4 max-w-xl mx-auto text-left font-serif text-base italic text-slate-300 leading-relaxed mt-6">
            Responsibility is the final layer of the stack. We do not just build systems; we steward the information that flows through them.
          </blockquote>
        </header>

        {/* What runs today */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            What Runs Today
          </h2>
          <ul className="border-t border-slate-800/40">
            {LIVE_PLATFORMS.map((item) => (
              <li key={item.label} className="py-4 border-b border-slate-800/40 space-y-1">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{item.label}</div>
                <p className="font-serif text-base text-slate-200 leading-relaxed">{item.body}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Fields of Engagement */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Fields of Engagement
          </h2>
          <ul className="border-t border-slate-800/40">
            {EXPERTISE.map((item) => (
              <li key={item.label} className="py-4 border-b border-slate-800/40 space-y-1">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-400">{item.label}</div>
                <p className="font-serif text-base text-slate-200 leading-relaxed">{item.body}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* PRIME */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            PRIME
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            PRIME is the direction this work points: a zero-UI generative education fabric joining
            continuous audio streams to automated oral examination. The components run today as
            separate systems — Book Radio for the audio, School of Chat for the examination. PRIME
            is the argument that they belong together. A prospectus, not yet a product.
          </p>
        </section>

        {/* Contact methods */}
        <section className="py-10 border-b border-slate-800/60 space-y-6">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Get In Touch
          </h2>
          <ul className="border-t border-slate-800/40">
            {CONTACTS.map((c) => (
              <li key={c.label} className="border-b border-slate-800/40">
                <a
                  href={c.href}
                  target={c.external ? '_blank' : undefined}
                  rel={c.external ? 'noopener noreferrer' : undefined}
                  aria-label={c.aria}
                  className="group flex items-center justify-between gap-4 py-4 px-2 -mx-2 hover:bg-slate-800/30 transition-colors rounded-sm ring-focus"
                >
                  <div className="flex-1 space-y-1">
                    <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">{c.label}</div>
                    <div className="font-mono text-base text-slate-200 group-hover:text-slate-50 transition-colors">{c.value}</div>
                  </div>
                  {c.external
                    ? <ExternalLink className="h-3 w-3 text-slate-600 group-hover:text-slate-300 transition-colors shrink-0" aria-hidden="true" />
                    : <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-slate-300 transition-colors shrink-0" aria-hidden="true" />
                  }
                </a>
              </li>
            ))}
          </ul>
        </section>

        {/* Arc Codex back-link */}
        <section className="py-10 border-b border-slate-800/60 text-center space-y-3">
          <p className="font-serif text-base text-slate-400 italic">See the work in action.</p>
          <Link
            href="/"
            aria-label="Go to Arc Codex intelligence feed"
            className="inline-flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-200 hover:text-slate-50 transition-colors ring-focus rounded-sm"
          >
            Arc Codex Intelligence Feed
            <ChevronRight className="h-3 w-3" aria-hidden="true" />
          </Link>
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