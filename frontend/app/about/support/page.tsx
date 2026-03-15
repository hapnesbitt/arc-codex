// Filename: /frontend/app/about/support/page.tsx
// Arc Codex — How to Use Arc Codex
// v2.0 Mar 15 2026 — Complete user guide rewrite

'use client';

import React, { useState, useId } from 'react';
import { motion } from 'framer-motion';
import {
  BrainCircuit, ChevronDown, ChevronRight, Shield, Eye,
  Globe, MessageSquare, Lock, Share2, Upload, Crosshair,
  ScanLine, Combine, Zap, BookOpen, Terminal, AlertTriangle,
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';

const reducedMotion =
  typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;

const fadeUp = reducedMotion
  ? {}
  : { initial: { opacity: 0, y: 20 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true }, transition: { duration: 0.5 } };

const heroAnim = reducedMotion
  ? {}
  : { initial: { opacity: 0, y: -20 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6 } };

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  gradient: string;
  id?: string;
}

const Section: React.FC<SectionProps> = ({ title, icon, children, gradient, id }) => (
  <motion.section
    {...fadeUp}
    aria-labelledby={id ? `${id}-heading` : undefined}
    className={`p-8 rounded-2xl bg-slate-900/30 border ${gradient} backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.15)] transition-all duration-500`}
  >
    <div className="flex items-center gap-4 mb-6">
      <span aria-hidden="true">{icon}</span>
      <h2 id={id ? `${id}-heading` : undefined} className="text-2xl font-bold text-slate-50 tracking-tight">
        {title}
      </h2>
    </div>
    <div className="text-slate-300 leading-relaxed space-y-4">
      {children}
    </div>
  </motion.section>
);

interface CollapseProps { label: string; children: React.ReactNode; }
const Collapse: React.FC<CollapseProps> = ({ label, children }) => {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonId = useId();
  return (
    <div className="border border-white/10 rounded-lg overflow-hidden">
      <button
        id={buttonId}
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/40 hover:bg-slate-800/70 transition-colors text-left outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 focus-visible:ring-inset"
      >
        <span className="text-slate-200 font-mono text-sm font-medium">{label}</span>
        {open
          ? <ChevronDown size={16} className="text-amber-400" aria-hidden="true" />
          : <ChevronRight size={16} className="text-slate-500" aria-hidden="true" />
        }
      </button>
      {open && (
        <div id={panelId} role="region" aria-labelledby={buttonId} className="px-4 py-4 bg-slate-900/50 border-t border-white/5 text-slate-300 text-sm space-y-2 leading-relaxed">
          {children}
        </div>
      )}
    </div>
  );
};

const Tip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div role="note" className="flex gap-3 bg-amber-900/15 border border-amber-500/30 rounded-lg p-4 text-amber-200 text-sm">
    <Zap size={16} className="text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
    <span>{children}</span>
  </div>
);

const SupportPage: React.FC = () => {
  return (
    <PageWrapper>
      <a href="#support-main" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300">
        Skip to main content
      </a>

      <main id="support-main" className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="space-y-12">

          {/* Hero */}
          <motion.header {...heroAnim} className="flex flex-col items-center text-center space-y-6 py-10">
            <div className="p-4 rounded-2xl bg-gradient-to-br from-amber-500/30 via-orange-400/20 to-yellow-500/30 border border-amber-400/50 shadow-[0_0_40px_rgba(251,191,36,0.4)]" aria-hidden="true">
              <BookOpen className="h-12 w-12 text-amber-300" />
            </div>
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-slate-50">How to Use Arc Codex</h1>
            <p className="text-xl text-amber-300/80 italic max-w-2xl mx-auto">
              Your guide to reading intelligence, understanding analysis, and contributing to the feed.
            </p>
            <div className="w-24 h-1 bg-gradient-to-r from-amber-400 to-orange-500 rounded-full" aria-hidden="true" />
          </motion.header>

          {/* Reading the Feed */}
          <Section id="feed" title="Reading the Feed" icon={<Eye className="w-8 h-8 text-amber-400" />} gradient="border-amber-400/40">
            <p>
              The main feed shows articles collected from over 1,200 sources worldwide, analyzed by the A.R.C. framework as they arrive. Each card represents one article with its full analysis inline.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="The Tone Score (circle gauge)">
                <p>The circular score on each card measures objectivity on a scale of 0–100. <strong className="text-amber-300">Higher is more objective.</strong></p>
                <ul className="list-disc ml-5 space-y-1 mt-2">
                  <li><span className="text-emerald-400">Green (75+)</span> — factual, measured tone</li>
                  <li><span className="text-amber-400">Amber (40–74)</span> — mixed or opinionated</li>
                  <li><span className="text-red-400">Red (0–39)</span> — highly charged or divisive</li>
                </ul>
                <p className="mt-2 text-slate-400 text-xs">Note: calibrated for English. Non-English articles may score unexpectedly.</p>
              </Collapse>
              <Collapse label="Directive tags (footer)">
                <p>The tag at the bottom of each card shows which editorial directive matched the article — e.g. <em>Active Threat Campaigns</em> or <em>Economic Policy</em>. Click it to filter the entire feed to that topic.</p>
              </Collapse>
              <Collapse label="Infinite scroll">
                <p>The feed loads in Tribonacci batches — 2, 3, 5, 10, 18... articles at a time as you scroll. This keeps initial load fast while giving you a deep feed on long sessions.</p>
              </Collapse>
            </div>
            <Tip>Click any article title to go to the full article page, where all analysis sections are expanded by default.</Tip>
          </Section>

          {/* A.R.C. Analysis */}
          <Section id="analysis" title="Understanding the A.R.C. Analysis" icon={<BrainCircuit className="w-8 h-8 text-purple-400" />} gradient="border-purple-400/40">
            <p>
              Every article is run through three independent AI analytical passes. Expand any section on a card to read it.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="🎯 Facts Only (Red Team)">
                <p>Extracts verifiable facts only — who, what, when, where. No interpretation, no opinion. If it can&apos;t be independently verified, it&apos;s not in here.</p>
              </Collapse>
              <Collapse label="🔵 Executive Summary (Blue Team)">
                <p>A balanced, journalist-style summary written for an educated general reader. Covers the key points without editorializing. Good starting point if you&apos;re short on time.</p>
              </Collapse>
              <Collapse label="🟣 Full Take (Purple Team)">
                <p>The deep analysis. Covers: steelmanning the narrative, scanning for 48 A.R.C. cognitive anti-patterns, root cause analysis, implications for human dignity, bridge-building questions, and a hypothetical influence campaign analysis. This is where Arc Codex earns its keep.</p>
              </Collapse>
              <Collapse label="🤖 Counter-Analyst comment">
                <p>Every article gets an adversarial AI comment, labeled with a robot emoji and cyan styling. It&apos;s deliberately provocative — designed to give readers something to push back against. The &quot;empty dance floor&quot; problem: nobody wants to be the first to comment. The Counter-Analyst solves that.</p>
              </Collapse>
            </div>
          </Section>

          {/* Sentinel */}
          <Section id="sentinel" title="Sentinel — AI Content Detection" icon={<ScanLine className="w-8 h-8 text-cyan-400" />} gradient="border-cyan-400/40">
            <p>
              Sentinel runs a forensic pass on every article to estimate whether it was written by a human or generated by AI. It&apos;s tuned conservative — false positives (calling human writing synthetic) are treated as worse than false negatives.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="Verdicts explained">
                <ul className="list-disc ml-5 space-y-1">
                  <li><span className="text-emerald-400">HUMAN</span> — synthetic confidence below 20%</li>
                  <li><span className="text-amber-400">UNCERTAIN</span> — 20–60% confidence</li>
                  <li><span className="text-red-400">SYNTHETIC</span> — above 80% confidence</li>
                </ul>
                <p className="mt-2 text-slate-400 text-xs">The confidence bar shows the raw synthetic probability. The Signals Detected section lists specific indicators that contributed to the verdict.</p>
              </Collapse>
            </div>
            <Tip>Sentinel is not a spam filter — a SYNTHETIC verdict means the writing pattern resembles AI output, not that the content is wrong or malicious.</Tip>
          </Section>

          {/* Translation */}
          <Section id="translation" title="Translation" icon={<Globe className="w-8 h-8 text-blue-400" />} gradient="border-blue-400/40">
            <p>
              Arc Codex supports 162 languages via the TranslateGemma model running locally on the M1. Translations are cached for 24 hours per article/language pair.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="How to translate an article">
                <ol className="list-decimal ml-5 space-y-1">
                  <li>Click the <strong>Translate</strong> button below the article title</li>
                  <li>If you have a preferred language set in your account, it fires immediately</li>
                  <li>Otherwise a language picker appears — select your language</li>
                  <li>Once translated, a language pill appears. Click it again to switch languages or reset to original</li>
                </ol>
              </Collapse>
              <Collapse label="Translating foreign-language articles into English">
                <p>English is first in the dropdown specifically for this use case. Articles from German, Swedish, Spanish, and other sources can be read in English instantly. Arc Codex sources include Aftenposten, NRC, Der Spiegel, and others.</p>
              </Collapse>
              <Collapse label="Setting a preferred language">
                <p>Sign in with Google or GitHub, then open the account menu (top right). Set your preferred language and Arc Codex will auto-translate articles when the source language differs from your preference.</p>
              </Collapse>
            </div>
          </Section>

          {/* Publishing */}
          <Section id="publishing" title="Publishing to Arc Codex" icon={<Upload className="w-8 h-8 text-green-400" />} gradient="border-green-400/40">
            <p>
              Signed-in users can submit content directly to the Arc Codex pipeline via the <a href="/publish" className="text-amber-400 hover:text-amber-300 underline">Publish</a> page. All submitted content goes through the full A.R.C. analysis pipeline.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="Share a URL">
                <p>Paste any article URL — Arc Codex fetches the content, runs A.R.C. analysis, and publishes it to the feed. YouTube URLs are also supported (metadata and description are analyzed).</p>
              </Collapse>
              <Collapse label="Write Text">
                <p>Paste or write article text directly. Good for content behind paywalls or content you&apos;ve written yourself. The full A.R.C. pipeline runs on your text.</p>
              </Collapse>
              <Collapse label="Upload a File">
                <p>Upload .txt, .md, .pdf, or .docx files. Arc Codex extracts the text and runs full analysis.</p>
              </Collapse>
              <Collapse label="Write a Prompt">
                <p>Describe what you want Arc Codex to write — it generates a full article using AI, then runs it through the A.R.C. pipeline. The title is derived automatically from the generated content.</p>
              </Collapse>
              <Collapse label="Make Public vs Keep Private">
                <p>When you click Publish, a confirmation modal asks how to publish:</p>
                <ul className="list-disc ml-5 space-y-1 mt-1">
                  <li><strong>Make Public</strong> — article appears in the public feed for all readers</li>
                  <li><strong>Keep Private 🔒</strong> — article is visible only to you when signed in. Nobody else can see it.</li>
                </ul>
                <p className="mt-1 text-slate-400 text-xs">Private articles appear in your feed with a lock icon. Use kasmir7 option [11] to manage your publications from the admin console.</p>
              </Collapse>
            </div>
            <Tip>Submissions are processed asynchronously — your article will appear in the feed within 1–2 scribe cycles (up to ~10 minutes). Priority queue items are processed first at the top of each cycle.</Tip>
          </Section>

          {/* Sharing */}
          <Section id="sharing" title="Sharing Articles" icon={<Share2 className="w-8 h-8 text-pink-400" />} gradient="border-pink-400/40">
            <p>
              Every card has a share menu (the arrow icon) with options to copy the link, post to X, share on Facebook, share on LinkedIn, post to Bluesky, or send via email.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="What gets shared">
                <p>The share payload includes: article title, the Counter-Analyst comment (normalized to start with &quot;This article&quot;), and the article URL. If no Counter-Analyst comment exists yet, just title + URL is shared.</p>
              </Collapse>
              <Collapse label="Post to Bluesky">
                <p>The Bluesky option posts directly to the configured Bluesky account via the AT Protocol API. It creates a post with title, blurb, and a link card. No window opens — the post fires in the background and the button flashes &quot;Posted!&quot; on success.</p>
              </Collapse>
              <Collapse label="Sharing translated articles">
                <p>If you&apos;re viewing a translation, the share link includes a <code className="font-mono text-xs bg-slate-800/60 border border-white/10 rounded px-1.5 py-0.5 text-amber-300/90">?lang=</code> parameter so recipients see the same language automatically.</p>
              </Collapse>
            </div>
          </Section>

          {/* Account */}
          <Section id="account" title="Your Account" icon={<Lock className="w-8 h-8 text-slate-400" />} gradient="border-slate-600/40">
            <p>
              Arc Codex uses soft authentication — the site is fully public and requires no login. Signing in with Google or GitHub unlocks preferences, publishing, and private articles.
            </p>
            <div className="space-y-3 mt-4">
              <Collapse label="What signing in gives you">
                <ul className="list-disc ml-5 space-y-1">
                  <li>Set a preferred translation language (auto-fires on foreign articles)</li>
                  <li>Publish articles to the feed (public or private)</li>
                  <li>See your private articles in the feed</li>
                  <li>Your publications tracked in the admin console</li>
                </ul>
              </Collapse>
              <Collapse label="Privacy">
                <p>No tracking, no ads, no data sales. Arc Codex stores: your email, name, profile picture (from OAuth provider), preferred language, and account timestamps. GDPR self-service deletion is available in the account menu.</p>
              </Collapse>
            </div>
          </Section>

          {/* Contact */}
          <motion.div {...fadeUp} className="text-center space-y-4 py-8 border-t border-slate-800/50">
            <p className="text-slate-400">Questions not answered here?</p>
            <a href="mailto:ross@arc-codex.com" className="text-amber-400 hover:text-amber-300 underline underline-offset-4 font-medium">
              ross@arc-codex.com
            </a>
          </motion.div>

        </div>
      </main>
    </PageWrapper>
  );
};

export default SupportPage;
