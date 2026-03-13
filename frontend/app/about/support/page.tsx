// Filename: /frontend/app/about/support/page.tsx
// Arc Codex — Support & Docs
// Updated: Mar 7, 2026 — arc.sh command reference, 162 languages, Next.js 16.1.6, ARIA pass, email corrected

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
  BrainCircuit, Compass, GitBranch, Terminal, Database,
  Shield, Eye, Zap, Heart, Book, Target, Layers, Rss,
  ScanLine, MessageSquare, Globe, UserCircle, RotateCcw
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import { Badge } from '@/components/ui/badge';

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  gradient: string;
  id: string;
}

const Section: React.FC<SectionProps> = ({ title, icon, children, gradient, id }) => (
  <motion.section
    id={id}
    aria-labelledby={`${id}-heading`}
    initial={{ opacity: 0, y: 20 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true }}
    transition={{ duration: 0.5 }}
    className={`p-8 rounded-2xl bg-slate-900/30 border ${gradient} backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.3)] transition-all duration-500 hover:scale-[1.01] hover:shadow-[0_0_40px_rgba(251,191,36,0.5)]`}
  >
    <div className="flex items-center gap-4 mb-6">
      <div aria-hidden="true">{icon}</div>
      <h2 id={`${id}-heading`} className="text-2xl font-bold text-slate-50 mb-0 font-sans tracking-tight">
        {title}
      </h2>
    </div>
    <div className="prose prose-invert prose-lg max-w-none text-slate-200 font-sans leading-relaxed space-y-5">
      {children}
    </div>
  </motion.section>
);

// Command row component for arc.sh reference
interface CmdRowProps {
  cmd: string;
  desc: string;
  badge?: string;
  badgeColor?: string;
}

const CmdRow: React.FC<CmdRowProps> = ({ cmd, desc, badge, badgeColor = 'text-amber-300 border-amber-500/40 bg-amber-600/10' }) => (
  <div className="flex items-start gap-4 py-3 border-b border-slate-700/40 last:border-0">
    <code className="text-amber-300 font-mono text-sm bg-slate-900/60 px-3 py-1 rounded-lg border border-amber-500/20 whitespace-nowrap flex-shrink-0">
      {cmd}
    </code>
    <div className="flex-1 min-w-0">
      <span className="text-slate-300 text-sm">{desc}</span>
      {badge && (
        <span className={`ml-2 text-xs border px-2 py-0.5 rounded-full font-medium ${badgeColor}`}>
          {badge}
        </span>
      )}
    </div>
  </div>
);

const SupportPage: React.FC = () => {
  return (
    <PageWrapper>
      {/* Skip to content */}
      <a
        href="#support-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
      >
        Skip to main content
      </a>

      <main id="support-main" aria-label="Arc Codex Support and Documentation">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="space-y-12">

            {/* Hero */}
            <motion.header
              className="flex flex-col items-center text-center space-y-6 py-10"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <div
                className="p-4 rounded-2xl bg-gradient-to-br from-indigo-500/40 via-blue-400/30 to-sky-500/40 backdrop-blur-2xl border border-blue-400/60 shadow-[0_0_40px_rgba(59,130,246,0.5)]"
                aria-hidden="true"
              >
                <Shield className="h-12 w-12 text-blue-300 animate-pulse" />
              </div>
              <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-sans tracking-tight text-slate-50 drop-shadow-[0_0_10px_rgba(59,130,246,0.8)]">
                The A.R.C. Codex
              </h1>
              <p className="text-xl md:text-2xl text-blue-300/90 font-sans italic leading-relaxed">
                Argumentative Resilience Codex v5.2 — Mind Armor for the Information Age
              </p>
              <div className="flex flex-wrap gap-3 justify-center" role="list" aria-label="Platform stats">
                <Badge role="listitem" variant="outline" className="bg-blue-600/20 text-blue-300 border-blue-500/30 font-sans text-sm">48 Cognitive Patterns</Badge>
                <Badge role="listitem" variant="outline" className="bg-cyan-600/20 text-cyan-300 border-cyan-500/30 font-sans text-sm">AI Content Detection</Badge>
                <Badge role="listitem" variant="outline" className="bg-purple-600/20 text-purple-300 border-purple-500/30 font-sans text-sm">Watchline Operator</Badge>
                <Badge role="listitem" variant="outline" className="bg-green-600/20 text-green-300 border-green-500/30 font-sans text-sm">162-Language Translation</Badge>
                <Badge role="listitem" variant="outline" className="bg-amber-600/20 text-amber-300 border-amber-500/30 font-sans text-sm">2,004 Sources Monitored</Badge>
              </div>
              <div className="w-24 h-1 bg-gradient-to-r from-blue-400 to-purple-500 rounded-full animate-pulse" aria-hidden="true" />
            </motion.header>

            {/* MISSION */}
            <Section id="mission" title="Our Mission: Cognitive Sovereignty"
              icon={<Target className="w-8 h-8 text-blue-400" />}
              gradient="border-blue-400/50 hover:border-blue-300/50"
            >
              <p>
                Arc Codex doesn&apos;t give you conclusions — we give you <strong>tools for independent thinking</strong>. In an era of algorithmic manipulation, synthetic narratives, and weaponized discourse, we build cognitive resilience through principled analysis.
              </p>
              <p>
                Our platform transforms information into <strong>intelligence</strong> through the A.R.C. framework: a multi-team analytical approach that steelmans arguments, detects AI-generated content, identifies manipulation patterns, seeds constructive debate, and asks bridge-building questions.
              </p>
              <div className="bg-slate-800/30 border border-blue-500/30 rounded-lg p-6 mt-6">
                <p className="text-blue-300 font-semibold mb-3 text-lg">Core Principles:</p>
                <ul className="space-y-3 text-slate-300" role="list">
                  <li className="flex items-start gap-3">
                    <Heart className="h-5 w-5 text-pink-400 mt-1 flex-shrink-0" aria-hidden="true" />
                    <span><strong>I. Attack ideas, never people</strong> — Civility without compromise</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Eye className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" aria-hidden="true" />
                    <span><strong>II. Model thinking, not conclusions</strong> — Show your work</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Compass className="h-5 w-5 text-blue-400 mt-1 flex-shrink-0" aria-hidden="true" />
                    <span><strong>III. Invite inquiry, don&apos;t command belief</strong> — Questions over answers</span>
                  </li>
                </ul>
              </div>
            </Section>

            {/* ARC FRAMEWORK */}
            <Section id="arc-framework" title="The A.R.C. Framework: Three Perspectives"
              icon={<Layers className="w-8 h-8 text-amber-400" />}
              gradient="border-amber-400/50 hover:border-amber-300/50"
            >
              <p>
                Every article passes through our <strong>A.R.C. (Argumentative Resilience Codex)</strong> framework, analyzed by three independent AI teams:
              </p>
              <div className="space-y-6 mt-6">
                <div className="bg-red-900/10 border border-red-500/30 rounded-lg p-6">
                  <div className="flex items-center gap-3 mb-3">
                    <Database className="h-6 w-6 text-red-400" aria-hidden="true" />
                    <h3 className="text-xl font-bold text-red-300 font-sans">Red Team: Facts Only</h3>
                  </div>
                  <p className="text-slate-300">Extracts <strong>verifiable core facts</strong> without interpretation. Who, what, when, where — nothing more. Pure signal, zero noise.</p>
                </div>
                <div className="bg-blue-900/10 border border-blue-500/30 rounded-lg p-6">
                  <div className="flex items-center gap-3 mb-3">
                    <Book className="h-6 w-6 text-blue-400" aria-hidden="true" />
                    <h3 className="text-xl font-bold text-blue-300 font-sans">Blue Team: Executive Summary</h3>
                  </div>
                  <p className="text-slate-300">Provides <strong>balanced, comprehensive context</strong> for educated readers. Synthesizes facts into coherent narrative while maintaining strict journalistic neutrality.</p>
                </div>
                <div className="bg-purple-900/10 border border-purple-500/30 rounded-lg p-6">
                  <div className="flex items-center gap-3 mb-3">
                    <Shield className="h-6 w-6 text-purple-400" aria-hidden="true" />
                    <h3 className="text-xl font-bold text-purple-300 font-sans">Purple Team: Watchline Operator</h3>
                  </div>
                  <p className="text-slate-300 mb-4">The crown jewel. Our <strong>Watchline Operator</strong> performs deep cognitive analysis:</p>
                  <ol className="space-y-2 text-slate-300 list-decimal list-inside">
                    <li><strong>Steelman the narrative</strong> — Find the strongest version of the argument</li>
                    <li><strong>Scan for A.R.C. anti-patterns</strong> — Detect cognitive manipulation (48 patterns catalogued)</li>
                    <li><strong>Root cause analysis</strong> — Identify underlying paradigms and assumptions</li>
                    <li><strong>Practical implications</strong> — Impact on human dignity and agency</li>
                    <li><strong>Bridge-building questions</strong> — Help readers think across perspectives</li>
                    <li><strong>Counterstrike scan</strong> — Hypothetical influence campaign pattern analysis</li>
                  </ol>
                </div>
              </div>
            </Section>

            {/* SENTINEL */}
            <Section id="sentinel" title="The Sentinel: AI Content Detection"
              icon={<ScanLine className="w-8 h-8 text-cyan-400" />}
              gradient="border-cyan-400/50 hover:border-cyan-300/50"
            >
              <p>
                Every article undergoes an independent <strong>forensic analysis</strong> to detect synthetic or AI-generated content. The Sentinel operates as a separate pass after the main analysis — it cannot be influenced by the article&apos;s own claims about its authorship.
              </p>
              <div className="space-y-4 mt-6">
                <div className="bg-slate-800/30 border border-cyan-500/30 rounded-lg p-6">
                  <p className="font-semibold text-cyan-300 mb-3">What the Sentinel Detects:</p>
                  <ul className="space-y-2 text-slate-300 text-sm" role="list">
                    <li className="flex items-start gap-3"><span className="text-cyan-400 font-bold mt-0.5" aria-hidden="true">→</span><span><strong>Coherence without conviction</strong> — Text that is fluent everywhere but passionate nowhere</span></li>
                    <li className="flex items-start gap-3"><span className="text-cyan-400 font-bold mt-0.5" aria-hidden="true">→</span><span><strong>Coordination indicators</strong> — Talking points appearing nearly verbatim across sources</span></li>
                    <li className="flex items-start gap-3"><span className="text-cyan-400 font-bold mt-0.5" aria-hidden="true">→</span><span><strong>Fabrication risk</strong> — Claims attributed to sources that seem unusually convenient</span></li>
                    <li className="flex items-start gap-3"><span className="text-cyan-400 font-bold mt-0.5" aria-hidden="true">→</span><span><strong>Structural uniformity</strong> — Paragraph cadence, transition patterns, hedging language</span></li>
                  </ul>
                </div>
                <div className="grid grid-cols-3 gap-4" role="list" aria-label="Sentinel confidence levels">
                  <div role="listitem" className="bg-green-900/20 border border-green-500/30 rounded-lg p-4 text-center">
                    <div className="text-green-400 font-bold text-lg">HUMAN</div>
                    <div className="text-slate-400 text-xs mt-1">&lt; 20% confidence</div>
                  </div>
                  <div role="listitem" className="bg-amber-900/20 border border-amber-500/30 rounded-lg p-4 text-center">
                    <div className="text-amber-400 font-bold text-lg">UNCERTAIN</div>
                    <div className="text-slate-400 text-xs mt-1">20–60% confidence</div>
                  </div>
                  <div role="listitem" className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-center">
                    <div className="text-red-400 font-bold text-lg">SYNTHETIC</div>
                    <div className="text-slate-400 text-xs mt-1">&gt; 80% confidence</div>
                  </div>
                </div>
                <p className="text-sm text-slate-400 italic">
                  Design principle: false positives are worse than false negatives. The Sentinel is tuned to be conservative — a low score is normal and healthy. A high score is a genuine red flag.
                </p>
              </div>
            </Section>

            {/* COUNTER-ANALYST */}
            <Section id="counter-analyst" title="The Counter-Analyst: Seeding Constructive Debate"
              icon={<MessageSquare className="w-8 h-8 text-cyan-400" />}
              gradient="border-cyan-400/50 hover:border-cyan-300/50"
            >
              <p>
                Every article&apos;s comment section is seeded with a <strong>principled devil&apos;s advocate</strong> — the A.R.C. Counter-Analyst. This AI-authored comment challenges the article&apos;s strongest point using a steelman-then-flip approach, always beginning with &ldquo;This article&rdquo; and ending with a genuine question.
              </p>
              <div className="bg-cyan-900/10 border border-cyan-500/30 rounded-lg p-6 mt-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-lg" aria-hidden="true">🤖</span>
                  <span className="font-semibold text-cyan-300">A.R.C. Counter-Analyst</span>
                </div>
                <p className="text-slate-300 text-sm italic">
                  &ldquo;This article convincingly argues for decentralized regulation, but assumes existing institutions can adapt at the speed required. Given that legacy bureaucracies took decades to regulate broadcast media, what evidence suggests they can keep pace with AI-driven information systems that evolve in months?&rdquo;
                </p>
              </div>
              <p className="mt-4">
                The Counter-Analyst is <strong>transparently labeled</strong> — cyan card styling with a robot emoji prefix, visually distinct from human comments. No deception, no astroturfing. Its comment also becomes the body of every LinkedIn auto-post, carrying the adversarial signal into the public feed.
              </p>
            </Section>

            {/* TRANSLATION */}
            <Section id="translation" title="Universal Translation: 162 Languages"
              icon={<Globe className="w-8 h-8 text-green-400" />}
              gradient="border-green-400/50 hover:border-green-300/50"
            >
              <p>
                Every article — including its full A.R.C. analysis — can be translated on demand into <strong>162 languages</strong>. Select a language from the translate button on any article card, and within seconds the title, body, and all three analytical perspectives are rendered in your chosen language.
              </p>
              <div className="bg-slate-800/30 border border-green-500/30 rounded-lg p-6 mt-4">
                <p className="font-semibold text-green-300 mb-3">Language Coverage:</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm text-slate-300">
                  <div><p className="text-green-400 font-semibold mb-1">European (21)</p><p className="text-slate-400 text-xs">Spanish, French, German, Italian, Polish, Ukrainian, Russian, and 14 more</p></div>
                  <div><p className="text-amber-400 font-semibold mb-1">Middle East (7)</p><p className="text-slate-400 text-xs">Arabic, Hebrew, Persian, Urdu, Turkish, Pashto, Kurdish</p></div>
                  <div><p className="text-blue-400 font-semibold mb-1">South Asia (11)</p><p className="text-slate-400 text-xs">Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, and 5 more</p></div>
                  <div><p className="text-purple-400 font-semibold mb-1">East Asia (11)</p><p className="text-slate-400 text-xs">Chinese (Simplified & Traditional), Japanese, Korean, Vietnamese, Thai, and 5 more</p></div>
                  <div><p className="text-pink-400 font-semibold mb-1">Africa (8)</p><p className="text-slate-400 text-xs">Swahili, Amharic, Hausa, Yoruba, Igbo, Zulu, Somali, Afrikaans</p></div>
                  <div><p className="text-cyan-400 font-semibold mb-1">Americas & Pacific (5+)</p><p className="text-slate-400 text-xs">Haitian Creole, Quechua, Guaraní, Māori, Hawaiian, and many more</p></div>
                </div>
              </div>
              <p className="mt-4">
                RTL languages (Arabic, Hebrew, Urdu, Persian, and others) automatically flip the article layout right-to-left. Translations are cached for 24 hours — repeat requests return instantly. <strong>Sign in with Google</strong> to set a default language for auto-translation on every article load.
              </p>
            </Section>

            {/* GOOGLE SSO */}
            <Section id="account" title="Your Account: Personalization via Google"
              icon={<UserCircle className="w-8 h-8 text-blue-400" />}
              gradient="border-blue-400/50 hover:border-blue-300/50"
            >
              <p>
                Arc Codex is fully public — no account required to read anything. But signing in with Google unlocks <strong>persistent preferences</strong> that follow you across sessions and devices.
              </p>
              <div className="bg-slate-800/30 border border-blue-500/30 rounded-lg p-6 mt-4 space-y-4">
                <div className="flex items-start gap-4">
                  <Globe className="h-5 w-5 text-green-400 mt-1 flex-shrink-0" aria-hidden="true" />
                  <div>
                    <p className="font-semibold text-slate-200">Default Language</p>
                    <p className="text-slate-400 text-sm">Set a preferred language and every article auto-translates on load — no button click required.</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <Shield className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" aria-hidden="true" />
                  <div>
                    <p className="font-semibold text-slate-200">Privacy First</p>
                    <p className="text-slate-400 text-sm">We store only your Google display name, email, profile picture, and preferences. No tracking, no ads, no data sales. Delete your account at any time from the settings panel.</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <Zap className="h-5 w-5 text-blue-400 mt-1 flex-shrink-0" aria-hidden="true" />
                  <div>
                    <p className="font-semibold text-slate-200">One Click</p>
                    <p className="text-slate-400 text-sm">Google OAuth — no password to create or remember. Click the sign-in button in the sidebar, authorize once, and you&apos;re in.</p>
                  </div>
                </div>
              </div>
              <p className="mt-4 text-slate-400 text-sm italic">
                Coming soon: saved searches with email digest notifications, reading history, and topic preferences.
              </p>
            </Section>

            {/* CODEX PATTERNS */}
            <Section id="codex" title="The Codex: 48 Patterns of Cognitive Manipulation"
              icon={<BrainCircuit className="w-8 h-8 text-green-400" />}
              gradient="border-green-400/50 hover:border-green-300/50"
            >
              <p>
                The A.R.C. Codex catalogs <strong>48 cognitive anti-patterns and eristic techniques</strong> that weaponize discourse. Our Watchline Operators are trained to recognize and name these patterns:
              </p>
              <div className="grid md:grid-cols-2 gap-4 mt-6">
                <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
                  <h3 className="font-bold text-amber-300 mb-2">Foundational (ARC-0001 to 0004)</h3>
                  <ul className="text-sm text-slate-400 space-y-1">
                    <li>• The Siren&apos;s Trap</li>
                    <li>• Deniability Decoy</li>
                    <li>• The Wolf&apos;s Gambit</li>
                    <li>• Configuration Drift</li>
                  </ul>
                </div>
                <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
                  <h3 className="font-bold text-blue-300 mb-2">Schopenhauer (ARC-0005 to 0042)</h3>
                  <ul className="text-sm text-slate-400 space-y-1">
                    <li>• Extension &amp; Homonymy</li>
                    <li>• Ad Hominem &amp; False Dilemma</li>
                    <li>• Appeal to Authority &amp; Emotion</li>
                    <li>• ...and 35 more stratagems</li>
                  </ul>
                </div>
                <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
                  <h3 className="font-bold text-purple-300 mb-2">Modern (ARC-0043 to 0048)</h3>
                  <ul className="text-sm text-slate-400 space-y-1">
                    <li>• Motte-and-Bailey</li>
                    <li>• Gish Gallop</li>
                    <li>• Sealioning &amp; Kafka Trap</li>
                    <li>• Sanewashing</li>
                  </ul>
                </div>
                <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-amber-400 mb-1" aria-label="48 total patterns">48</div>
                    <div className="text-xs text-slate-400">Total Patterns</div>
                  </div>
                </div>
              </div>
              <div className="mt-6 bg-green-900/10 border border-green-500/30 rounded-lg p-4">
                <p className="text-green-300 text-sm">
                  <strong>The Kalisti Principle:</strong> &ldquo;You cannot exclude Eris from the party. She will lob the problem into your garden regardless.&rdquo; — Better to study manipulation than pretend it doesn&apos;t exist. The Codex is a shield, not a weapon.
                </p>
              </div>
            </Section>

            {/* SYSTEM ARCHITECTURE */}
            <Section id="architecture" title="System Architecture: Built for Resilience"
              icon={<GitBranch className="w-8 h-8 text-amber-400" />}
              gradient="border-amber-400/50 hover:border-amber-300/50"
            >
              <p>
                Arc Codex is a decoupled, event-driven platform built for <strong>performance, resilience, and real-time delivery</strong>. The stack runs on a homelab HP Z230 workstation with AI inference offloaded to a MacBook Air M1 via Ollama:
              </p>
              <ul className="list-disc list-outside ml-6 space-y-4 mt-4">
                <li><strong>The Scribe (scribe.py):</strong> Autonomous RSS orchestrator scanning 1,200+ global sources. Stealth-capable extraction handles anti-bot protections. Runs the full pipeline: A.R.C. analysis → Sentinel forensics → Counter-Analyst comment generation.</li>
                <li><strong>The Publisher (manual_publisher.py):</strong> Instant processing of user submissions. Supports text, URL, and file uploads with the same Sentinel and Counter-Analyst passes as automated ingestion.</li>
                <li><strong>The LinkedIn Poster (linkedin_poster.py):</strong> Monitors Redis for new articles and auto-posts title + Counter-Analyst comment + URL to the Arc Codex LinkedIn page. Toggleable via Redis key. 30–180s jitter prevents spam patterns.</li>
                <li><strong>The Translator:</strong> On-demand translation into 162 languages via Ollama. Results cached in Redis for 24 hours. RTL language support built in.</li>
                <li><strong>The Stream (Redis Streams):</strong> Real-time event bus delivering completed analyses instantly. Zero polling, zero filesystem overhead.</li>
                <li><strong>The API (main.py):</strong> Flask/Gunicorn backend handling submissions, analysis, translation, user preferences, search, reactions, and the RSS feed.</li>
                <li><strong>The Search Engine (Solr):</strong> Full-text search with highlighted snippets, relevance scoring, and title-boosted ranking across 4,500+ articles.</li>
                <li><strong>The Data Core (Redis):</strong> In-memory store for articles, analyses, comments, reactions, translations, user preferences, and real-time streams.</li>
                <li><strong>The Frontend (Next.js 16.1.6):</strong> Dockerized server-rendered React with App Router, Tribonacci infinite scroll, markdown rendering, Auth.js Google SSO, and real-time translation.</li>
                <li><strong>The AI Engine (Ollama on M1):</strong> Cloud-first with local fallback. Benchmarked models selected for optimal speed-to-quality ratio. ~12x faster than local Z230 inference.</li>
              </ul>
            </Section>

            {/* ARC.SH COMMAND REFERENCE */}
            <Section id="arc-sh" title="Platform Administration: arc.sh"
              icon={<Terminal className="w-8 h-8 text-green-400" />}
              gradient="border-green-400/50 hover:border-green-300/50"
            >
              <p>
                The entire Arc Codex stack is managed by a single shell script — <code className="text-green-300 font-mono text-sm bg-slate-900/50 px-2 py-0.5 rounded">arc.sh</code>. It controls all 9 services including the Docker frontend container, backup schedules, and watchdog monitoring.
              </p>

              <div className="mt-6 space-y-6">
                {/* Stack control */}
                <div className="bg-slate-800/30 border border-green-500/20 rounded-xl p-6">
                  <h3 className="font-bold text-green-300 mb-4 font-mono text-sm uppercase tracking-wider">Stack Control</h3>
                  <CmdRow cmd="arc.sh start" desc="Start all 9 services (gunicorn, scribe, manual_publisher, stream_consumer, analyzer, mailer, linkedin_poster, frontend, watchdog)" />
                  <CmdRow cmd="arc.sh stop" desc="Gracefully stop all services including Docker frontend" />
                  <CmdRow cmd="arc.sh restart" desc="Full stack restart" />
                  <CmdRow cmd="arc.sh status" desc="Live status of all services with PIDs, ports, log sizes, and backup inventory" />
                </div>

                {/* Service-level */}
                <div className="bg-slate-800/30 border border-blue-500/20 rounded-xl p-6">
                  <h3 className="font-bold text-blue-300 mb-4 font-mono text-sm uppercase tracking-wider">Service-Level Control</h3>
                  <CmdRow cmd="arc.sh start [service]" desc="Start a single service by name" />
                  <CmdRow cmd="arc.sh stop [service]" desc="Stop a single service" />
                  <CmdRow cmd="arc.sh restart [service]" desc="Restart a single service" />
                  <CmdRow cmd="arc.sh logs [service]" desc="Tail logs for a specific service" />
                  <p className="text-slate-400 text-xs mt-3 font-mono">
                    Services: gunicorn · scribe · manual_publisher · stream_consumer · analyzer · mailer · linkedin_poster · frontend · watchdog
                  </p>
                </div>

                {/* Build */}
                <div className="bg-slate-800/30 border border-amber-500/20 rounded-xl p-6">
                  <h3 className="font-bold text-amber-300 mb-4 font-mono text-sm uppercase tracking-wider">Build</h3>
                  <CmdRow cmd="arc.sh build" desc="Build and deploy the Docker frontend container (Next.js 16.1.6)" />
                  <CmdRow cmd="arc.sh build --clean" desc="Force clear webpack cache before build" />
                </div>

                {/* Backup */}
                <div className="bg-slate-800/30 border border-purple-500/20 rounded-xl p-6">
                  <h3 className="font-bold text-purple-300 mb-4 font-mono text-sm uppercase tracking-wider">Backup & Restore</h3>
                  <CmdRow cmd="arc.sh backup" desc="Fast SSD backup — code only, stack stops briefly. Runs nightly at 3am via cron. Keeps 5 most recent." />
                  <CmdRow cmd="arc.sh backup-cold" desc="Full cold archive to /mnt/data — stack stays up. Runs weekly Sunday 2am. Keeps 30." />
                  <CmdRow cmd="arc.sh checkup" desc="Health check across all services and dependencies" />
                  <CmdRow
                    cmd="arc.sh restore"
                    desc="List available backups, select one, confirm, extract, and restart the stack"
                    badge="coming soon"
                    badgeColor="text-slate-400 border-slate-500/40 bg-slate-700/30"
                  />
                  <CmdRow cmd="arc.sh prune [dry]" desc="Remove old backups beyond retention limit. Use 'dry' to preview without deleting." />
                </div>

                {/* LinkedIn toggle */}
                <div className="bg-slate-800/30 border border-cyan-500/20 rounded-xl p-6">
                  <h3 className="font-bold text-cyan-300 mb-4 font-mono text-sm uppercase tracking-wider">LinkedIn Auto-Poster</h3>
                  <CmdRow cmd="redis-cli set linkedin:autopost 1" desc="Enable automatic LinkedIn posting for new articles" />
                  <CmdRow cmd="redis-cli set linkedin:autopost 0" desc="Disable LinkedIn auto-posting (daemon keeps running)" />
                  <p className="text-slate-400 text-xs mt-3">The poster daemon runs continuously — the Redis key is a live on/off switch with no restart required.</p>
                </div>
              </div>

              <div className="mt-6 bg-green-900/10 border border-green-500/30 rounded-lg p-4">
                <p className="text-green-300 text-sm font-mono">
                  Cron schedule: backup at 0 3 * * * · backup-cold at 0 2 * * 0
                </p>
              </div>
            </Section>

            {/* RSS */}
            <Section id="rss" title="Subscribe: RSS Feed"
              icon={<Rss className="w-8 h-8 text-orange-400" />}
              gradient="border-orange-400/50 hover:border-orange-300/50"
            >
              <p>
                Get the full A.R.C. analysis delivered straight to your reader. Every article includes Red, Blue, and Purple team analysis plus the Chimera Score — no website visit required.
              </p>
              <div className="bg-slate-800/30 border border-orange-500/30 rounded-lg p-6 mt-4">
                <p className="font-semibold text-orange-300 mb-3">Feed URL:</p>
                <code className="block bg-slate-900/50 text-orange-300 px-4 py-2 rounded-lg text-sm font-mono border border-orange-500/20 overflow-x-auto">
                  https://arc-codex.com/api/rss
                </code>
                <p className="text-slate-400 text-sm mt-4">
                  Works with Thunderbird, Newsboat, Feedly, Inoreader, or any RSS reader. Filter by category with <code className="text-orange-300/70">?category=threat_intelligence</code> or limit results with <code className="text-orange-300/70">?limit=10</code>.
                </p>
              </div>
              <p className="mt-4">
                Also available at <code className="text-orange-300/70">/api/feed.xml</code>. The feed updates with every new article and analysis.
              </p>
            </Section>

            {/* PHILOSOPHY */}
            <Section id="philosophy" title="Philosophical Foundation"
              icon={<Heart className="w-8 h-8 text-pink-400" />}
              gradient="border-pink-400/50 hover:border-pink-300/50"
            >
              <p>The A.R.C. framework rests on five humanist principles:</p>
              <ol className="list-decimal list-inside space-y-4 mt-4 text-slate-300">
                <li><strong className="text-amber-300">Cognitive Sovereignty:</strong> Readers deserve tools for independent thinking, not conclusions handed down from authority.</li>
                <li><strong className="text-blue-300">Steelmanning:</strong> Understand the strongest version of any position before critiquing it. Attack ideas at their best, never their worst.</li>
                <li><strong className="text-purple-300">Bridge-Building:</strong> Seek to understand and connect across differences, not to win and divide.</li>
                <li><strong className="text-green-300">Defensive Capability:</strong> Truth and human dignity must be defended, not just performed. We study manipulation to resist it.</li>
                <li><strong className="text-pink-300">Intellectual Humility:</strong> Acknowledge uncertainty while maintaining principled clarity. Confidence without arrogance.</li>
              </ol>
            </Section>

            {/* CTA */}
            <motion.div
              className="bg-gradient-to-br from-amber-500/10 via-purple-500/10 to-blue-500/10 border border-amber-400/30 rounded-2xl p-8 text-center"
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
            >
              <Zap className="h-12 w-12 text-amber-400 mx-auto mb-4" aria-hidden="true" />
              <h2 className="text-2xl font-bold text-slate-50 mb-4 font-sans">
                Ready to Build Cognitive Resilience?
              </h2>
              <p className="text-slate-300 font-sans mb-6 max-w-2xl mx-auto">
                Every article you read here strengthens your ability to think independently, recognize manipulation, and engage constructively across differences.
              </p>
              <div className="flex flex-wrap gap-4 justify-center">
                <a
                  href="/publish"
                  aria-label="Publish your story to Arc Codex"
                  className="inline-block px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-900 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-sans focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
                >
                  Publish Your Story
                </a>
                <a
                  href="/search"
                  aria-label="Search the Arc Codex article archive"
                  className="inline-block px-8 py-4 bg-gradient-to-r from-slate-700 to-slate-600 hover:from-slate-600 hover:to-slate-500 text-slate-100 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-sans border border-slate-500/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/60"
                >
                  Search the Archive
                </a>
              </div>
            </motion.div>

            {/* Support contact */}
            <motion.div
              className="bg-gradient-to-br from-amber-500/10 via-orange-500/10 to-transparent border border-amber-400/30 rounded-2xl p-8 text-center"
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
            >
              <h2 className="text-2xl font-bold text-slate-50 mb-4 font-sans">Technical Support</h2>
              <p className="text-slate-300 font-sans mb-6 max-w-2xl mx-auto">
                Questions about the platform, API, or A.R.C. framework? Reach out directly to the founder.
              </p>
              <a
                href="mailto:ross@arc-codex.com"
                aria-label="Email ross@arc-codex.com for technical support"
                className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-900 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-sans focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
              >
                ross@arc-codex.com
              </a>
              <p className="mt-4 text-xs text-slate-500 font-mono">
                Response time varies — this is a homelab project, not a SaaS.
              </p>
            </motion.div>

            {/* Footer */}
            <footer className="text-center text-sm text-slate-400 pt-8 pb-4 border-t border-slate-700/50">
              <p className="font-sans">
                © {new Date().getFullYear()} Arc Codex. Protected by the A.R.C. Cognitive Framework.{' '}
                <a
                  href="https://github.com/hapnesbitt"
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="Hap Nesbitt on GitHub (opens in new tab)"
                  className="text-amber-300/90 hover:text-amber-200 transition-colors duration-300 focus-visible:outline-none focus-visible:underline"
                >
                  github.com/hapnesbitt
                </a>
              </p>
            </footer>

          </div>
        </div>
      </main>
    </PageWrapper>
  );
};

export default SupportPage;
