// Filename: /frontend/components/layout/PageWrapper.tsx
// FINAL VERSION: Now includes the conditional Back to Home button logic.
'use client';

import React from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link'; // Import Link
import { ArrowLeft } from 'lucide-react'; // Import ArrowLeft

// Update the component to accept the optional prop
function PageWrapper({ children, showBackButton = false }: { children: React.ReactNode; showBackButton?: boolean }) {
  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-slate-50 font-sans">
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl animate-pulse delay-2000"></div>
      </div>
      
      {/* ✅ This is the button logic, now inside the wrapper and controlled by the prop */}
      {showBackButton && (
        <div className="fixed top-4 left-4 z-50">
            <Link href="/" aria-label="Back to home">
                <div className="inline-flex items-center gap-2 px-3 py-2 bg-slate-800/80 hover:bg-slate-700/90 text-slate-100 rounded-xl shadow-lg backdrop-blur transition">
                    <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                    <span className="text-sm">Home</span>
                </div>
            </Link>
        </div>
      )}

      {/* main and footer share ONE fade container. Previously the footer sat outside it,
          so during the enter fade the content was transparent while the footer was fully
          opaque — leaving its "School of Chat" cross-link as the only legible thing on
          screen for the duration. On a cold PWA launch that read as School of Chat
          branding flashing before Arc's stories appeared. Nothing had leaked between the
          two apps; the manifest, icons and service worker were all correct.
          flex-col + flex-1 additionally keeps the footer below the fold on routes that
          render little content, so it cannot ride up into view. */}
      <motion.div
        className="relative z-10 flex flex-1 flex-col"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeInOut" }}
      >
        <main className="w-full flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          {children}
        </main>

        <footer className="border-t border-white/5 py-6 text-center text-xs text-slate-600">
          <a
            href="https://soc.arc-codex.com"
            className="inline-flex items-center gap-1.5 hover:text-slate-400 transition-colors focus-visible:outline-none focus-visible:text-amber-400"
            aria-label="School of Chat — AI-graded compliance and certification practice"
          >
            <span aria-hidden="true">🎸</span>
            School of Chat
          </a>
        </footer>
      </motion.div>
    </div>
  );
}
export default React.memo(PageWrapper);
