'use client';

// frontend/components/QuizResult.tsx
// Final score screen — Pop Quiz hero layout.

import Link from 'next/link';
import { RotateCcw, ArrowLeft, Trophy } from 'lucide-react';

interface Props {
  score: number;
  total: number;
  weekLabel: string;
  onReplay: () => void;
}

interface Tier {
  label: string;
  line: string;
}

const LADDER: Record<number, Tier> = {
  7: { label: 'Front Page Editor', line: 'A clean sweep. Nothing got past you.' },
  6: { label: 'Senior Correspondent', line: 'Almost perfect — one slipped through the wire.' },
  5: { label: 'On the Beat', line: 'Sharp instincts. A few details to chase down.' },
  4: { label: 'Steady Reader', line: 'You caught the big stories.' },
  3: { label: 'Skimming the Headlines', line: 'Time to read past the lede.' },
  2: { label: 'Out of the Loop', line: 'A rough news week to be quizzed on.' },
  1: { label: 'Just Checked In', line: 'Welcome back to the news cycle.' },
  0: { label: 'Off the Grid', line: "Sometimes that's the smarter play." },
};

export default function QuizResult({ score, total, weekLabel, onReplay }: Props) {
  const tier = LADDER[score] ?? LADDER[0];
  const isPerfect = score === total;

  return (
    <div className="text-center space-y-8 py-6">
      <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-amber-400 font-semibold animate-pulse">
        Pop Quiz Complete
      </div>

      {/* Hero Score Box Container */}
      <div className="relative max-w-sm mx-auto bg-slate-900/60 border border-slate-800/80 rounded-3xl p-8 shadow-2xl backdrop-blur-sm overflow-hidden">
        {/* Subtle decorative background highlight ring */}
        <div className="absolute -top-12 -left-12 w-32 h-32 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-12 -right-12 w-32 h-32 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

        {isPerfect && (
          <div className="flex justify-center mb-2 animate-bounce">
            <Trophy className="h-10 w-10 text-amber-400" />
          </div>
        )}

        <div className="space-y-1">
          <div className="font-sans text-[11px] uppercase tracking-[0.2em] text-slate-500">
            Final Score
          </div>
          <div className="font-serif text-7xl sm:text-8xl font-bold tracking-tight text-amber-300 leading-none">
            {score}<span className="text-slate-600 font-normal">/{total}</span>
          </div>
        </div>
      </div>

      {/* Tier Label & Subtitle Text */}
      <div className="space-y-3 max-w-md mx-auto">
        <div className="font-serif text-3xl sm:text-4xl font-semibold text-slate-100 leading-tight tracking-tight">
          {tier.label}
        </div>
        <p className="font-serif text-base sm:text-lg text-slate-400 italic leading-relaxed">
          "{tier.line}"
        </p>
      </div>

      {/* Navigation Buttons Block */}
      <div className="pt-4 flex flex-col sm:flex-row gap-3 max-w-md mx-auto print:hidden">
        <button
          type="button"
          onClick={onReplay}
          className="flex-1 rounded-2xl border border-slate-700/60 bg-slate-900/40 hover:bg-slate-900/70 hover:border-amber-400/40 text-slate-200 font-sans text-sm uppercase tracking-[0.3em] py-4 min-h-[56px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50 flex items-center justify-center gap-2"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Play Again
        </button>
        <Link
          href="/"
          className="flex-1 rounded-2xl border border-slate-700/60 bg-slate-900/40 hover:bg-slate-900/70 hover:border-amber-400/40 text-slate-200 font-sans text-sm uppercase tracking-[0.3em] py-4 min-h-[56px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50 flex items-center justify-center gap-2"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to feed
        </Link>
      </div>
    </div>
  );
}
