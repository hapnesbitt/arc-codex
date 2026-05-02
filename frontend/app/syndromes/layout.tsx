/**
 * Syndromes section layout.
 * Wraps every /syndromes/* page in the Arc dark shell and adds a
 * lightweight breadcrumb nav.  Individual pages own their own <h1>
 * and any deeper breadcrumb segment — this layout only knows "Syndromes".
 */

import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { ChevronRight, Home } from 'lucide-react';

export const metadata: Metadata = {
  title: {
    template: '%s | Syndromes | Arc Codex',
    default:  'Syndromes | Arc Codex',
  },
  description:
    'Condition-specific intelligence units — curated reading, video, and self-assessment for each syndrome covered by Arc Codex.',
};

export default function SyndromesLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-slate-50 font-sans">
      {/* Subtle ambient glows — matches PageWrapper */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-purple-500/8 rounded-full blur-3xl" />
      </div>

      {/* Breadcrumb strip */}
      <nav
        aria-label="Breadcrumb"
        className="relative z-10 border-b border-white/5 bg-slate-900/60 backdrop-blur-sm"
      >
        <ol className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 h-10 flex items-center gap-1 text-sm text-slate-500">
          <li>
            <Link
              href="/"
              className="inline-flex items-center gap-1 hover:text-slate-300 transition-colors
                         focus-visible:outline-none focus-visible:text-amber-400"
              aria-label="Arc Codex home"
            >
              <Home className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Arc Codex</span>
            </Link>
          </li>
          <li aria-hidden="true"><ChevronRight className="h-3.5 w-3.5" /></li>
          <li>
            <Link
              href="/syndromes"
              className="hover:text-slate-300 transition-colors
                         focus-visible:outline-none focus-visible:text-amber-400"
            >
              Syndromes
            </Link>
          </li>
          {/* Individual pages may render a deeper crumb via their own heading;
              this layout intentionally stops at "Syndromes" */}
        </ol>
      </nav>

      {/* Page content */}
      <main
        id="syndrome-main"
        className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 pb-20"
      >
        {children}
      </main>

      <footer className="relative z-10 border-t border-white/5 py-5 text-center text-xs text-slate-600">
        <Link
          href="https://soc.arc-codex.com"
          className="hover:text-slate-400 transition-colors focus-visible:outline-none focus-visible:text-amber-400"
          aria-label="School of Chat — AI-graded compliance and certification practice"
        >
          School of Chat
        </Link>
        <span className="mx-2" aria-hidden="true">·</span>
        <Link
          href="/"
          className="hover:text-slate-400 transition-colors focus-visible:outline-none focus-visible:text-amber-400"
        >
          Arc Codex
        </Link>
      </footer>
    </div>
  );
}
