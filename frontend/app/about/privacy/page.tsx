// Filename: /frontend/app/about/privacy/page.tsx
// Privacy Policy.
// Librarian aesthetic. Server component. Content preserved verbatim from the
// prior client-side page; only chrome and styling changed.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Privacy Policy — Arc Codex',
  description: 'How Arc Codex collects, uses, and protects your information.',
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Privacy Policy
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Your Privacy. Our Commitment.
          </h1>
          <p className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Last Updated · March 7, 2026
          </p>
        </header>

        {/* Commitment to Privacy */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Commitment to Privacy
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex (the &ldquo;Site&rdquo;) is committed to protecting your privacy. We are ad-free and collect the absolute minimum data needed to operate the service.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Our Core Privacy Principles
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Transparency in all data practices.</li>
            <li>Minimal data collection by design.</li>
            <li>Authentication via OAuth only — we never store your password.</li>
            <li>Private by default — your submissions are yours until you choose to share.</li>
          </ul>
        </section>

        {/* Information We Do Not Collect */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Information We Do Not Collect
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex can be used anonymously for reading and browsing. Optional sign-in via Google, GitHub, or LinkedIn enables publishing and private workspaces. We never store passwords — authentication is handled entirely by your chosen provider via OAuth.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            We Never Collect
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Names, email addresses, or contact information (unless you voluntarily provide it).</li>
            <li>Social security numbers or government IDs.</li>
            <li>Financial information or payment details.</li>
            <li>Passwords (we use OAuth only — Google, GitHub, LinkedIn sign-in).</li>
            <li>Personal browsing history across other websites.</li>
          </ul>
        </section>

        {/* Information We Collect */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Information We Collect
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Servers may log basic, non-personal data (IP address, browser type, pages visited) for performance monitoring, security, and debugging. No third-party sharing occurs.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Technical Data We May Log
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li><strong>IP Address</strong> — used for security and geographic traffic analysis.</li>
            <li><strong>Browser Type</strong> — helps optimize site compatibility.</li>
            <li><strong>Pages Visited</strong> — assists with content improvement and bug tracking.</li>
            <li><strong>Timestamps</strong> — used for debugging and performance monitoring.</li>
          </ul>
          <p className="font-serif text-sm text-slate-400 italic leading-relaxed pt-2">
            This technical data is never sold, shared with third parties, or used to identify individual users. It exists solely for operational purposes and security monitoring.
          </p>
        </section>

        {/* Third-Party Services */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Third-Party Services
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex is ad-free. We do not use Google AdSense, Google Ad Manager, or any advertising network. No advertising cookies are set by this site.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            What We Do Use
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li><strong>Google OAuth</strong> — optional sign-in. Google may log authentication requests per their standard policies.</li>
            <li><strong>GitHub OAuth</strong> — optional sign-in. GitHub may log authentication requests per their standard policies.</li>
            <li><strong>LinkedIn OAuth</strong> — optional sign-in (coming soon). LinkedIn may log authentication requests per their standard policies.</li>
            <li><strong>Google Fonts</strong> — Ubuntu font served via fonts.googleapis.com. Google may log this request per their standard infrastructure logging.</li>
            <li><strong>External article links</strong> — clicking links takes you to third-party news sites with their own privacy policies.</li>
          </ul>
          <p className="font-serif text-sm text-slate-300 italic leading-relaxed pt-2">
            No advertising. No trackers. No paywalls. Arc Codex does not sell advertising space, participate in ad networks, or use behavioral tracking of any kind.
          </p>
        </section>

        {/* Third-Party Links */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Third-Party Links
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            We may link to external sources. We are not responsible for their content or privacy practices. Review third-party policies before interacting.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex aggregates and links to news articles and external sources. When you click these links, you leave our site and are subject to the privacy policies of those external websites. We encourage you to review their privacy practices before sharing any personal information.
          </p>
        </section>

        {/* Private Workspaces */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Private Workspaces for Education
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex is building private workspaces designed for educators and students. Authentication is required. Your workspace is yours alone until you choose to share it.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">For Teachers</div>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Upload a folder of student papers. Every submission is scored across the same objective A.R.C. framework — argument structure, factual grounding, narrative coherence, and critical synthesis. See your whole class at a glance before you start reading. Arc doesn&apos;t replace your judgment — it gives you a map so your time goes where it matters most.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">For Students</div>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Upload your draft before you turn it in. Not to get a grade — to see what a neutral reader extracts from it. Does your argument come through? Are your facts grounded? Does your narrative build to your conclusion, or does it drift? Arc shows you the gap between what you meant to say and what you wrote.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">Our Commitment</div>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex never writes for you. It reads like a rigorous peer who tells you the truth. Student work uploaded to a private workspace is never surfaced publicly, never used to train models, and never shared with any third party. Your workspace, your data.
          </p>
          <p className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Coming Soon · Sign in to be notified when workspaces launch
          </p>
        </section>

        {/* Policy Updates */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Policy Updates
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            We may update this Privacy Policy to reflect legal, operational, or service changes. Updates are posted with a new &ldquo;Last Updated&rdquo; date.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            How We Notify You
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Material changes will be posted prominently on this page.</li>
            <li>The &ldquo;Last Updated&rdquo; date at the top will reflect the most recent revision.</li>
            <li>We recommend checking this page periodically for updates.</li>
          </ul>
        </section>

        {/* Contact */}
        <section className="py-10 border-b border-slate-800/60 text-center space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Questions or Concerns?
          </h2>
          <p className="font-serif text-base text-slate-300 italic leading-relaxed max-w-xl mx-auto">
            If you have any questions about our privacy practices or need to discuss privacy concerns, we&apos;re here to help.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <Link
              href="/about/contact"
              className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-slate-50 font-sans text-xs uppercase tracking-[0.25em] font-semibold rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-300"
            >
              Contact
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </Link>
            <a
              href="mailto:ross@arc-codex.com"
              className="inline-flex items-center gap-2 px-6 py-3 border border-slate-700 hover:border-slate-500 text-slate-300 hover:text-slate-100 font-sans text-xs uppercase tracking-[0.25em] rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40"
            >
              ross@arc-codex.com
            </a>
          </div>
        </section>

        {/* Footer — identifier block */}
        <footer className="text-center pt-12 pb-6 space-y-1 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-600">
          <p>Harold Edwin Ross Nesbitt III</p>
          <p>Fort Collins, CO · 40.5853° N, 105.0844° W</p>
          <p>A.R.C. Framework v7.14 · Connection Secure</p>
        </footer>
      </main>
    </div>
  );
}
