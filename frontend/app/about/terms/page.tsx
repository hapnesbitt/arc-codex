// Filename: /frontend/app/about/terms/page.tsx
// Terms of Service.
// Librarian aesthetic. Server component. Content preserved from the prior
// client-side page; only chrome and styling changed.

import React from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Terms of Service — Arc Codex',
  description: 'Community guidelines and terms of service for Arc Codex.',
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Terms of Service
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Community Guidelines
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            Guidelines for thoughtful discourse on Arc Codex.
          </p>
          <p className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Last Updated · March 7, 2026
          </p>
        </header>

        {/* Welcome */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Welcome to Arc Codex
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            By accessing Arc Codex, you agree to these Terms of Service, which ensure that our digital community stays respectful, creative, and informed.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Our platform is a hub for exploration, discussion, and discovery. Treat fellow users with civility and uphold a positive digital environment.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Our Commitment
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>A space for independent thinking and cognitive resilience.</li>
            <li>Civil discourse and bridge-building across perspectives.</li>
            <li>Protection from manipulation and disinformation.</li>
          </ul>
        </section>

        {/* Account and Use */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Account and Use
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Browsing is open to all. Optional sign-in via Google, GitHub, or LinkedIn enables publishing, commenting, and private workspaces. We never store passwords — all authentication is handled by your chosen OAuth provider.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            You are responsible for all activity on your account. If you believe your account has been compromised, revoke access via your OAuth provider immediately.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Prohibited Activities
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Posting spam, malware, or malicious code.</li>
            <li>Automated scraping or data harvesting without permission.</li>
            <li>Attempting to gain unauthorized access to accounts or systems.</li>
            <li>Violating intellectual property rights of others.</li>
            <li>Impersonating other users or entities.</li>
            <li>Using the platform for illegal activities.</li>
          </ul>
        </section>

        {/* Content Standards */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Content Standards
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Contributions to Arc Codex should be accurate, constructive, and non-inflammatory. We strive for a community where ideas flourish and misinformation is minimized.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Explicit or offensive material is strictly prohibited, and we reserve the right to remove content that fails to meet these standards.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Content Guidelines
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li><strong>Accuracy</strong> — strive for truthfulness and fact-based contributions.</li>
            <li><strong>Constructiveness</strong> — engage in good faith with a goal of understanding.</li>
            <li><strong>Civility</strong> — attack ideas, never people (A.R.C. Principle I).</li>
            <li><strong>Context</strong> — provide sufficient context for claims and arguments.</li>
          </ul>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Prohibited Content
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Hate speech, harassment, or targeted abuse.</li>
            <li>Explicit sexual content or violent imagery.</li>
            <li>Doxxing or sharing private information without consent.</li>
            <li>Deliberate misinformation or coordinated disinformation campaigns.</li>
          </ul>
        </section>

        {/* Intellectual Property */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Intellectual Property
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            All content remains the property of its original authors. By contributing, you grant Arc Codex a limited license to display and share it on the platform.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Do not copy, distribute, or modify content without proper permission.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Your Rights &amp; Our License
          </div>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <strong>You retain ownership</strong> of all content you submit to Arc Codex.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <strong>You grant us a license</strong> to display, distribute, and analyze your content through our A.R.C. framework for the purpose of operating the platform.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <strong>We respect attribution.</strong> Original sources and authors are credited whenever possible.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <strong>We never train on your content.</strong> Material you submit — including workspace documents, papers, and articles — is never used to train AI models, never sold, and never shared with third parties.
          </p>
        </section>

        {/* Private Workspaces */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Private Workspaces
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex offers private workspaces for authenticated users — designed for educators, students, researchers, and analysts who need to score and analyze documents outside the public feed.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Workspace Commitments
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li><strong>Private by default</strong> — workspace content is never publicly visible unless you explicitly choose to share it.</li>
            <li><strong>No model training</strong> — documents you upload are never used to train AI models.</li>
            <li><strong>No third-party sharing</strong> — your workspace data is never sold or shared.</li>
            <li><strong>Student work</strong> — papers and drafts uploaded by students are treated with the highest confidentiality.</li>
            <li><strong>Deletion</strong> — you may delete your workspace and all associated content at any time.</li>
          </ul>
          <p className="font-serif text-sm text-slate-300 italic leading-relaxed pt-2">
            Educational use: Arc Codex is a critical thinking tool, not a writing tool. It analyzes and scores — it does not generate, ghost-write, or complete assignments. Use of Arc Codex is consistent with academic integrity policies at most institutions.
          </p>
          <p className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Coming Soon · Workspaces launching in a future update
          </p>
        </section>

        {/* Disclaimer & Liability */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Disclaimer &amp; Liability
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Arc Codex provides content for educational and informational purposes only. We are not liable for losses or damages arising from use of the site or reliance on any content.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Users engage at their own risk, and should exercise critical thinking when interacting with the material.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            Important Disclaimers
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Content is provided &ldquo;as is&rdquo; without warranties of any kind.</li>
            <li>We are not responsible for third-party content linked from our platform.</li>
            <li>Our A.R.C. analysis is computational assistance, not professional advice.</li>
            <li>Users should independently verify information before making decisions.</li>
            <li>We are not liable for damages arising from use or inability to use the service.</li>
          </ul>
        </section>

        {/* Modifications */}
        <section className="py-10 border-b border-slate-800/60 space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Modifications to Terms
          </h2>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            We may update these Terms at any time to reflect legal, operational, or technological changes. Users are encouraged to review the Terms periodically.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Continued use of Arc Codex constitutes acceptance of the revised Terms.
          </p>
          <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            How Updates Work
          </div>
          <ul className="list-disc ml-6 space-y-2 font-serif text-base text-slate-200 leading-relaxed">
            <li>Material changes will be posted prominently on this page.</li>
            <li>The &ldquo;Last Updated&rdquo; date reflects the most recent revision.</li>
            <li>Continued use after changes indicates acceptance.</li>
            <li>If you disagree with changes, please discontinue use.</li>
          </ul>
        </section>

        {/* Contact */}
        <section className="py-10 border-b border-slate-800/60 text-center space-y-4">
          <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
            Contact &amp; Support
          </h2>
          <p className="font-serif text-base text-slate-300 italic leading-relaxed max-w-xl mx-auto">
            Questions or concerns about these Terms? We are committed to maintaining a safe, informative, and constructive environment for all Arc Codex users.
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
