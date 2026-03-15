// Filename: /frontend/app/about/sales/page.tsx
// Arc Codex — Vision, Mission & Platform
// v2.0 Mar 15 2026 — Updated with Huntaegis success story, Docker deployment, source count

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
  Shield, Target, Zap,
  Sparkles, Globe, Rocket, Users, Lightbulb,
  ArrowRight, Server, Package, ExternalLink,
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
                  Intelligence infrastructure for individuals, researchers, and specialized platforms.
                </p>
              </div>

              <div className="flex flex-wrap gap-3 justify-center" role="list" aria-label="Core values">
                <Badge role="listitem" variant="outline" className="bg-blue-600/20 text-blue-300 border-blue-500/40 px-4 py-1 text-sm">
                  2,087 Sources
                </Badge>
                <Badge role="listitem" variant="outline" className="bg-indigo-600/20 text-indigo-300 border-indigo-500/40 px-4 py-1 text-sm">
                  162 Languages
                </Badge>
                <Badge role="listitem" variant="outline" className="bg-cyan-600/20 text-cyan-300 border-cyan-500/40 px-4 py-1 text-sm">
                  48 A.R.C. Patterns
                </Badge>
                <Badge role="listitem" variant="outline" className="bg-green-600/20 text-green-300 border-green-500/40 px-4 py-1 text-sm">
                  Docker-Ready
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

            {/* HOW IT WORKS */}
            <Section
              id="how"
              title="How It Works"
              icon={<Zap className="w-9 h-9 text-amber-400" />}
              gradient="border-amber-400/40 hover:border-amber-300/60"
            >
              <p>
                Arc Codex monitors over <strong>2,004 RSS sources</strong> across 162 languages in real time. Every article is automatically fetched, scored for objectivity, and run through three independent AI analytical passes:
              </p>
              <div className="grid md:grid-cols-3 gap-4 mt-4" role="list" aria-label="Analysis pipeline">
                <div role="listitem" className="bg-red-900/10 border border-red-500/20 p-4 rounded-xl">
                  <p className="font-bold text-red-300 mb-1">🎯 Facts Only</p>
                  <p className="text-sm text-slate-300">Verifiable facts only. Who, what, when, where. No interpretation.</p>
                </div>
                <div role="listitem" className="bg-blue-900/10 border border-blue-500/20 p-4 rounded-xl">
                  <p className="font-bold text-blue-300 mb-1">🔵 Executive Summary</p>
                  <p className="text-sm text-slate-300">Balanced journalist-style summary for educated readers.</p>
                </div>
                <div role="listitem" className="bg-purple-900/10 border border-purple-500/20 p-4 rounded-xl">
                  <p className="font-bold text-purple-300 mb-1">🟣 Full Take</p>
                  <p className="text-sm text-slate-300">Deep cognitive analysis: steelman, 48 A.R.C. anti-patterns, root cause, implications.</p>
                </div>
              </div>
              <p className="mt-4">
                Every article also gets a <strong>Sentinel forensic pass</strong> for AI-generated content detection, a <strong>Counter-Analyst adversarial comment</strong>, and a <strong>Chimera objectivity score</strong>. Translation into any of 162 languages is one click away.
              </p>
            </Section>

            {/* SUCCESS STORY */}
            <Section
              id="huntaegis"
              title="Success Story: Huntaegis"
              icon={<Shield className="w-9 h-9 text-green-400" />}
              gradient="border-green-400/40 hover:border-green-300/60"
            >
              <p>
                <a
                  href="https://huntaegis.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-green-400 hover:text-green-300 font-bold underline underline-offset-4"
                >
                  Huntaegis.com
                </a>
                {' '}is a purpose-built cybersecurity intelligence platform deployed on the Arc Codex engine — fully customized for a professional penetration tester.
              </p>
              <p>
                Where Arc Codex monitors general world news, Huntaegis is focused exclusively on threat intelligence: active ransomware campaigns, critical CVEs, state-sponsored cyber operations, DFIR developments, and law enforcement cybercrime actions. It ingests from 51 security-specialist sources including Krebs on Security, Google Project Zero, CISA, Mandiant, Unit 42, and Cisco Talos.
              </p>
              <p>
                The same A.R.C. cognitive analysis engine runs on every threat report — giving security professionals not just the news, but the <em>angle</em>, the <em>context</em>, and the <em>counter-argument</em>. A dedicated terminal aesthetic makes it feel at home in a SOC environment.
              </p>
              <div className="flex justify-start mt-4">
                <a
                  href="https://huntaegis.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="Visit Huntaegis (opens in new tab)"
                  className="group flex items-center gap-2 px-6 py-3 bg-green-600/20 border border-green-500/40 hover:bg-green-600/30 text-green-300 font-bold rounded-xl transition-all duration-200 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-400/60"
                >
                  Visit Huntaegis <ExternalLink className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
                </a>
              </div>
            </Section>

            {/* DEPLOYMENT */}
            <Section
              id="deployment"
              title="Deploy Your Own"
              icon={<Package className="w-9 h-9 text-indigo-400" />}
              gradient="border-indigo-400/40 hover:border-indigo-300/60"
            >
              <p>
                Arc Codex is available as a Docker-based deployment. The full stack — Flask API, Next.js frontend, Redis, Apache Solr, and all background workers — ships as a single <code className="font-mono text-xs bg-slate-800/60 border border-white/10 rounded px-1.5 py-0.5 text-amber-300/90">docker-compose.yml</code>. AI inference runs locally via Ollama, keeping your data on your hardware.
              </p>
              <div className="grid md:grid-cols-2 gap-4 mt-4" role="list" aria-label="Deployment options">
                <div role="listitem" className="bg-indigo-900/10 border border-indigo-500/20 p-5 rounded-xl">
                  <Server className="h-6 w-6 text-indigo-400 mb-3" aria-hidden="true" />
                  <h3 className="font-bold text-white mb-2">Self-Hosted</h3>
                  <p className="text-sm text-slate-300">Run on your own hardware — a single workstation or server is sufficient. All inference stays local, zero cloud dependency.</p>
                </div>
                <div role="listitem" className="bg-blue-900/10 border border-blue-500/20 p-5 rounded-xl">
                  <Lightbulb className="h-6 w-6 text-blue-400 mb-3" aria-hidden="true" />
                  <h3 className="font-bold text-white mb-2">Customized for Your Domain</h3>
                  <p className="text-sm text-slate-300">Swap sources, directives, branding, and color scheme. Huntaegis went from Arc Codex to a fully branded security platform in a single session.</p>
                </div>
              </div>
              <p className="mt-4">
                Interested in a custom deployment? Reach out — Arc Codex has been deployed for general news intelligence, cybersecurity operations, and domain-specific research platforms.
              </p>
            </Section>

            {/* INTEGRITY */}
            <Section
              id="integrity"
              title="Information Integrity by Design"
              icon={<Shield className="w-9 h-9 text-cyan-400" />}
              gradient="border-cyan-400/40 hover:border-cyan-300/60"
            >
              <p>
                The digital landscape is flooded with synthetic content and manufactured consensus. Arc Codex works tirelessly to <strong>verify, validate, and challenge</strong> every piece of information you see.
              </p>
              <p>
                The A.R.C. framework applies Chimera scoring, objectivity analysis, and Socratic counter-dialogue to every article — stripping away the noise and leaving you with the <strong>signal that actually matters</strong>. No ads, no tracking, no paywalls.
              </p>
              <blockquote className="mt-6 p-6 bg-slate-800/40 rounded-2xl border border-slate-700/50 italic text-blue-200 not-italic">
                &ldquo;Our technology doesn&apos;t just process information — it defends the human element in information.&rdquo;
              </blockquote>
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
                    Stop Reacting. Start Analysing.
                  </h2>
                  <p className="text-xl text-slate-300 font-sans max-w-2xl mx-auto leading-relaxed">
                    Read the feed, deploy your own instance, or reach out to discuss a custom platform.
                  </p>
                </div>

                <div className="flex flex-wrap gap-5 justify-center">
                  <a
                    href="/about/support"
                    aria-label="Read the how-to guide"
                    className="group flex items-center gap-2 px-10 py-5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-2xl shadow-[0_0_20px_rgba(37,99,235,0.4)] hover:shadow-[0_0_40px_rgba(37,99,235,0.6)] transition-all duration-300 text-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60"
                  >
                    How to Use Arc Codex <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
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
                © {new Date().getFullYear()} Arc Codex — Intelligence infrastructure for the independent mind.
              </p>
            </footer>

          </div>
        </div>
      </main>
    </PageWrapper>
  );
};

export default SalesPage;
