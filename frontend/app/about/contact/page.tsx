// Filename: /frontend/app/about/contact/page.tsx
// Arc Codex Contact Page — Founder contact
// Updated: Mar 7, 2026 — LinkedIn added, ARIA pass, Hap Nesbitt branding

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Mail, Github, ExternalLink, Linkedin } from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';

export default function ContactPage() {
  return (
    <PageWrapper>
      <div className="max-w-2xl mx-auto px-4 py-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="space-y-12 text-center"
        >
          {/* Header */}
          <header className="space-y-4">
            <h1 className="text-3xl font-bold text-slate-100 tracking-tight">Contact</h1>
            <p className="text-slate-400 text-base leading-relaxed">
              Arc Codex is built and maintained by <span className="text-slate-200 font-medium">Hap Nesbitt</span> —
              independent AI infrastructure engineer and systems architect.<br />
              Reach out via email, connect on LinkedIn, or explore the code on GitHub.
            </p>
          </header>

          {/* Contact cards */}
          <div
            role="list"
            aria-label="Contact methods"
            className="flex flex-col sm:flex-row gap-4 justify-center"
          >
            {/* Email */}
            <a
              role="listitem"
              href="mailto:hapnesbitt@outlook.com"
              aria-label="Send email to hapnesbitt@outlook.com"
              className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
            >
              <Mail className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" aria-hidden="true" />
              <div className="text-left">
                <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">Email</div>
                <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                  hapnesbitt@outlook.com
                </div>
              </div>
            </a>

            {/* LinkedIn */}
            <a
              role="listitem"
              href="https://www.linkedin.com/in/hap-e-nesbitt/"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Hap Nesbitt on LinkedIn (opens in new tab)"
              className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
            >
              <Linkedin className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" aria-hidden="true" />
              <div className="text-left flex-1">
                <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">LinkedIn</div>
                <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                  hap-e-nesbitt
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

          {/* Footer note */}
          <footer>
            <p className="text-xs text-slate-600">
              © {new Date().getFullYear()} Arc Codex — Hap Nesbitt
            </p>
          </footer>
        </motion.div>
      </div>
    </PageWrapper>
  );
}
