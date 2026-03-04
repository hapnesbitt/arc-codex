// Filename: /frontend/app/about/terms/page.tsx
// TERMS OF SERVICE PAGE
'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { 
  FileText, Shield, Users, Copyright, AlertTriangle, 
  RefreshCw, Mail, Scale, Heart, BookOpen
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

const TermsPage: React.FC = () => {
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
            <div className="p-4 rounded-2xl bg-gradient-to-br from-amber-500/40 via-orange-400/30 to-yellow-500/40 backdrop-blur-2xl border border-amber-400/60 shadow-[0_0_40px_rgba(251,191,36,0.5)] transition-all duration-500 hover:shadow-[0_0_50px_rgba(251,191,36,0.6)]">
              <Scale className="h-12 w-12 text-amber-300 animate-pulse-slow" />
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-sans tracking-tight text-slate-50 drop-shadow-[0_0_10px_rgba(251,191,36,0.8)]">
              Terms of Service
            </h1>
            <p className="text-xl md:text-2xl text-amber-300/90 font-serif italic drop-shadow-sm leading-relaxed">
              Community Guidelines for Thoughtful Discourse
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              <Badge variant="outline" className="bg-amber-600/20 text-amber-300 border-amber-500/30 font-serif text-sm">
                Last Updated: February 25, 2026
              </Badge>
            </div>
            <div className="w-24 h-1 bg-gradient-to-r from-amber-400 to-orange-500 rounded-full animate-pulse"></div>
          </motion.div>

          {/* Welcome */}
          <Section
            title="Welcome to Arc Codex"
            icon={<Heart className="w-8 h-8 text-amber-400 group-hover:animate-pulse" />}
            gradient="border-amber-400/50 hover:border-amber-300/50"
          >
            <p>
              By accessing Arc Codex, you agree to these Terms of Service, which ensure that our digital community 
              stays respectful, creative, and informed.
            </p>
            <p>
              Our platform is a hub for exploration, discussion, and discovery. Treat fellow users with civility 
              and uphold a positive digital environment.
            </p>
            <div className="bg-amber-900/10 border border-amber-500/30 rounded-lg p-6 mt-6">
              <p className="text-amber-300 font-semibold mb-3 text-lg">Our Commitment:</p>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-3">
                  <BookOpen className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" />
                  <span>A space for independent thinking and cognitive resilience</span>
                </li>
                <li className="flex items-start gap-3">
                  <Users className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" />
                  <span>Civil discourse and bridge-building across perspectives</span>
                </li>
                <li className="flex items-start gap-3">
                  <Shield className="h-5 w-5 text-amber-400 mt-1 flex-shrink-0" />
                  <span>Protection from manipulation and disinformation</span>
                </li>
              </ul>
            </div>
          </Section>

          {/* Account and Use */}
          <Section
            title="Account and Use"
            icon={<Users className="w-8 h-8 text-blue-400 group-hover:animate-pulse" />}
            gradient="border-blue-400/50 hover:border-blue-300/50"
          >
            <p>
              While browsing is open to all, registered accounts must follow ethical use. Do not post spam, malware, 
              or content that violates laws or intellectual property rights.
            </p>
            <p>
              You are responsible for safeguarding your credentials and for all activity on your account.
            </p>
            <div className="bg-blue-900/10 border border-blue-500/30 rounded-lg p-6 mt-6">
              <p className="text-blue-300 font-semibold mb-3">Prohibited Activities:</p>
              <ul className="space-y-2 text-slate-300 list-disc list-inside text-sm">
                <li>Posting spam, malware, or malicious code</li>
                <li>Automated scraping or data harvesting without permission</li>
                <li>Attempting to gain unauthorized access to accounts or systems</li>
                <li>Violating intellectual property rights of others</li>
                <li>Impersonating other users or entities</li>
                <li>Using the platform for illegal activities</li>
              </ul>
            </div>
          </Section>

          {/* Content Standards */}
          <Section
            title="Content Standards"
            icon={<FileText className="w-8 h-8 text-purple-400 group-hover:animate-pulse" />}
            gradient="border-purple-400/50 hover:border-purple-300/50"
          >
            <p>
              Contributions to Arc Codex should be accurate, constructive, and non-inflammatory. We strive for a 
              community where ideas flourish and misinformation is minimized.
            </p>
            <p>
              Explicit or offensive material is strictly prohibited, and we reserve the right to remove content 
              that fails to meet these standards.
            </p>
            <div className="bg-purple-900/10 border border-purple-500/30 rounded-lg p-6 mt-6 space-y-4">
              <div>
                <p className="text-purple-300 font-semibold mb-2">Content Guidelines:</p>
                <ul className="space-y-2 text-slate-300 text-sm list-disc list-inside">
                  <li><strong>Accuracy:</strong> Strive for truthfulness and fact-based contributions</li>
                  <li><strong>Constructiveness:</strong> Engage in good faith with a goal of understanding</li>
                  <li><strong>Civility:</strong> Attack ideas, never people (A.R.C. Principle I)</li>
                  <li><strong>Context:</strong> Provide sufficient context for claims and arguments</li>
                </ul>
              </div>
              <div className="bg-slate-800/30 rounded-lg p-4">
                <p className="text-red-300 font-semibold mb-2 text-sm">Prohibited Content:</p>
                <ul className="space-y-1 text-slate-400 text-sm list-disc list-inside">
                  <li>Hate speech, harassment, or targeted abuse</li>
                  <li>Explicit sexual content or violent imagery</li>
                  <li>Doxxing or sharing private information without consent</li>
                  <li>Deliberate misinformation or coordinated disinformation campaigns</li>
                </ul>
              </div>
            </div>
          </Section>

          {/* Intellectual Property */}
          <Section
            title="Intellectual Property"
            icon={<Copyright className="w-8 h-8 text-cyan-400 group-hover:animate-pulse" />}
            gradient="border-cyan-400/50 hover:border-cyan-300/50"
          >
            <p>
              All content remains the property of its original authors. By contributing, you grant Arc Codex a 
              limited license to display and share it on the platform.
            </p>
            <p>
              Do not copy, distribute, or modify content without proper permission.
            </p>
            <div className="bg-cyan-900/10 border border-cyan-500/30 rounded-lg p-6 mt-6">
              <p className="text-cyan-300 font-semibold mb-3">Your Rights & Our License:</p>
              <div className="space-y-3 text-slate-300 text-sm">
                <p>
                  <strong className="text-cyan-300">You retain ownership</strong> of all content you submit to Arc Codex.
                </p>
                <p>
                  <strong className="text-cyan-300">You grant us a license</strong> to display, distribute, and analyze 
                  your content through our A.R.C. framework for the purpose of operating the platform.
                </p>
                <p>
                  <strong className="text-cyan-300">We respect attribution:</strong> Original sources and authors are 
                  credited whenever possible.
                </p>
              </div>
            </div>
          </Section>

          {/* Disclaimer & Liability */}
          <Section
            title="Disclaimer & Liability"
            icon={<AlertTriangle className="w-8 h-8 text-orange-400 group-hover:animate-pulse" />}
            gradient="border-orange-400/50 hover:border-orange-300/50"
          >
            <p>
              Arc Codex provides content for educational and informational purposes only. We are not liable for 
              losses or damages arising from use of the site or reliance on any content.
            </p>
            <p>
              Users engage at their own risk, and should exercise critical thinking when interacting with the material.
            </p>
            <div className="bg-orange-900/10 border border-orange-500/30 rounded-lg p-6 mt-6">
              <p className="text-orange-300 font-semibold mb-3">Important Disclaimers:</p>
              <ul className="space-y-2 text-slate-300 text-sm list-disc list-inside">
                <li>Content is provided "as is" without warranties of any kind</li>
                <li>We are not responsible for third-party content linked from our platform</li>
                <li>Our A.R.C. analysis is computational assistance, not professional advice</li>
                <li>Users should independently verify information before making decisions</li>
                <li>We are not liable for damages arising from use or inability to use the service</li>
              </ul>
            </div>
          </Section>

          {/* Modifications */}
          <Section
            title="Modifications to Terms"
            icon={<RefreshCw className="w-8 h-8 text-green-400 group-hover:animate-pulse" />}
            gradient="border-green-400/50 hover:border-green-300/50"
          >
            <p>
              We may update these Terms at any time to reflect legal, operational, or technological changes. 
              Users are encouraged to review the Terms periodically.
            </p>
            <p>
              Continued use of Arc Codex constitutes acceptance of the revised Terms.
            </p>
            <div className="bg-green-900/10 border border-green-500/30 rounded-lg p-6 mt-6">
              <p className="text-green-300 font-semibold mb-3">How Updates Work:</p>
              <ul className="space-y-2 text-slate-300 text-sm list-disc list-inside">
                <li>Material changes will be posted prominently on this page</li>
                <li>The "Last Updated" date reflects the most recent revision</li>
                <li>Continued use after changes indicates acceptance</li>
                <li>If you disagree with changes, please discontinue use</li>
              </ul>
            </div>
          </Section>

          {/* Contact Section */}
          <motion.div 
            className="bg-gradient-to-br from-amber-500/10 via-orange-500/10 to-yellow-500/10 border border-amber-400/30 rounded-2xl p-8 text-center"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <Mail className="h-12 w-12 text-amber-400 mx-auto mb-4" />
            <h3 className="text-2xl font-bold text-slate-50 mb-4 font-sans">
              Contact & Support
            </h3>
            <p className="text-slate-300 font-serif mb-6 max-w-2xl mx-auto">
              Questions or concerns about these Terms? Our team is committed to maintaining a safe, 
              informative, and enjoyable environment for all Arc Codex users.
            </p>
            <div className="flex gap-4 justify-center flex-wrap">
              <Link 
                href="/about/contact"
                className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-900 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-serif"
              >
                <Mail className="h-5 w-5" />
                Contact Us
              </Link>
              <a 
                href="mailto:ross@arc-codex.com"
                className="inline-flex items-center gap-2 px-8 py-4 bg-slate-800/50 hover:bg-slate-800/70 border-2 border-amber-400/50 hover:border-amber-300 text-amber-300 font-bold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 font-serif"
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
                className="text-amber-300/90 hover:text-amber-200 transition-colors duration-300"
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

export default TermsPage;
