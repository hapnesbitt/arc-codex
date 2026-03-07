// Filename: /frontend/app/about/sales/page.tsx
// Arc Codex — Vision & Mission (Sales)
// Updated: Mar 7, 2026 — ARC framework accuracy, ARIA pass, email corrected

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
  Shield, Target, Zap,
  Sparkles, Globe, Rocket, Users, Lightbulb,
  ArrowRight
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
    className={`p-8 rounded-2xl bg-slate-900/40 border ${gradient} backdrop-blur-2xl shadow-[0_0_25px_rgba(59,130,246,0.2)] transition-all duration-500 hover:scale-[1.01] hover:shadow-[0_0_50px_rgba(59,130,246,0.4)]`}
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

const SalesPage: React.FC = () => {
  return (
    <PageWrapper>
      {/* Skip to content */}
      <a
        href="#sales-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
      >
        Skip to main content
      </a>

      <main id="sales-main" aria-label="Arc Codex Vision and Mission">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="space-y-16 py-12">

            {/* HERO */}
            <motion.header
              className="flex flex-col items-center text-center space-y-8"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
            >
              <div
                className="p-5 rounded-3xl bg-gradient-to-br from-blue-500/30 via-cyan-400/20 to-indigo-500/30 backdrop-blur-3xl border border-blue-400/50 shadow-[0_0_60px_rgba(59,130,246,0.4)]"
                aria-hidden="true"
              >
                <Sparkles className="h-14 w-14 text-blue-200 animate-pulse" />
              </div>

              <div className="space-y-4">
                <h1 className="text-5xl sm:text-6xl md:text-7xl font-black font-sans tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-blue-100 via-blue-300 to-indigo-200 drop-shadow-sm">
                  AI for the Independent Mind
                </h1>
                <p className="text-2xl md:text-3xl text-blue-300/80 font-sans font-light max-w-3xl mx-auto leading-tight italic">
                  Bridging the gap between elite technology and human-scale innovation.
                </p>
              </div>

              <div className="flex flex-wrap gap-3 justify-center" role="list" aria-label="Core values">
                <Badge role="listitem" variant="outline" className="bg-blue-600/20 text-blue-300 border-blue-500/40 px-4 py-1 text-sm">
                  Democratic Innovation
                </Badge>
                <Badge role="listitem" variant="outline" className="bg-indigo-600/20 text-indigo-300 border-indigo-500/40 px-4 py-1 text-sm">
                  Cognitive Freedom
                </Badge>
                <Badge role="listitem" variant="outline" className="bg-cyan-600/20 text-cyan-300 border-cyan-500/40 px-4 py-1 text-sm">
                  Human-Centric Design
                </Badge>
              </div>

              <div className="w-32 h-1.5 bg-gradient-to-r from-transparent via-blue-500 to-transparent rounded-full opacity-50" aria-hidden="true" />
            </motion.header>

            {/* MISSION */}
            <Section
              id="mission"
              title="Our Mission: Empowering the 100%"
              icon={<Target className="w-9 h-9 text-blue-400" />}
              gradient="border-blue-400/40 hover:border-blue-300/60"
            >
              <p>
                In a world where AI is often kept behind the gates of massive corporations, Arc Codex is built as a <strong>public utility for intelligence</strong>. Our mission is to take the most sophisticated analytical tools on the planet and place them directly into the hands of the individuals who need them most: creators, researchers, small business owners, and local leaders.
              </p>
              <p>
                We don&apos;t just provide software; we provide <strong>clarity</strong>. The A.R.C. (Argumentative Resilience Codex) framework transforms raw, overwhelming data into structured, multi-perspective insight — so you can compete at the highest level without the corporate overhead.
              </p>
            </Section>

            {/* VISION */}
            <Section
              id="vision"
              title="The Vision: Your Cognitive Competitive Edge"
              icon={<Rocket className="w-9 h-9 text-indigo-400" />}
              gradient="border-indigo-400/40 hover:border-indigo-300/60"
            >
              <p>
                Arc Codex monitors over <strong>1,200 RSS sources</strong> across 68 languages in real time, running every article through a multi-model AI ensemble that produces red, blue, and purple team analysis — surface-level consensus and the dissenting signal beneath it.
              </p>
              <div className="grid md:grid-cols-3 gap-6 mt-8" role="list" aria-label="Platform capabilities">
                <div role="listitem" className="bg-blue-900/10 border border-blue-500/20 p-5 rounded-xl">
                  <Globe className="h-7 w-7 text-blue-400 mb-3" aria-hidden="true" />
                  <h3 className="font-bold text-white mb-2">Global Awareness</h3>
                  <p className="text-sm text-slate-300">68-language translation with intelligent caching — every perspective, instantly readable.</p>
                </div>
                <div role="listitem" className="bg-indigo-900/10 border border-indigo-500/20 p-5 rounded-xl">
                  <Lightbulb className="h-7 w-7 text-indigo-400 mb-3" aria-hidden="true" />
                  <h3 className="font-bold text-white mb-2">Counter-Analyst</h3>
                  <p className="text-sm text-slate-300">Every article gets an adversarial AI review — the argument you weren&apos;t supposed to see.</p>
                </div>
                <div role="listitem" className="bg-cyan-900/10 border border-cyan-500/20 p-5 rounded-xl">
                  <Users className="h-7 w-7 text-cyan-400 mb-3" aria-hidden="true" />
                  <h3 className="font-bold text-white mb-2">Radical Reach</h3>
                  <p className="text-sm text-slate-300">Automatic LinkedIn publishing amplifies your signal — no media team required.</p>
                </div>
              </div>
            </Section>

            {/* INTEGRITY */}
            <Section
              id="integrity"
              title="The Reality: Information Integrity"
              icon={<Shield className="w-9 h-9 text-cyan-400" />}
              gradient="border-cyan-400/40 hover:border-cyan-300/60"
            >
              <p>
                The digital landscape is flooded with synthetic content and manufactured consensus. Arc Codex works tirelessly to <strong>verify, validate, and challenge</strong> every piece of information you see.
              </p>
              <p>
                The A.R.C. framework applies Chimera scoring, objectivity analysis, and Socratic counter-dialogue to every article — stripping away the noise and leaving you with the <strong>signal that actually matters</strong>.
              </p>
              <blockquote className="mt-6 p-6 bg-slate-800/40 rounded-2xl border border-slate-700/50 italic text-blue-200 not-italic">
                &ldquo;Our technology doesn&apos;t just process information — it defends the human element in information.&rdquo;
              </blockquote>
            </Section>

            {/* FUTURE */}
            <Section
              id="future"
              title="Possibilities Without Borders"
              icon={<Zap className="w-9 h-9 text-amber-400" />}
              gradient="border-amber-400/40 hover:border-amber-300/60"
            >
              <p>
                We are entering a new era of <strong>Human-AI Collaboration</strong>. Arc Codex is the infrastructure for that future — whether you are building a boutique brand, leading a community movement, or researching the next breakthrough.
              </p>
              <ul className="space-y-4 mt-6" aria-label="Future capabilities">
                <li className="flex gap-4 items-start">
                  <div className="mt-1.5 h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_10px_rgba(96,165,250,0.8)] flex-shrink-0" aria-hidden="true" />
                  <span><strong>Hyper-Personalized Intelligence:</strong> Tailored feeds scored and ranked to your specific mission and interests.</span>
                </li>
                <li className="flex gap-4 items-start">
                  <div className="mt-1.5 h-2 w-2 rounded-full bg-indigo-400 shadow-[0_0_10px_rgba(129,140,248,0.8)] flex-shrink-0" aria-hidden="true" />
                  <span><strong>Instant Global Publishing:</strong> From ingestion to LinkedIn post in under a minute — the full pipeline, automated.</span>
                </li>
                <li className="flex gap-4 items-start">
                  <div className="mt-1.5 h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.8)] flex-shrink-0" aria-hidden="true" />
                  <span><strong>Trust by Default:</strong> Built-in adversarial analysis ensures your audience knows the content is rigorous, not reactive.</span>
                </li>
              </ul>
            </Section>

            {/* CTA */}
            <motion.div
              className="relative overflow-hidden bg-gradient-to-br from-blue-600/20 via-indigo-600/10 to-transparent border border-blue-400/30 rounded-3xl p-12 text-center"
              initial={{ opacity: 0, scale: 0.98 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
            >
              <div className="absolute top-0 left-0 w-64 h-64 bg-blue-500/10 rounded-full blur-[80px] -translate-x-1/2 -translate-y-1/2" aria-hidden="true" />
              <div className="absolute bottom-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-[80px] translate-x-1/2 translate-y-1/2" aria-hidden="true" />

              <div className="relative z-10 space-y-8">
                <div className="space-y-4">
                  <h2 className="text-3xl md:text-4xl font-bold text-slate-50 font-sans tracking-tight">
                    Stop Reacting. Start Innovating.
                  </h2>
                  <p className="text-xl text-slate-300 font-sans max-w-2xl mx-auto leading-relaxed">
                    Join a growing community of independent thinkers using the A.R.C. Framework to reclaim their attention and amplify their impact.
                  </p>
                </div>

                <div className="flex flex-wrap gap-5 justify-center">
                  <a
                    href="/about"
                    aria-label="Learn more about Arc Codex"
                    className="group flex items-center gap-2 px-10 py-5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-2xl shadow-[0_0_20px_rgba(37,99,235,0.4)] hover:shadow-[0_0_40px_rgba(37,99,235,0.6)] transition-all duration-300 text-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60"
                  >
                    Explore Arc Codex <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
                  </a>
                  <a
                    href="mailto:ross@arc-codex.com"
                    aria-label="Email ross@arc-codex.com"
                    className="flex items-center gap-2 px-10 py-5 bg-slate-800/80 hover:bg-slate-700 text-slate-200 font-bold rounded-2xl border border-slate-600/50 transition-all duration-300 text-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/60"
                  >
                    ross@arc-codex.com
                  </a>
                </div>
              </div>
            </motion.div>

            {/* FOOTER */}
            <footer className="text-center text-sm text-slate-500 pt-8 pb-4 border-t border-slate-800/50">
              <p className="font-sans tracking-wide">
                © {new Date().getFullYear()} Arc Codex — Empowering the next generation of independent thinkers.
              </p>
            </footer>

          </div>
        </div>
      </main>
    </PageWrapper>
  );
};

export default SalesPage;
