/**
 * Arc Codex — About Gateway (Accessibility POC)
 * 
 * Same visual design as the original. Changes:
 * 
 * 1. react-aria-components for focus management + keyboard nav
 * 2. Semantic HTML landmarks (<main>, <nav>, <section>, proper heading hierarchy)
 * 3. Skip-to-content link for keyboard users
 * 4. Visible focus rings that match the amber/blue/green card themes
 * 5. aria-label and aria-describedby for screen reader context
 * 6. Cards are proper <a> links with role semantics handled by react-aria Link
 * 7. Reduced motion support via prefers-reduced-motion
 * 8. Footer links in a proper <nav> landmark
 *
 * New dependency: react-aria-components
 *   npm install react-aria-components
 *
 * Drop-in replacement for: frontend/app/about/page.tsx
 */

'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Shield, Cpu, Terminal, ArrowRight, Zap } from 'lucide-react';
import { Link as AriaLink } from 'react-aria-components';
import PageWrapper from '@/components/layout/PageWrapper';

// ── Reduced motion helper ────────────────────────────────────────────────────
// Respects OS-level "prefers-reduced-motion" setting. When enabled,
// framer-motion variants collapse to instant (no animation).

const reducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false;

const fadeUp = reducedMotion
  ? { initial: {}, animate: {} }
  : { initial: { opacity: 0, y: -20 }, animate: { opacity: 1, y: 0 } };

const cardHover = reducedMotion
  ? {}
  : { whileHover: { scale: 1.02 }, whileTap: { scale: 0.98 } };

// ── Card data ────────────────────────────────────────────────────────────────

const CARDS = [
  {
    href: '/about/sales',
    icon: Zap,
    iconColor: 'text-blue-500',
    accentBg: 'bg-blue-600',
    accentShadow: 'shadow-[0_0_20px_rgba(37,99,235,0.6)]',
    borderColor: 'border-blue-500/30 hover:border-blue-500',
    glowIdle: 'shadow-[0_0_30px_rgba(59,130,246,0.1)]',
    glowHover: 'hover:shadow-[0_0_50px_rgba(59,130,246,0.3)]',
    focusRing: 'focus-visible:ring-blue-500/70',
    titleColor: 'text-blue-100',
    ctaColor: 'text-blue-400',
    title: 'Vision & Mission',
    description: 'How Arc Codex empowers creators, small teams, and independent thinkers with enterprise-grade intelligence tools.',
    cta: 'Explore the Vision',
    ariaLabel: 'Vision and Mission — learn how Arc Codex empowers independent thinkers',
  },
  {
    href: '/about/support',
    icon: Cpu,
    iconColor: 'text-amber-500',
    accentBg: 'bg-amber-600',
    accentShadow: 'shadow-[0_0_20px_rgba(217,119,6,0.6)]',
    borderColor: 'border-amber-500/30 hover:border-amber-500',
    glowIdle: 'shadow-[0_0_30px_rgba(245,158,11,0.1)]',
    glowHover: 'hover:shadow-[0_0_50px_rgba(245,158,11,0.3)]',
    focusRing: 'focus-visible:ring-amber-500/70',
    titleColor: 'text-amber-100',
    ctaColor: 'text-amber-400',
    title: 'Support & Docs',
    description: 'A.R.C. framework specs, Sentinel forensics, translation, Google SSO, and full platform documentation.',
    cta: 'Open the Codex',
    ariaLabel: 'Support and Documentation — A.R.C. framework specs and platform docs',
  },
  {
    href: '/about/developer',
    icon: Terminal,
    iconColor: 'text-green-500',
    accentBg: 'bg-green-600',
    accentShadow: 'shadow-[0_0_20px_rgba(22,163,74,0.6)]',
    borderColor: 'border-green-500/30 hover:border-green-500',
    glowIdle: 'shadow-[0_0_30px_rgba(34,197,94,0.1)]',
    glowHover: 'hover:shadow-[0_0_50px_rgba(34,197,94,0.3)]',
    focusRing: 'focus-visible:ring-green-500/70',
    titleColor: 'text-green-100',
    ctaColor: 'text-green-400',
    title: 'Developer Docs',
    description: 'Stack architecture, API contracts, Redis schemas, AI pipeline gotchas, and the technical roadmap.',
    cta: 'Read the Spec',
    ariaLabel: 'Developer Documentation — stack architecture, API contracts, and technical roadmap',
  },
] as const;

// ── Footer links ─────────────────────────────────────────────────────────────

const FOOTER_LINKS = [
  { href: '/about/privacy', label: 'Privacy Policy' },
  { href: '/about/terms', label: 'Terms of Service' },
  { href: '/about/contact', label: 'Contact' },
] as const;

// ── Gateway Card ─────────────────────────────────────────────────────────────
// Uses react-aria Link for proper focus management, keyboard activation,
// and screen reader semantics. Visual design unchanged from original.

interface GatewayCardProps {
  card: typeof CARDS[number];
  index: number;
}

const GatewayCard: React.FC<GatewayCardProps> = ({ card, index }) => {
  const Icon = card.icon;

  return (
    <motion.div
      {...cardHover}
      initial={reducedMotion ? {} : { opacity: 0, y: 30 }}
      animate={reducedMotion ? {} : { opacity: 1, y: 0 }}
      transition={reducedMotion ? {} : { duration: 0.5, delay: 0.2 + index * 0.1 }}
    >
      <AriaLink
        href={card.href}
        aria-label={card.ariaLabel}
        className={`
          group relative block p-8 rounded-3xl bg-slate-900/40 border-2
          ${card.borderColor} transition-all duration-500 overflow-hidden
          ${card.glowIdle} ${card.glowHover}
          outline-none focus-visible:ring-2 ${card.focusRing} focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950
        `}
      >
        {/* Background icon */}
        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-30 transition-opacity" aria-hidden="true">
          <Icon className={`h-20 w-20 ${card.iconColor}`} />
        </div>

        <div className="relative z-10 space-y-4">
          {/* Accent dot */}
          <div
            className={`h-10 w-20 ${card.accentBg} rounded-full ${card.accentShadow} mb-5 animate-pulse`}
            aria-hidden="true"
          />
          <h2 className={`text-2xl font-bold ${card.titleColor}`}>
            {card.title}
          </h2>
          <p className="text-slate-300 leading-relaxed">
            {card.description}
          </p>
          <div className={`pt-3 flex items-center gap-2 ${card.ctaColor} font-bold`} aria-hidden="true">
            {card.cta}
            <ArrowRight className="h-5 w-5 group-hover:translate-x-2 transition-transform" />
          </div>
        </div>
      </AriaLink>
    </motion.div>
  );
};

// ── Main Page ────────────────────────────────────────────────────────────────

const AboutGateway = () => {
  return (
    <PageWrapper>
      {/* Skip to content — visible only on keyboard focus */}
      <a
        href="#about-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
      >
        Skip to main content
      </a>

      <main
        id="about-main"
        role="main"
        aria-label="About Arc Codex"
        className="min-h-[80vh] flex flex-col items-center justify-center max-w-5xl mx-auto px-4"
      >
        {/* Header */}
        <motion.header
          {...fadeUp}
          className="text-center mb-16 space-y-6"
        >
          <div className="inline-block p-3 rounded-2xl bg-slate-900/50 border border-slate-700 mb-4" aria-hidden="true">
            <Shield className="h-10 w-10 text-amber-400" />
          </div>
          <h1 className="text-4xl md:text-6xl font-black text-slate-50 tracking-tight">
            Arc Codex
          </h1>
          <p className="text-xl text-slate-400 max-w-2xl mx-auto italic">
            Intelligence infrastructure for the independent mind. Choose your path.
          </p>
        </motion.header>

        {/* Navigation cards */}
        <section
          aria-label="Explore Arc Codex sections"
          className="grid md:grid-cols-3 gap-6 w-full"
        >
          {CARDS.map((card, index) => (
            <GatewayCard key={card.href} card={card} index={index} />
          ))}
        </section>

        {/* Footer navigation */}
        <nav aria-label="Legal and contact links" className="mt-12 flex flex-wrap gap-6 justify-center text-sm text-slate-500">
          {FOOTER_LINKS.map((link, i) => (
            <React.Fragment key={link.href}>
              {i > 0 && <span aria-hidden="true">·</span>}
              <AriaLink
                href={link.href}
                className="hover:text-slate-300 transition-colors outline-none focus-visible:text-amber-400 focus-visible:underline focus-visible:underline-offset-4"
              >
                {link.label}
              </AriaLink>
            </React.Fragment>
          ))}
        </nav>

        <p className="mt-8 text-slate-500 text-sm font-mono uppercase tracking-widest" aria-hidden="true">
          A.R.C. Framework v5.2 // Connection Secure
        </p>
      </main>
    </PageWrapper>
  );
};

export default AboutGateway;
