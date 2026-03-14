// Filename: /frontend/app/about/contact/page.tsx
// Arc Codex Contact Page — Ross Nesbitt
// Updated: Mar 2026 — Ross Nesbitt branding, consulting focus

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Mail, Github, ExternalLink, Linkedin, Shield, Brain, Server, Lock } from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';

const expertise = [
  {
    icon: <Brain className="h-5 w-5" aria-hidden="true" />,
    label: 'Cognitive Security',
    description: 'Creator of the A.R.C. framework — 48 cognitive anti-patterns for detecting manipulation, disinformation, and adversarial narratives at scale.',
  },
  {
    icon: <Lock className="h-5 w-5" aria-hidden="true" />,
    label: 'Email Authentication',
    description: 'SPF, DKIM, DMARC, BIMI architecture and deployment. Self-hosted MTA hardening, PTR alignment, and deliverability forensics.',
  },
  {
    icon: <Server className="h-5 w-5" aria-hidden="true" />,
    label: 'AI Infrastructure',
    description: 'Agentic LLM pipelines, Ollama/local inference, Redis-backed orchestration, ensemble architectures. Production systems on bare metal.',
  },
  {
    icon: <Shield className="h-5 w-5" aria-hidden="true" />,
    label: 'Systems Architecture',
    description: '30+ years Linux/UNIX. IAM, entitlement automation, OpenShift CI/CD. Former Proofpoint (employee #10), Wells Fargo, Morgan Stanley, J.P. Morgan Chase.',
  },
];

export default function ContactPage() {
  return (
    <PageWrapper>
      <div className="max-w-2xl mx-auto px-4 py-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="space-y-12"
        >
          {/* Header */}
          <header className="space-y-4 text-center">
            <h1 className="text-3xl font-bold text-slate-100 tracking-tight">Contact</h1>
            <p className="text-slate-400 text-base leading-relaxed">
              Arc Codex is built and maintained by{' '}
              <span className="text-slate-200 font-medium">Ross Nesbitt</span> —
              independent AI infrastructure engineer, systems architect, and creator of the
              A.R.C. cognitive security framework.<br className="hidden sm:block" />
              Available for contract engagements.
            </p>
          </header>

          {/* Expertise grid */}
          <section aria-label="Areas of expertise">
            <h2 className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-4 text-center">
              Consulting Expertise
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {expertise.map((item) => (
                <div
                  key={item.label}
                  className="flex gap-3 p-4 bg-slate-800/40 border border-slate-700/40 rounded-xl"
                >
                  <div className="text-amber-400 mt-0.5 shrink-0">{item.icon}</div>
                  <div>
                    <div className="text-sm font-medium text-slate-200 mb-1">{item.label}</div>
                    <div className="text-xs text-slate-500 leading-relaxed">{item.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Contact cards */}
          <section>
            <h2 className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-4 text-center">
              Get in Touch
            </h2>
            <div
              role="list"
              aria-label="Contact methods"
              className="flex flex-col sm:flex-row gap-4 justify-center"
            >
              {/* Email */}
              <a
                role="listitem"
                href="mailto:ross@arc-codex.com"
                aria-label="Send email to ross@arc-codex.com"
                className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
              >
                <Mail className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" aria-hidden="true" />
                <div className="text-left">
                  <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">Email</div>
                  <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                    ross@arc-codex.com
                  </div>
                </div>
              </a>

              {/* LinkedIn */}
              <a
                role="listitem"
                href="https://www.linkedin.com/in/arc-codex"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Ross Nesbitt on LinkedIn (opens in new tab)"
                className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
              >
                <Linkedin className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" aria-hidden="true" />
                <div className="text-left flex-1">
                  <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">LinkedIn</div>
                  <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                    arc-codex
                  </div>
                </div>
                <ExternalLink className="h-3.5 w-3.5 text-slate-600 group-hover:text-amber-400/60 transition-colors" aria-hidden="true" />
              </a>

              {/* GitHub */}
              <a
                role="listitem"
                href="https://github.com/hapnesbitt"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="hapnesbitt on GitHub (opens in new tab)"
                className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
              >
                <Github className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" aria-hidden="true" />
                <div className="text-left flex-1">
                  <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">GitHub</div>
                  <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                    hapnesbitt
                  </div>
                </div>
                <ExternalLink className="h-3.5 w-3.5 text-slate-600 group-hover:text-amber-400/60 transition-colors" aria-hidden="true" />
              </a>
            </div>
          </section>

          {/* Footer note */}
          <footer className="text-center">
            <p className="text-xs text-slate-600">
              © {new Date().getFullYear()} Arc Codex — Ross Nesbitt
            </p>
          </footer>
        </motion.div>
      </div>
    </PageWrapper>
  );
}
