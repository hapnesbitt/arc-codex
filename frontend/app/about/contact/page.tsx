// Filename: /frontend/app/about/contact/page.tsx
// Arc Codex Contact Page — Simple founder contact

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Mail, Github, ExternalLink } from 'lucide-react';
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
          <div className="space-y-4">
            <h1 className="text-3xl font-bold text-slate-100 tracking-tight">Contact</h1>
            <p className="text-slate-400 text-base leading-relaxed">
              Arc Codex is built and maintained by its founder.<br />
              Reach out via email or explore the code on GitHub.
            </p>
          </div>

          {/* Contact cards */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="mailto:ross@arc-codex.com"
              className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80"
            >
              <Mail className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" />
              <div className="text-left">
                <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">Email</div>
                <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                  ross@arc-codex.com
                </div>
              </div>
            </a>

            <a
              href="https://github.com/hapnesbitt"
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center gap-3 px-6 py-4 bg-slate-800/50 border border-slate-700/50 hover:border-amber-500/40 rounded-xl transition-all duration-200 hover:bg-slate-800/80"
            >
              <Github className="h-5 w-5 text-slate-400 group-hover:text-amber-400 transition-colors" />
              <div className="text-left flex-1">
                <div className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-0.5">GitHub</div>
                <div className="text-sm text-slate-200 font-mono group-hover:text-amber-300 transition-colors">
                  github.com/hapnesbitt
                </div>
              </div>
              <ExternalLink className="h-3.5 w-3.5 text-slate-600 group-hover:text-amber-400/60 transition-colors" />
            </a>
          </div>

          {/* Footer note */}
          <p className="text-xs text-slate-600">
            © {new Date().getFullYear()} Arc Codex
          </p>
        </motion.div>
      </div>
    </PageWrapper>
  );
}
