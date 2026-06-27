'use client';

// frontend/components/QuizCard.tsx
// Single-question card. Big tap targets, per-question reveal on tap.

import Link from 'next/link';
import { ExternalLink, ArrowRight, Check, X } from 'lucide-react';
import type { QuizQuestion } from './QuizPlayer';

interface Props {
  index: number;
  total: number;
  question: QuizQuestion;
  chosen: number | null;
  onChoose: (idx: number) => void;
  onNext: () => void;
}

const LETTER = ['A', 'B', 'C', 'D'];

export default function QuizCard({ index, total, question, chosen, onChoose, onNext }: Props) {
  const revealed = chosen !== null;
  const isLast = index === total - 1;

  const buttonClass = (i: number) => {
    const base =
      'group w-full text-left rounded-2xl border px-4 py-3.5 sm:py-4 min-h-[58px] sm:min-h-[64px] flex items-start gap-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50';
    if (!revealed) {
      return `${base} border-slate-700/60 bg-slate-900/40 hover:border-amber-400/40 hover:bg-slate-900/70 active:bg-slate-900 cursor-pointer`;
    }
    if (i === question.correct) {
      return `${base} border-emerald-500/60 bg-emerald-500/10 text-emerald-100`;
    }
    if (i === chosen) {
      return `${base} border-rose-500/60 bg-rose-500/10 text-rose-100`;
    }
    return `${base} border-slate-800/60 bg-slate-900/20 text-slate-500`;
  };

  return (
    /* We use flex layout to explicitly control the ordering of items on mobile vs desktop */
    <div className="flex flex-col sm:block space-y-4 sm:space-y-6">
      
      {/* 1. Header Line: Normal position on desktop, pushed to the bottom on mobile */}
      <div className="order-last mt-6 sm:mt-0 flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-t border-slate-800/40 pt-4 sm:pt-0 sm:border-0">
        <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
          <span className="sm:hidden">Pop Quiz · </span>Question {index + 1} of {total}
        </div>
        <div className="flex gap-1.5" aria-hidden="true">
          {Array.from({ length: total }).map((_, i) => (
            <span
              key={i}
              className={
                i < index
                  ? 'w-6 h-1 rounded-full bg-amber-400/70'
                  : i === index
                  ? 'w-6 h-1 rounded-full bg-amber-400'
                  : 'w-6 h-1 rounded-full bg-slate-700/60'
              }
            />
          ))}
        </div>
      </div>

      {/* 2. Question Stem: Stays in natural order */}
      <h2 className="order-1 font-serif text-xl sm:text-3xl text-slate-100 leading-snug">
        {question.question}
      </h2>

      {/* 3. Multiple Choice Options: Stays in natural order */}
      <div className="order-2 space-y-2.5 sm:space-y-3">
        {question.options.map((opt, i) => (
          <button
            key={i}
            type="button"
            disabled={revealed}
            onClick={() => onChoose(i)}
            className={buttonClass(i)}
            aria-pressed={chosen === i}
          >
            <span className="font-sans text-[11px] uppercase tracking-[0.3em] text-slate-500 mt-0.5 sm:mt-1 shrink-0">
              {LETTER[i]}
            </span>
            <span className="font-serif text-base sm:text-lg leading-snug flex-1">{opt}</span>
            {revealed && i === question.correct && (
              <Check className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" aria-hidden="true" />
            )}
            {revealed && i === chosen && i !== question.correct && (
              <X className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" aria-hidden="true" />
            )}
          </button>
        ))}
      </div>

      {/* 4. Revealed Content Section */}
      {revealed && (
        /* On mobile, we use flex-col-reverse inside the revealed zone to force the Next button to the top of the answer details block! */
        <div className="order-3 border-t border-slate-800/60 pt-4 sm:pt-5 flex flex-col-reverse sm:block gap-4 space-y-3.5 sm:space-y-4">
          
          {/* Explanation Text */}
          <p className="font-serif text-base sm:text-lg text-slate-300 leading-relaxed italic mt-4 sm:mt-0">
            {question.explanation}
          </p>

          {/* Article Source Link */}
          <div className="mt-2 sm:mt-0">
            <Link
              href={question.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 font-sans text-[11px] uppercase tracking-[0.3em] text-amber-300 hover:text-amber-200 transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="truncate max-w-[80vw] sm:max-w-[60vw]">Read the source — {question.source_title}</span>
            </Link>
          </div>

          {/* Next Button: Renders at the top of the reveal zone on mobile viewports */}
          <button
            type="button"
            onClick={onNext}
            className="w-full sm:mt-1 rounded-2xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-sans text-sm uppercase tracking-[0.3em] font-semibold py-3.5 sm:py-4 min-h-[52px] sm:min-h-[56px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-200 flex items-center justify-center gap-2 mb-2 sm:mb-0"
          >
            {isLast ? 'See your score' : 'Next question'}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>

        </div>
      )}
    </div>
  );
}
