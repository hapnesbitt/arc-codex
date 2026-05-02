// Filename: /frontend/app/about/support/page.tsx
// The Art of Discernment — User Codex.
// Librarian aesthetic. Reconstructed from page.tsx.Apr20 (full how-to content)
// with the Gemini doctrinal framing folded into the lead paragraph of each
// section. Server component — collapsible panels use native <details>.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'The Art of Discernment — Arc Codex',
  description: 'How to read the Arc Codex feed, understand the A.R.C. analysis, translate, publish, and share.',
};

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

const Panel: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <details className="group/p border-b border-slate-800/40">
    <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer flex items-center justify-between gap-4 py-3 px-2 -mx-2 rounded-sm hover:bg-slate-800/30 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40">
      <span className="font-sans text-xs uppercase tracking-[0.2em] text-slate-300">{label}</span>
      <ChevronRight className="h-3 w-3 text-slate-500 group-open/p:rotate-90 transition-transform" aria-hidden="true" />
    </summary>
    <div className="pt-2 pb-4 px-2 font-serif text-base text-slate-300 leading-relaxed space-y-3">
      {children}
    </div>
  </details>
);

const Tip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="font-serif text-sm text-slate-300 italic leading-relaxed flex items-start gap-2">
    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" aria-hidden="true" />
    <span>{children}</span>
  </p>
);

export default function SupportCodex() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            The Art of Discernment
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            How to Use Arc Codex
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            Your guide to reading intelligence, understanding analysis, and contributing to the feed.
          </p>
        </header>

        {/* Reading the Feed */}
        <SectionShell id="feed" eyebrow="I · Observation" heading="Reading the Feed">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            The main feed shows articles collected from 2,088 sources worldwide, analyzed by the A.R.C. framework as they arrive. Each card represents one article with its full analysis inline.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="The Chimera Difficulty Score (circle gauge)">
              <p>
                The circular gauge on each card shows reading difficulty on a 0–100 scale, synthesizing four grade-level readability metrics: Flesch–Kincaid, Coleman–Liau, SMOG, and Dale–Chall. This is a purely informational signal — not a quality or manipulation score.
              </p>
              <ul className="list-disc ml-6 space-y-1 not-italic">
                <li>0–30 — accessible (Kindergarten → Middle School)</li>
                <li>31–50 — moderate (High School → College)</li>
                <li>41–55 — the sweet spot for quality journalism</li>
                <li>56–70 — challenging (Graduate → Academic)</li>
                <li>71–100 — formidable (Expert → Quantum Electrodynamics)</li>
              </ul>
              <p className="text-sm text-slate-400">
                Labels run from &ldquo;Kindergarten&rdquo; through &ldquo;Quantum Electrodynamics.&rdquo; Higher scores indicate denser, more technical prose — not better or worse content.
              </p>
            </Panel>
            <Panel label="Directive tags (footer)">
              <p>
                The tag at the bottom of each card shows which editorial directive matched the article — e.g. <em>Active Threat Campaigns</em> or <em>Economic Policy</em>. Click it to navigate to the wiki page for that directive.
              </p>
            </Panel>
            <Panel label="Infinite scroll">
              <p>
                The feed loads in Tribonacci batches — 2, 3, 5, 10, 18… articles at a time as you scroll. This keeps the initial load fast while giving you a deep feed on long sessions.
              </p>
            </Panel>
          </div>
          <Tip>Click any article title to go to the full article page, where all analysis sections are expanded by default.</Tip>
        </SectionShell>

        {/* A.R.C. Analysis */}
        <SectionShell id="analysis" eyebrow="II · The Analytical Triad" heading="Understanding the A.R.C. Analysis">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Every article is run through three independent AI analytical passes. Expand any section on a card to read it. We do not tell you what to think — we show you how the thinking was constructed.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="Facts Only — Red Team">
              <p>
                Extracts verifiable facts only — who, what, when, where. No interpretation, no opinion. If it can&apos;t be independently verified, it&apos;s not in here.
              </p>
            </Panel>
            <Panel label="Executive Summary — Blue Team">
              <p>
                A balanced, journalist-style summary written for an educated general reader. Covers the key points without editorializing. Good starting point if you&apos;re short on time.
              </p>
            </Panel>
            <Panel label="Full Take — Purple Team">
              <p>
                The deep analysis. Covers: steelmanning the narrative, scanning for 48 A.R.C. cognitive anti-patterns, root cause analysis, implications for human dignity, bridge-building questions, and a hypothetical influence campaign analysis. This is where Arc Codex earns its keep.
              </p>
            </Panel>
            <Panel label="Counter-Analyst comment">
              <p>
                Every article gets an adversarial AI comment, labeled with a robot emoji and cyan styling. It&apos;s deliberately provocative — designed to give readers something to push back against. The &ldquo;empty dance floor&rdquo; problem: nobody wants to be the first to comment. The Counter-Analyst solves that.
              </p>
            </Panel>
          </div>
        </SectionShell>

        {/* Sentinel */}
        <SectionShell id="sentinel" eyebrow="III · Synthetic Vigilance" heading="Sentinel — AI Content Detection">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Sentinel runs a forensic pass on every article to estimate whether it was written by a human or generated by AI. It&apos;s tuned conservative — false positives (calling human writing synthetic) are treated as worse than false negatives. A verdict of <em>Synthetic</em> is not a judgment of value, but a disclosure of origin.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="Verdicts explained">
              <ul className="list-disc ml-6 space-y-1 not-italic">
                <li><span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-400 mr-2">Human</span> synthetic confidence below 20%</li>
                <li><span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-400 mr-2">Uncertain</span> 20–60% confidence</li>
                <li><span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-400 mr-2">Synthetic</span> above 80% confidence</li>
              </ul>
              <p className="text-sm text-slate-400">
                The confidence bar shows the raw synthetic probability. The Signals Detected section lists specific indicators that contributed to the verdict.
              </p>
            </Panel>
          </div>
          <Tip>Sentinel is not a spam filter — a Synthetic verdict means the writing pattern resembles AI output, not that the content is wrong or malicious.</Tip>
        </SectionShell>

        {/* Translation */}
        <SectionShell id="translation" eyebrow="IV · Universal Availability" heading="Translation">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex supports 162 languages via the TranslateGemma model running locally on the M1. Translations are cached for 24 hours per article/language pair.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="How to translate an article">
              <ol className="list-decimal ml-6 space-y-1 not-italic">
                <li>Click the Translate button below the article title.</li>
                <li>If you have a preferred language set in your account, it fires immediately.</li>
                <li>Otherwise a language picker appears — select your language.</li>
                <li>Once translated, a language pill appears. Click it again to switch languages or reset to the original.</li>
              </ol>
            </Panel>
            <Panel label="Translating foreign-language articles into English">
              <p>
                English is first in the dropdown specifically for this use case. Articles from German, Swedish, Spanish, and other sources can be read in English instantly. Arc Codex sources include Aftenposten, NRC, Der Spiegel, and others.
              </p>
            </Panel>
            <Panel label="Setting a preferred language">
              <p>
                Sign in with Google or GitHub, then open the account menu (top right). Set your preferred language and Arc Codex will auto-translate articles when the source language differs from your preference.
              </p>
            </Panel>
          </div>
        </SectionShell>

        {/* Publishing */}
        <SectionShell id="publishing" eyebrow="V · The Act of Publication" heading="Publishing to Arc Codex">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Signed-in users can submit content directly to the Arc Codex pipeline via the{' '}
            <Link href="/publish" className="text-slate-100 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2">
              Publish
            </Link>{' '}
            page. All submitted content goes through the full A.R.C. analysis pipeline.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="Share a URL">
              <p>
                Paste any article URL — Arc Codex fetches the content, runs A.R.C. analysis, and publishes it to the feed. YouTube URLs are also supported (metadata and description are analyzed).
              </p>
            </Panel>
            <Panel label="Write Text">
              <p>
                Paste or write article text directly. Good for content behind paywalls or content you&apos;ve written yourself. The full A.R.C. pipeline runs on your text.
              </p>
            </Panel>
            <Panel label="Upload a File">
              <p>
                Upload .txt, .md, .pdf, .docx, or .odt files. Arc Codex extracts the text and runs the full analysis.
              </p>
            </Panel>
            <Panel label="Write a Prompt">
              <p>
                Describe what you want Arc Codex to write — it generates a full article using AI, then runs it through the A.R.C. pipeline. The title is derived automatically from the generated content.
              </p>
            </Panel>
            <Panel label="Make Public vs Keep Private">
              <p>When you click Publish, a confirmation modal asks how to publish:</p>
              <ul className="list-disc ml-6 space-y-1 not-italic">
                <li><strong>Make Public</strong> — article appears in the public feed for all readers.</li>
                <li><strong>Keep Private 🔒</strong> — article is visible only to you when signed in. Nobody else can see it.</li>
              </ul>
              <p className="text-sm text-slate-400">
                Private articles appear in your feed with a lock icon. Use the admin console to manage your publications.
              </p>
            </Panel>
          </div>
          <Tip>Submissions are processed asynchronously — your article will appear in the feed within 1–2 scribe cycles (up to ~10 minutes). Priority queue items are processed first at the top of each cycle.</Tip>
        </SectionShell>

        {/* Sharing */}
        <SectionShell id="sharing" eyebrow="VI · Stewardship" heading="Sharing Articles">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Every card has a share menu (the arrow icon) with options to copy the link, post to X, share on Facebook, share on LinkedIn, post to Bluesky, post to Mastodon, or send via email.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="What gets shared">
              <p>
                The share payload includes: article title, the Counter-Analyst comment (normalized to start with &ldquo;This article&rdquo;), and the article URL. If no Counter-Analyst comment exists yet, just title + URL is shared.
              </p>
            </Panel>
            <Panel label="Post to Bluesky">
              <p>
                The Bluesky option opens a Bluesky compose window with the share payload prefilled. Submit it from your own Bluesky account.
              </p>
            </Panel>
            <Panel label="Sharing translated articles">
              <p>
                If you&apos;re viewing a translation, the share link includes a{' '}
                <code className="font-mono text-sm text-slate-300 bg-slate-900 border border-slate-800 rounded-sm px-1.5 py-0.5">?lang=</code>{' '}
                parameter so recipients see the same language automatically.
              </p>
            </Panel>
          </div>
        </SectionShell>

        {/* Account */}
        <SectionShell id="account" eyebrow="VII · Soft Authentication" heading="Your Account">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex uses soft authentication — the site is fully public and requires no login. Signing in with Google or GitHub unlocks preferences, publishing, and private articles.
          </p>
          <div className="border-t border-slate-800/40">
            <Panel label="What signing in gives you">
              <ul className="list-disc ml-6 space-y-1 not-italic">
                <li>Set a preferred translation language (auto-fires on foreign articles).</li>
                <li>Publish articles to the feed (public or private).</li>
                <li>See your private articles in the feed.</li>
                <li>Your publications tracked in the admin console.</li>
              </ul>
            </Panel>
            <Panel label="Privacy">
              <p>
                No tracking, no ads, no data sales. Arc Codex stores: your email, name, profile picture (from OAuth provider), preferred language, and account timestamps. GDPR self-service deletion is available in the account menu.
              </p>
            </Panel>
          </div>
        </SectionShell>

        {/* Contact */}
        <section className="py-10 border-b border-slate-800/60 text-center space-y-3">
          <p className="font-serif text-base text-slate-300 italic">Questions not answered here?</p>
          <a
            href="mailto:ross@arc-codex.com"
            className="inline-block font-sans text-xs uppercase tracking-[0.2em] text-slate-300 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
          >
            ross@arc-codex.com
          </a>
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
