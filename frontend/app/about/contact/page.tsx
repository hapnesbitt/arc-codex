// Filename: /frontend/app/about/contact/page.tsx
// Arc Codex Contact Page — Hap Nesbitt
// v2.0 Mar 15 2026 — Full visual redesign

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Mail, Github, ExternalLink, Linkedin, Shield, Brain, Server, Lock, ArrowRight } from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';

const expertise = [
  {
    icon: <Brain className="h-5 w-5" aria-hidden="true" />,
    label: 'Cognitive Security',
    accent: 'from-purple-500/20 to-purple-600/5 border-purple-500/20 hover:border-purple-400/40',
    iconColor: 'text-purple-400',
    description: 'Creator of the A.R.C. framework — 48 cognitive anti-patterns for detecting manipulation, disinformation, and adversarial narratives at scale.',
  },
  {
    icon: <Lock className="h-5 w-5" aria-hidden="true" />,
    label: 'Email Authentication',
    accent: 'from-amber-500/20 to-amber-600/5 border-amber-500/20 hover:border-amber-400/40',
    iconColor: 'text-amber-400',
    description: 'SPF, DKIM, DMARC, BIMI architecture and deployment. Self-hosted MTA hardening, PTR alignment, and deliverability forensics.',
  },
  {
    icon: <Server className="h-5 w-5" aria-hidden="true" />,
    label: 'AI Infrastructure',
    accent: 'from-blue-500/20 to-blue-600/5 border-blue-500/20 hover:border-blue-400/40',
    iconColor: 'text-blue-400',
    description: 'Agentic LLM pipelines, Ollama/local inference, Redis-backed orchestration, ensemble architectures. Production systems on bare metal.',
  },
  {
    icon: <Shield className="h-5 w-5" aria-hidden="true" />,
    label: 'Systems Architecture',
    accent: 'from-green-500/20 to-green-600/5 border-green-500/20 hover:border-green-400/40',
    iconColor: 'text-green-400',
    description: '30+ years Linux/UNIX. IAM, entitlement automation, OpenShift CI/CD. Former Proofpoint (employee #10), Wells Fargo, Morgan Stanley, J.P. Morgan Chase.',
  },
];

const contacts = [
  {
    icon: <Mail className="h-5 w-5" aria-hidden="true" />,
    label: 'Email',
    value: 'hap@arc-codex.com',
    href: 'mailto:hap@arc-codex.com',
    aria: 'Send email to hap@arc-codex.com',
    external: false,
    accent: 'hover:border-amber-500/40 hover:shadow-[0_0_20px_rgba(245,158,11,0.15)]',
    iconHover: 'group-hover:text-amber-400',
    valueHover: 'group-hover:text-amber-300',
  },
  {
    icon: <Linkedin className="h-5 w-5" aria-hidden="true" />,
    label: 'LinkedIn',
    value: 'arccodexsupport',
    href: 'https://www.linkedin.com/in/arccodexsupport/',
    aria: 'Hap Nesbitt on LinkedIn (opens in new tab)',
    external: true,
    accent: 'hover:border-blue-500/40 hover:shadow-[0_0_20px_rgba(59,130,246,0.15)]',
    iconHover: 'group-hover:text-blue-400',
    valueHover: 'group-hover:text-blue-300',
  },
  {
    icon: <Github className="h-5 w-5" aria-hidden="true" />,
    label: 'GitHub',
    value: 'hapnesbitt',
    href: 'https://github.com/hapnesbitt',
    aria: 'hapnesbitt on GitHub (opens in new tab)',
    external: true,
    accent: 'hover:border-slate-400/40 hover:shadow-[0_0_20px_rgba(148,163,184,0.15)]',
    iconHover: 'group-hover:text-slate-300',
    valueHover: 'group-hover:text-slate-200',
  },
];

export default function ContactPage() {
  return (
    <PageWrapper>
      <a
        href="#contact-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
      >
        Skip to main content
      </a>

      <main id="contact-main" className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="space-y-16">

          {/* Hero */}
          <motion.header
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="relative"
          >
            {/* Ambient glow */}
            <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-96 h-48 bg-amber-500/10 rounded-full blur-[80px] pointer-events-none" aria-hidden="true" />

            <div className="relative text-center space-y-6">
              {/* Monogram */}
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.1 }}
                className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-amber-500/30 via-amber-400/20 to-orange-500/30 border border-amber-400/40 shadow-[0_0_40px_rgba(251,191,36,0.3)] text-3xl font-black text-amber-300 select-none"
                aria-hidden="true"
              >
                HN
              </motion.div>

              <div className="space-y-3">
                <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-slate-50">
                  Hap Nesbitt
                </h1>
                <p className="text-lg text-amber-300/80 font-light italic">
                  Independent AI Infrastructure Engineer &amp; Systems Architect
                </p>
                <p className="text-slate-400 text-base leading-relaxed max-w-xl mx-auto">
                  Builder of Arc Codex and the A.R.C. cognitive security framework.
                  Available for contract engagements.
                </p>
              </div>

              {/* Decorative divider */}
              <div className="flex items-center justify-center gap-4" aria-hidden="true">
                <div className="h-px w-16 bg-gradient-to-r from-transparent to-amber-500/40" />
                <div className="h-1.5 w-1.5 rounded-full bg-amber-500/60" />
                <div className="h-px w-16 bg-gradient-to-l from-transparent to-amber-500/40" />
              </div>
            </div>
          </motion.header>

          {/* Expertise grid */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            aria-label="Consulting expertise"
          >
            <h2 className="text-xs text-slate-500 font-medium uppercase tracking-widest mb-6 text-center">
              Consulting Expertise
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {expertise.map((item, i) => (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: i * 0.07 }}
                  className={`flex gap-4 p-5 bg-gradient-to-br ${item.accent} border rounded-2xl transition-all duration-300 group`}
                >
                  <div className={`${item.iconColor} mt-0.5 shrink-0 transition-transform duration-300 group-hover:scale-110`}>
                    {item.icon}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-200 mb-1.5">{item.label}</div>
                    <div className="text-xs text-slate-500 leading-relaxed">{item.description}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.section>

          {/* Contact methods */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            <h2 className="text-xs text-slate-500 font-medium uppercase tracking-widest mb-6 text-center">
              Get in Touch
            </h2>
            <div role="list" aria-label="Contact methods" className="space-y-3">
              {contacts.map((c, i) => (
                <motion.a
                  key={c.label}
                  role="listitem"
                  href={c.href}
                  target={c.external ? '_blank' : undefined}
                  rel={c.external ? 'noopener noreferrer' : undefined}
                  aria-label={c.aria}
                  initial={{ opacity: 0, x: -16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: i * 0.08 }}
                  className={`group flex items-center gap-4 px-6 py-4 bg-slate-900/50 border border-slate-700/40 rounded-2xl transition-all duration-300 ${c.accent} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60`}
                >
                  <div className={`text-slate-500 transition-colors duration-200 ${c.iconHover}`}>
                    {c.icon}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs text-slate-600 font-medium uppercase tracking-widest mb-0.5">{c.label}</div>
                    <div className={`text-sm text-slate-300 font-mono transition-colors duration-200 ${c.valueHover}`}>
                      {c.value}
                    </div>
                  </div>
                  {c.external
                    ? <ExternalLink className="h-3.5 w-3.5 text-slate-700 group-hover:text-slate-400 transition-colors" aria-hidden="true" />
                    : <ArrowRight className="h-4 w-4 text-slate-700 group-hover:text-amber-400 group-hover:translate-x-1 transition-all duration-200" aria-hidden="true" />
                  }
                </motion.a>
              ))}
            </div>
          </motion.section>

          {/* Arc Codex link */}
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="relative overflow-hidden rounded-2xl border border-amber-400/20 bg-gradient-to-br from-amber-500/10 via-slate-900/40 to-transparent p-8 text-center"
          >
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06),transparent_70%)]" aria-hidden="true" />
            <div className="relative space-y-3">
              <p className="text-slate-400 text-sm">See the work in action</p>
              <a
                href="/"
                className="group inline-flex items-center gap-2 text-amber-300 font-semibold hover:text-amber-200 transition-colors focus-visible:outline-none focus-visible:underline focus-visible:underline-offset-4"
                aria-label="Go to Arc Codex intelligence feed"
              >
                Arc Codex Intelligence Feed
                <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
              </a>
            </div>
          </motion.div>

          {/* Footer */}
          <footer className="text-center">
            <p className="text-xs text-slate-700 font-mono tracking-widest uppercase">
              © {new Date().getFullYear()} Arc Codex — Hap Nesbitt
            </p>
          </footer>

        </div>
      </main>
    </PageWrapper>
  );
}
