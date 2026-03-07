// Filename: /frontend/app/about/privacy/page.tsx
// PRIVACY POLICY PAGE
'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { 
  Shield, Eye, Database, ExternalLink, Bell, Lock,
  FileText, Mail
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';

// Reusable Section component with smooth animations (matching about page)
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
    <div className="prose prose-invert prose-lg max-w-none text-slate-200 font-serif leading-relaxed space-y-5">
      {children}
    </div>
  </motion.div>
);

const PrivacyPage: React.FC = () => {
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
            <div className="p-4 rounded-2xl bg-gradient-to-br from-green-500/40 via-emerald-400/30 to-teal-500/40 backdrop-blur-2xl border border-green-400/60 shadow-[0_0_40px_rgba(34,197,94,0.5)] transition-all duration-500 hover:shadow-[0_0_50px_rgba(34,197,94,0.6)]">
              <Shield className="h-12 w-12 text-green-300 animate-pulse-slow" />
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-sans tracking-tight text-slate-50 drop-shadow-[0_0_10px_rgba(34,197,94,0.8)]">
              Privacy Policy
            </h1>
            <p className="text-xl md:text-2xl text-green-300/90 font-serif italic drop-shadow-sm leading-relaxed">
              Your Privacy. Our Commitment.
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              <Badge variant="outline" className="bg-green-600/20 text-green-300 border-green-500/30 font-serif text-sm">
                Last Updated: March 7, 2026
              </Badge>
            </div>
            <div className="w-24 h-1 bg-gradient-to-r from-green-400 to-emerald-500 rounded-full animate-pulse"></div>
          </motion.div>

          {/* Commitment to Privacy */}
          <Section
            title="Commitment to Privacy"
            icon={<Lock className="w-8 h-8 text-green-400 group-hover:animate-pulse" />}
            gradient="border-green-400/50 hover:border-green-300/50"
          >
            <p>
              Arc Codex (the "Site") is committed to protecting your privacy. We are ad-free and
              collect the absolute minimum data needed to operate the service.
            </p>
            <div className="bg-green-900/10 border border-green-500/30 rounded-lg p-6 mt-6">
              <p className="text-green-300 font-semibold mb-3 text-lg">Our Core Privacy Principles:</p>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-3">
                  <Shield className="h-5 w-5 text-green-400 mt-1 flex-shrink-0" />
                  <span>Transparency in all data practices</span>
                </li>
                <li className="flex items-start gap-3">
                  <Eye className="h-5 w-5 text-green-400 mt-1 flex-shrink-0" />
                  <span>Minimal data collection by design</span>
                </li>
                <li className="flex items-start gap-3">
                  <Lock className="h-5 w-5 text-green-400 mt-1 flex-shrink-0" />
                  <span>Authentication via OAuth only — we never store your password</span>
                </li>
                <li className="flex items-start gap-3">
                  <Shield className="h-5 w-5 text-green-400 mt-1 flex-shrink-0" />
                  <span>Private by default — your submissions are yours until you choose to share</span>
                </li>
              </ul>
            </div>
          </Section>

          {/* What We Don't Collect */}
          <Section
            title="Information We Do Not Collect"
            icon={<Eye className="w-8 h-8 text-blue-400 group-hover:animate-pulse" />}
            gradient="border-blue-400/50 hover:border-blue-300/50"
          >
            <p>
              Arc Codex can be used anonymously for reading and browsing. Optional sign-in via Google, GitHub, or LinkedIn 
              enables publishing and private workspaces. We never store passwords — authentication is handled entirely by your 
              chosen provider via OAuth.
            </p>
            <div className="bg-blue-900/10 border border-blue-500/30 rounded-lg p-6 mt-6">
              <p className="text-blue-300 font-semibold mb-3">We Never Collect:</p>
              <ul className="space-y-2 text-slate-300 list-disc list-inside">
                <li>Names, email addresses, or contact information (unless you voluntarily provide it)</li>
                <li>Social security numbers or government IDs</li>
                <li>Financial information or payment details</li>
                <li>Passwords (we use OAuth only — Google, GitHub, LinkedIn sign-in)</li>
                <li>Personal browsing history across other websites</li>
              </ul>
            </div>
          </Section>

          {/* What We Do Collect */}
          <Section
            title="Information We Collect"
            icon={<Database className="w-8 h-8 text-amber-400 group-hover:animate-pulse" />}
            gradient="border-amber-400/50 hover:border-amber-300/50"
          >
            <p>
              Servers may log basic, non-personal data (IP address, browser type, pages visited) for performance monitoring, 
              security, and debugging. No third-party sharing occurs.
            </p>
            <div className="bg-amber-900/10 border border-amber-500/30 rounded-lg p-6 mt-6">
              <p className="text-amber-300 font-semibold mb-3">Technical Data We May Log:</p>
              <ul className="space-y-2 text-slate-300 list-disc list-inside">
                <li><strong>IP Address:</strong> Used for security and geographic traffic analysis</li>
                <li><strong>Browser Type:</strong> Helps optimize site compatibility</li>
                <li><strong>Pages Visited:</strong> Assists with content improvement and bug tracking</li>
                <li><strong>Timestamps:</strong> Used for debugging and performance monitoring</li>
              </ul>
              <div className="mt-4 p-4 bg-slate-800/30 rounded-lg">
                <p className="text-green-300 text-sm font-semibold mb-2">Privacy Protection:</p>
                <p className="text-slate-400 text-sm">
                  This technical data is never sold, shared with third parties, or used to identify individual users. 
                  It exists solely for operational purposes and security monitoring.
                </p>
              </div>
            </div>
          </Section>

          {/* Third-Party Services */}
          <Section
            title="Third-Party Services"
            icon={<ExternalLink className="w-8 h-8 text-purple-400 group-hover:animate-pulse" />}
            gradient="border-purple-400/50 hover:border-purple-300/50"
          >
            <p>
              Arc Codex is ad-free. We do not use Google AdSense, Google Ad Manager, or any
              advertising network. No advertising cookies are set by this site.
            </p>
            <div className="bg-purple-900/10 border border-purple-500/30 rounded-lg p-6 mt-6 space-y-4">
              <div>
                <p className="text-purple-300 font-semibold mb-2">What we do use:</p>
                <ul className="space-y-2 text-slate-300 text-sm list-disc list-inside">
                  <li><strong>Google OAuth</strong> — optional sign-in. Google may log authentication requests per their standard policies.</li>
                  <li><strong>GitHub OAuth</strong> — optional sign-in. GitHub may log authentication requests per their standard policies.</li>
                  <li><strong>LinkedIn OAuth</strong> — optional sign-in (coming soon). LinkedIn may log authentication requests per their standard policies.</li>
                  <li><strong>Google Fonts</strong> — Ubuntu font served via fonts.googleapis.com. Google may log this request per their standard infrastructure logging.</li>
                  <li><strong>External article links</strong> — clicking links takes you to third-party news sites with their own privacy policies.</li>
                </ul>
              </div>
              <div className="bg-slate-800/30 rounded-lg p-4">
                <p className="text-purple-300 text-sm font-semibold mb-2">No advertising. No trackers. No paywalls.</p>
                <p className="text-slate-400 text-sm">
                  Arc Codex does not sell advertising space, participate in ad networks, or use
                  behavioral tracking of any kind.
                </p>
              </div>
            </div>
          </Section>

          {/* Third-Party Links */}
          <Section
            title="Third-Party Links"
            icon={<ExternalLink className="w-8 h-8 text-cyan-400 group-hover:animate-pulse" />}
            gradient="border-cyan-400/50 hover:border-cyan-300/50"
          >
            <p>
              We may link to external sources. We are not responsible for their content or privacy practices. 
              Review third-party policies before interacting.
            </p>
            <div className="bg-cyan-900/10 border border-cyan-500/30 rounded-lg p-6 mt-6">
              <p className="text-cyan-300 font-semibold mb-3">Important Notice:</p>
              <p className="text-slate-300 text-sm">
                Arc Codex aggregates and links to news articles and external sources. When you click these links, 
                you leave our site and are subject to the privacy policies of those external websites. 
                We encourage you to review their privacy practices before sharing any personal information.
              </p>
            </div>
          </Section>

          {/* Education Workspaces — Coming Soon */}
          <Section
            title="Private Workspaces for Education"
            icon={<FileText className="w-8 h-8 text-emerald-400 group-hover:animate-pulse" />}
            gradient="border-emerald-400/50 hover:border-emerald-300/50"
          >
            <p>
              Arc Codex is building private workspaces designed for educators and students. 
              Authentication is required. Your workspace is yours alone until you choose to share it.
            </p>
            <div className="bg-emerald-900/10 border border-emerald-500/30 rounded-lg p-6 mt-6 space-y-5">
              <div>
                <p className="text-emerald-300 font-semibold mb-3 text-lg">For Teachers</p>
                <p className="text-slate-300 text-sm leading-relaxed">
                  Upload a folder of student papers. Every submission is scored across the same objective A.R.C. 
                  framework — argument structure, factual grounding, narrative coherence, and critical synthesis. 
                  See your whole class at a glance before you start reading. Arc doesn't replace your judgment — 
                  it gives you a map so your time goes where it matters most.
                </p>
              </div>
              <div>
                <p className="text-emerald-300 font-semibold mb-3 text-lg">For Students</p>
                <p className="text-slate-300 text-sm leading-relaxed">
                  Upload your draft before you turn it in. Not to get a grade — to see what a neutral reader 
                  extracts from it. Does your argument come through? Are your facts grounded? Does your narrative 
                  build to your conclusion, or does it drift? Arc shows you the gap between what you meant to say 
                  and what you wrote.
                </p>
              </div>
              <div className="bg-slate-800/40 rounded-lg p-4 border border-emerald-500/20">
                <p className="text-emerald-300 text-sm font-semibold mb-2">Our Commitment</p>
                <p className="text-slate-400 text-sm">
                  Arc Codex never writes for you. It reads like a rigorous peer who tells you the truth. 
                  Student work uploaded to a private workspace is never surfaced publicly, never used to 
                  train models, and never shared with any third party. Your workspace, your data.
                </p>
              </div>
              <div className="flex items-center gap-3 pt-2">
                <span className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/20 border border-emerald-400/40 rounded-full text-emerald-300 text-sm font-semibold">
                  🚧 Coming Soon — Sign in to be notified when workspaces launch
                </span>
              </div>
            </div>
          </Section>

          {/* Policy Updates */}
          <Section
            title="Policy Updates"
            icon={<Bell className="w-8 h-8 text-amber-400 group-hover:animate-pulse" />}
            gradient="border-amber-400/50 hover:border-amber-300/50"
          >
            <p>
              We may update this Privacy Policy to reflect legal, operational, or service changes. 
              Updates are posted with a new "Last Updated" date.
            </p>
            <div className="bg-amber-900/10 border border-amber-500/30 rounded-lg p-6 mt-6">
              <p className="text-amber-300 font-semibold mb-3">How We Notify You:</p>
              <ul className="space-y-2 text-slate-300 text-sm list-disc list-inside">
                <li>Material changes will be posted prominently on this page</li>
                <li>The "Last Updated" date at the top will reflect the most recent revision</li>
                <li>We recommend checking this page periodically for updates</li>
              </ul>
            </div>
          </Section>

          {/* Contact Section */}
          <motion.div 
            className="bg-gradient-to-br from-green-500/10 via-emerald-500/10 to-teal-500/10 border border-green-400/30 rounded-2xl p-8 text-center"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <Mail className="h-12 w-12 text-green-400 mx-auto mb-4" />
            <h3 className="text-2xl font-bold text-slate-50 mb-4 font-sans">
              Questions or Concerns?
            </h3>
            <p className="text-slate-300 font-serif mb-6 max-w-2xl mx-auto">
              If you have any questions about our privacy practices or need to discuss privacy concerns, 
              we're here to help.
            </p>
            <div className="flex gap-4 justify-center flex-wrap">
              <Link 
                href="/about/contact"
                className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-slate-900 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-serif"
              >
                <Mail className="h-5 w-5" />
                Contact Us
              </Link>
              <a 
                href="mailto:ross@arc-codex.com"
                className="inline-flex items-center gap-2 px-8 py-4 bg-slate-800/50 hover:bg-slate-800/70 border-2 border-green-400/50 hover:border-green-300 text-green-300 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-serif"
              >
                <Mail className="h-5 w-5" />
                ross@arc-codex.com
              </a>
            </div>
          </motion.div>

          {/* Footer */}
          <footer className="text-center text-sm text-slate-400 pt-8 pb-4 border-t border-slate-700/50">
            <p className="font-serif">
              © {new Date().getFullYear()} Arc Codex. {' '}
              <a 
                href="https://github.com/hapnesbitt" 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-green-300/90 hover:text-green-200 transition-colors duration-300"
              >
                GitHub
              </a>.
            </p>
          </footer>

        </div>
      </div>
    </PageWrapper>
  );
};

export default PrivacyPage;
