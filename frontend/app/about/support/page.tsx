// Filename: /frontend/app/about/support/page.tsx
// THE CROWN JEWEL - A.R.C. Codex v5.2 Showcase
// Updated Feb 27, 2026: Translation, Google SSO, User Preferences
'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { 
  BrainCircuit, Compass, GitBranch, Terminal, Database, 
  Shield, Eye, Zap, Heart, Book, Target, Layers, Rss,
  ScanLine, MessageSquare, Search, Globe, UserCircle
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import { Badge } from '@/components/ui/badge';

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  gradient: string;
}

const Section: React.FC<SectionProps> = ({ title, icon, children, gradient }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true }}
    transition={{ duration: 0.5 }}
    className={`p-8 rounded-2xl bg-slate-900/30 border ${gradient} backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.3)] transition-all duration-500 hover:scale-[1.01] hover:shadow-[0_0_40px_rgba(251,191,36,0.5)]`}
  >
    <div className="flex items-center gap-4 mb-6">
      <div className="group relative">
        {icon}
        <div className="absolute inset-0 scale-0 group-hover:scale-110 transition-transform duration-300 origin-center opacity-0 group-hover:opacity-40 bg-amber-400/20 rounded-full"></div>
      </div>
      <h2 className="text-2xl font-bold text-slate-50 mb-0 font-sans tracking-tight">{title}</h2>
    </div>
    <div className="prose prose-invert prose-lg max-w-none text-slate-200 font-sans leading-relaxed space-y-5">
      {children}
    </div>
  </motion.div>
);

const AboutPage: React.FC = () => {
  return (
    <PageWrapper>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="space-y-12">

          {/* Hero Header */}
          <motion.div 
            className="flex flex-col items-center text-center space-y-6 py-10"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-500/40 via-blue-400/30 to-sky-500/40 backdrop-blur-2xl border border-blue-400/60 shadow-[0_0_40px_rgba(59,130,246,0.5)] transition-all duration-500 hover:shadow-[0_0_50px_rgba(59,130,246,0.6)]">
              <Shield className="h-12 w-12 text-blue-300 animate-pulse-slow" />
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-sans tracking-tight text-slate-50 drop-shadow-[0_0_10px_rgba(59,130,246,0.8)]">
              The A.R.C. Codex
            </h1>
            <p className="text-xl md:text-2xl text-blue-300/90 font-sans italic drop-shadow-sm leading-relaxed">
              Argumentative Resilience Codex v5.2 — Mind Armor for the Information Age
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              <Badge variant="outline" className="bg-blue-600/20 text-blue-300 border-blue-500/30 font-sans text-sm">
                48 Cognitive Patterns
              </Badge>
              <Badge variant="outline" className="bg-cyan-600/20 text-cyan-300 border-cyan-500/30 font-sans text-sm">
                AI Content Detection
              </Badge>
              <Badge variant="outline" className="bg-purple-600/20 text-purple-300 border-purple-500/30 font-sans text-sm">
                Watchline Operator
              </Badge>
              <Badge variant="outline" className="bg-green-600/20 text-green-300 border-green-500/30 font-sans text-sm">
                67-Language Translation
              </Badge>
              <Badge variant="outline" className="bg-amber-600/20 text-amber-300 border-amber-500/30 font-sans text-sm">
                1,200+ Sources Monitored
              </Badge>
            </div>
            <div className="w-24 h-1 bg-gradient-to-r from-blue-400 to-purple-500 rounded-full animate-pulse"></div>
          </motion.div>

          {/* Mission Section */}
          <Section
            title="Our Mission: Cognitive Sovereignty"
            icon={<Target className="w-8 h-8 text-blue-400 group-hover:animate-pulse" />}
            gradient="border-blue-400/50 hover:border-blue-300/50"
          >
            <p>
              Arc Codex doesn&apos;t give you conclusions—we give you <strong>tools for independent thinking</strong>. In an era of algorithmic manipulation, synthetic narratives, and weaponized discourse, we build cognitive resilience through principled analysis.
            </p>
            <p>
              Our platform transforms information into <strong>intelligence</strong> through the A.R.C. framework: a multi-team analytical approach that steelmans arguments, detects AI-generated content, identifies manipulation patterns, seeds constructive debate, and asks bridge-building questions. We don&apos;t tell you what to think—we help you <em>think better</em>.
            </p>
            <div className="bg-slate-800/30 border border-blue-500/30 rounded-lg p-6 mt-6">
              <p className="text-blue-300 font-semibold mb-3 text-lg">Core Principles:</p>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-3">
                  <Heart className="h-5 w-5 text-pink-400 mt-1 flex-shrink-0" />
                  <span><strong>I. Attack ideas, never people</strong> — Civility without compromise</span>
                </li>
                <li className="flex items-start gap-3">
                  <Eye className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" />
                  <span><strong>II. Model thinking, not conclusions</strong> — Show your work</span>
                </li>
                <li className="flex items-start gap-3">
                  <Compass className="h-5 w-5 text-blue-400 mt-1 flex-shrink-0" />
                  <span><strong>III. Invite inquiry, don&apos;t command belief</strong> — Questions over answers</span>
                </li>
              </ul>
            </div>
          </Section>

          {/* A.R.C. Framework Section */}
          <Section
            title="The A.R.C. Framework: Three Perspectives"
            icon={<Layers className="w-8 h-8 text-amber-400 group-hover:animate-pulse" />}
            gradient="border-amber-400/50 hover:border-amber-300/50"
          >
            <p>
              Every article passes through our <strong>A.R.C. (Argumentative Resilience Codex)</strong> framework, analyzed by three independent AI teams:
            </p>
            
            <div className="space-y-6 mt-6">
              <div className="bg-red-900/10 border border-red-500/30 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-3">
                  <Database className="h-6 w-6 text-red-400" />
                  <h3 className="text-xl font-bold text-red-300 font-sans">Red Team: Facts Only</h3>
                </div>
                <p className="text-slate-300">
                  Extracts <strong>verifiable core facts</strong> without interpretation. Who, what, when, where—nothing more. Pure signal, zero noise.
                </p>
              </div>

              <div className="bg-blue-900/10 border border-blue-500/30 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-3">
                  <Book className="h-6 w-6 text-blue-400" />
                  <h3 className="text-xl font-bold text-blue-300 font-sans">Blue Team: Executive Summary</h3>
                </div>
                <p className="text-slate-300">
                  Provides <strong>balanced, comprehensive context</strong> for educated readers. Synthesizes facts into coherent narrative while maintaining strict journalistic neutrality.
                </p>
              </div>

              <div className="bg-purple-900/10 border border-purple-500/30 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-3">
                  <Shield className="h-6 w-6 text-purple-400" />
                  <h3 className="text-xl font-bold text-purple-300 font-sans">Purple Team: Watchline Operator</h3>
                </div>
                <p className="text-slate-300 mb-4">
                  The crown jewel. Our <strong>Watchline Operator</strong> performs deep cognitive analysis:
                </p>
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

          {/* Sentinel Section */}
          <Section
            title="The Sentinel: AI Content Detection"
            icon={<ScanLine className="w-8 h-8 text-cyan-400 group-hover:animate-pulse" />}
            gradient="border-cyan-400/50 hover:border-cyan-300/50"
          >
            <p>
              Every article undergoes an independent <strong>forensic analysis</strong> to detect synthetic or AI-generated content. The Sentinel operates as a separate pass after the main analysis — it cannot be influenced by the article&apos;s own claims about its authorship.
            </p>
            <div className="space-y-4 mt-6">
              <div className="bg-slate-800/30 border border-cyan-500/30 rounded-lg p-6">
                <p className="font-semibold text-cyan-300 mb-3">What the Sentinel Detects:</p>
                <ul className="space-y-2 text-slate-300 text-sm">
                  <li className="flex items-start gap-3">
                    <span className="text-cyan-400 font-bold mt-0.5">→</span>
                    <span><strong>Coherence without conviction</strong> — Text that is fluent everywhere but passionate nowhere</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-cyan-400 font-bold mt-0.5">→</span>
                    <span><strong>Coordination indicators</strong> — Talking points appearing nearly verbatim across sources</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-cyan-400 font-bold mt-0.5">→</span>
                    <span><strong>Fabrication risk</strong> — Claims attributed to sources that seem unusually convenient</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-cyan-400 font-bold mt-0.5">→</span>
                    <span><strong>Structural uniformity</strong> — Paragraph cadence, transition patterns, hedging language</span>
                  </li>
                </ul>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-4 text-center">
                  <div className="text-green-400 font-bold text-lg">HUMAN</div>
                  <div className="text-slate-400 text-xs mt-1">&lt; 20% confidence</div>
                </div>
                <div className="bg-amber-900/20 border border-amber-500/30 rounded-lg p-4 text-center">
                  <div className="text-amber-400 font-bold text-lg">UNCERTAIN</div>
                  <div className="text-slate-400 text-xs mt-1">20-60% confidence</div>
                </div>
                <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-center">
                  <div className="text-red-400 font-bold text-lg">SYNTHETIC</div>
                  <div className="text-slate-400 text-xs mt-1">&gt; 80% confidence</div>
                </div>
              </div>
              <p className="text-sm text-slate-400 italic">
                Design principle: false positives are worse than false negatives. The Sentinel is tuned to be conservative — a low score is normal and healthy. A high score is a genuine red flag.
              </p>
            </div>
          </Section>

          {/* Counter-Analyst Section */}
          <Section
            title="The Counter-Analyst: Seeding Constructive Debate"
            icon={<MessageSquare className="w-8 h-8 text-cyan-400 group-hover:animate-pulse" />}
            gradient="border-cyan-400/50 hover:border-cyan-300/50"
          >
            <p>
              Every article&apos;s comment section is seeded with a <strong>principled devil&apos;s advocate</strong> — the A.R.C. Counter-Analyst. This AI-authored comment challenges the article&apos;s strongest point using a steelman-then-flip approach, always ending with a genuine question.
            </p>
            <div className="bg-cyan-900/10 border border-cyan-500/30 rounded-lg p-6 mt-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-lg">🤖</span>
                <span className="font-semibold text-cyan-300">A.R.C. Counter-Analyst</span>
              </div>
              <p className="text-slate-300 text-sm italic">
                &ldquo;While the article convincingly argues for decentralized regulation, it assumes that existing institutions can adapt at the speed required. Given that legacy bureaucracies took decades to regulate broadcast media, what evidence suggests they can keep pace with AI-driven information systems that evolve in months?&rdquo;
              </p>
            </div>
            <p className="mt-4">
              The Counter-Analyst is <strong>transparently labeled</strong> — cyan card styling with a robot emoji prefix, visually distinct from human comments. No deception, no astroturfing. It exists to solve the &ldquo;empty dance floor&rdquo; problem: giving readers something to react to, agree with, or push back against from the moment they arrive.
            </p>
          </Section>

          {/* Translation Section — NEW */}
          <Section
            title="Universal Translation: 67 Languages"
            icon={<Globe className="w-8 h-8 text-green-400 group-hover:animate-pulse" />}
            gradient="border-green-400/50 hover:border-green-300/50"
          >
            <p>
              Every article — including its full A.R.C. analysis — can be translated on demand into <strong>67 languages</strong>. The translation button appears on every article card. Select a language, and within seconds the title, body, and all three analytical perspectives are rendered in your chosen language.
            </p>
            <div className="bg-slate-800/30 border border-green-500/30 rounded-lg p-6 mt-4">
              <p className="font-semibold text-green-300 mb-3">Language Coverage:</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm text-slate-300">
                <div>
                  <p className="text-green-400 font-semibold mb-1">European (21)</p>
                  <p className="text-slate-400 text-xs">Spanish, French, German, Italian, Polish, Ukrainian, Russian, and 14 more</p>
                </div>
                <div>
                  <p className="text-amber-400 font-semibold mb-1">Middle East (7)</p>
                  <p className="text-slate-400 text-xs">Arabic, Hebrew, Persian, Urdu, Turkish, Pashto, Kurdish</p>
                </div>
                <div>
                  <p className="text-blue-400 font-semibold mb-1">South Asia (11)</p>
                  <p className="text-slate-400 text-xs">Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, and 5 more</p>
                </div>
                <div>
                  <p className="text-purple-400 font-semibold mb-1">East Asia (11)</p>
                  <p className="text-slate-400 text-xs">Chinese (Simplified & Traditional), Japanese, Korean, Vietnamese, Thai, and 5 more</p>
                </div>
                <div>
                  <p className="text-pink-400 font-semibold mb-1">Africa (8)</p>
                  <p className="text-slate-400 text-xs">Swahili, Amharic, Hausa, Yoruba, Igbo, Zulu, Somali, Afrikaans</p>
                </div>
                <div>
                  <p className="text-cyan-400 font-semibold mb-1">Americas & Pacific (5)</p>
                  <p className="text-slate-400 text-xs">Haitian Creole, Quechua, Guaraní, Māori, Hawaiian</p>
                </div>
              </div>
            </div>
            <p className="mt-4">
              RTL languages (Arabic, Hebrew, Urdu, Persian, and others) automatically flip the article layout right-to-left. Translations are cached for 24 hours — repeat requests return instantly. The original A.R.C. analysis is never overwritten.
            </p>
            <p>
              <strong>Sign in with Google</strong> to set a default language — articles will auto-translate on load without requiring any interaction.
            </p>
          </Section>

          {/* Google SSO Section — NEW */}
          <Section
            title="Your Account: Personalization via Google"
            icon={<UserCircle className="w-8 h-8 text-blue-400 group-hover:animate-pulse" />}
            gradient="border-blue-400/50 hover:border-blue-300/50"
          >
            <p>
              Arc Codex is fully public — no account required to read anything. But signing in with Google unlocks <strong>persistent preferences</strong> that follow you across sessions and devices.
            </p>
            <div className="bg-slate-800/30 border border-blue-500/30 rounded-lg p-6 mt-4 space-y-4">
              <div className="flex items-start gap-4">
                <Globe className="h-5 w-5 text-green-400 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-slate-200">Default Language</p>
                  <p className="text-slate-400 text-sm">Set a preferred language and every article auto-translates on load — no button click required.</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <Shield className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-slate-200">Privacy First</p>
                  <p className="text-slate-400 text-sm">We store only your Google display name, email, profile picture, and preferences. No tracking, no ads, no data sales. Delete your data at any time from the settings panel.</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <Zap className="h-5 w-5 text-blue-400 mt-1 flex-shrink-0" />
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

          {/* Codex Section */}
          <Section
            title="The Codex: 48 Patterns of Cognitive Manipulation"
            icon={<BrainCircuit className="w-8 h-8 text-green-400 group-hover:animate-pulse" />}
            gradient="border-green-400/50 hover:border-green-300/50"
          >
            <p>
              The A.R.C. Codex catalogs <strong>48 cognitive anti-patterns and eristic techniques</strong> that weaponize discourse. Our Watchline Operators are trained to recognize and name these patterns:
            </p>
            
            <div className="grid md:grid-cols-2 gap-4 mt-6">
              <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
                <h4 className="font-bold text-amber-300 mb-2">Foundational (ARC-0001 to 0004)</h4>
                <ul className="text-sm text-slate-400 space-y-1">
                  <li>• The Siren&apos;s Trap</li>
                  <li>• Deniability Decoy</li>
                  <li>• The Wolf&apos;s Gambit</li>
                  <li>• Configuration Drift</li>
                </ul>
              </div>
              <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
                <h4 className="font-bold text-blue-300 mb-2">Schopenhauer (ARC-0005 to 0042)</h4>
                <ul className="text-sm text-slate-400 space-y-1">
                  <li>• Extension &amp; Homonymy</li>
                  <li>• Ad Hominem &amp; False Dilemma</li>
                  <li>• Appeal to Authority &amp; Emotion</li>
                  <li>• ...and 35 more stratagems</li>
                </ul>
              </div>
              <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
                <h4 className="font-bold text-purple-300 mb-2">Modern (ARC-0043 to 0048)</h4>
                <ul className="text-sm text-slate-400 space-y-1">
                  <li>• Motte-and-Bailey</li>
                  <li>• Gish Gallop</li>
                  <li>• Sealioning &amp; Kafka Trap</li>
                  <li>• Sanewashing</li>
                </ul>
              </div>
              <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-3xl font-bold text-amber-400 mb-1">48</div>
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

          {/* System Architecture Section */}
          <Section
            title="System Architecture: Built for Resilience"
            icon={<GitBranch className="w-8 h-8 text-amber-400 group-hover:animate-pulse" />}
            gradient="border-amber-400/50 hover:border-amber-300/50"
          >
            <p>
              Arc Codex is a decoupled, event-driven platform designed for <strong>performance, resilience, and real-time delivery</strong>. Everything runs on a homelab Z230 workstation with AI inference offloaded to a MacBook Air M1:
            </p>
            <ul className="list-disc list-outside ml-6 space-y-4 mt-4">
              <li>
                <strong>The Scribe (scribe.py):</strong> Autonomous RSS orchestrator scanning 1,200+ global sources. Stealth-capable extraction handles anti-bot protections. Runs the full pipeline: A.R.C. analysis → Sentinel forensics → Counter-Analyst comment generation.
              </li>
              <li>
                <strong>The Publisher (manual_publisher.py):</strong> Instant processing of user submissions. Supports text, URL, and file uploads with the same Sentinel and Counter-Analyst passes as automated ingestion.
              </li>
              <li>
                <strong>The Translator:</strong> On-demand translation of articles and analysis into 67 languages via Ollama. Results cached in Redis for 24 hours. RTL language support (Arabic, Hebrew, Urdu, and others) built in.
              </li>
              <li>
                <strong>The Stream (Redis Streams):</strong> Real-time event bus delivering completed analyses to articles instantly. Zero polling, zero filesystem overhead.
              </li>
              <li>
                <strong>The API (main.py):</strong> Flask backend handling submissions, analysis, translation, user preferences, search, reactions, and the RSS feed.
              </li>
              <li>
                <strong>The Search Engine (Solr):</strong> Full-text search with highlighted snippets, relevance scoring, and title-boosted ranking.
              </li>
              <li>
                <strong>The Data Core (Redis):</strong> In-memory store for articles, analyses, comments, reactions, translations, user preferences, and real-time streams.
              </li>
              <li>
                <strong>The Frontend (Next.js 16):</strong> Server-rendered React with App Router, Tribonacci infinite scroll, markdown rendering, Auth.js Google SSO, and real-time translation.
              </li>
              <li>
                <strong>The AI Engine (Ollama on M1):</strong> Cloud-first with local fallback. Benchmarked models selected for optimal speed-to-quality ratio. Think-token stripping ensures clean output from reasoning models. ~12x faster than local Z230 inference.
              </li>
            </ul>
          </Section>

          {/* Subscribe Section */}
          <Section
            title="Subscribe: RSS Feed"
            icon={<Rss className="w-8 h-8 text-orange-400 group-hover:animate-pulse" />}
            gradient="border-orange-400/50 hover:border-orange-300/50"
          >
            <p>
              Get the full A.R.C. analysis delivered straight to your reader. Every article includes Red, Blue, and Purple team analysis plus the Chimera Score — no website visit required.
            </p>
            <div className="bg-slate-800/30 border border-orange-500/30 rounded-lg p-6 mt-4">
              <p className="font-semibold text-orange-300 mb-3">Feed URL:</p>
              <div className="flex items-center gap-3">
                <code className="bg-slate-900/50 text-orange-300 px-4 py-2 rounded-lg text-sm font-mono border border-orange-500/20 flex-1 overflow-x-auto">
                  https://arc-codex.com/api/rss
                </code>
              </div>
              <p className="text-slate-400 text-sm mt-4">
                Works with Thunderbird, Newsboat, Feedly, Inoreader, or any RSS reader. Filter by category with <code className="text-orange-300/70">?category=threat_intelligence</code> or limit results with <code className="text-orange-300/70">?limit=10</code>.
              </p>
            </div>
            <p className="mt-4">
              Also available at <code className="text-orange-300/70">/api/feed.xml</code>. The feed updates with every new article and analysis.
            </p>
          </Section>

          {/* Philosophy Section */}
          <Section
            title="Philosophical Foundation"
            icon={<Heart className="w-8 h-8 text-pink-400 group-hover:animate-pulse" />}
            gradient="border-pink-400/50 hover:border-pink-300/50"
          >
            <p>
              The A.R.C. framework rests on five humanist principles:
            </p>
            <ol className="list-decimal list-inside space-y-4 mt-4 text-slate-300">
              <li>
                <strong className="text-amber-300">Cognitive Sovereignty:</strong> Readers deserve tools for independent thinking, not conclusions handed down from authority.
              </li>
              <li>
                <strong className="text-blue-300">Steelmanning:</strong> Understand the strongest version of any position before critiquing it. Attack ideas at their best, never their worst.
              </li>
              <li>
                <strong className="text-purple-300">Bridge-Building:</strong> Seek to understand and connect across differences, not to win and divide.
              </li>
              <li>
                <strong className="text-green-300">Defensive Capability:</strong> Truth and human dignity must be defended, not just performed. We study manipulation to resist it.
              </li>
              <li>
                <strong className="text-pink-300">Intellectual Humility:</strong> Acknowledge uncertainty while maintaining principled clarity. Confidence without arrogance.
              </li>
            </ol>
          </Section>

          {/* Call to Action */}
          <motion.div 
            className="bg-gradient-to-br from-amber-500/10 via-purple-500/10 to-blue-500/10 border border-amber-400/30 rounded-2xl p-8 text-center"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <Zap className="h-12 w-12 text-amber-400 mx-auto mb-4" />
            <h3 className="text-2xl font-bold text-slate-50 mb-4 font-sans">
              Ready to Build Cognitive Resilience?
            </h3>
            <p className="text-slate-300 font-sans mb-6 max-w-2xl mx-auto">
              Every article you read here strengthens your ability to think independently, recognize manipulation, and engage constructively across differences. This is how we build a more thoughtful world.
            </p>
            <div className="flex flex-wrap gap-4 justify-center">
              <a 
                href="/publish" 
                className="inline-block px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-900 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-sans"
              >
                Publish Your Story
              </a>
              <a 
                href="/search" 
                className="inline-block px-8 py-4 bg-gradient-to-r from-slate-700 to-slate-600 hover:from-slate-600 hover:to-slate-500 text-slate-100 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-sans border border-slate-500/30"
              >
                Search the Archive
              </a>
            </div>
          </motion.div>

          {/* Support Contact */}
          <motion.div
            className="bg-gradient-to-br from-amber-500/10 via-orange-500/10 to-transparent border border-amber-400/30 rounded-2xl p-8 text-center"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <h3 className="text-2xl font-bold text-slate-50 mb-4 font-sans">
              Technical Support
            </h3>
            <p className="text-slate-300 font-sans mb-6 max-w-2xl mx-auto">
              Questions about the platform, API, or A.R.C. framework? Reach out directly.
            </p>
            <a
              href="mailto:support@arc-codex.com"
              className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-900 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-sans"
            >
              support@arc-codex.com
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
                href="https://github.com/hapnesbitt/arc-codex" 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-amber-300/90 hover:text-amber-200 transition-colors duration-300"
              >
                Join the Expedition
              </a>.
            </p>
          </footer>

        </div>
      </div>
    </PageWrapper>
  );
};

export default AboutPage;
