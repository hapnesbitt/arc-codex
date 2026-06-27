// Filename: /frontend/app/quiz/page.tsx
// Pop Quiz — Server Component. Dynamic render (no build-time prerender)
// because the build container can't reach localhost:5005 to fetch the live
// quiz, so any prerender bakes in stale data. The page is cheap to render
// (one backend call per request), and ISR-style caching happens at the
// fetch layer via `next: { revalidate: 300 }`.

import Link from 'next/link';
import type { Metadata } from 'next';
import QuizPlayer, { type QuizPayload } from '@/components/QuizPlayer';

export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Pop Quiz — Arc Codex',
  description: "Seven questions from the week's news. Randomly ordered.",
};

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  'https://arc-codex.com';

async function getCurrentQuiz(): Promise<QuizPayload | null> {
  try {
    // No-store: the page is force-dynamic, so we want a fresh fetch on every
    // request. Without this, Next.js caches the fetch result on disk for the
    // revalidate window and stale quizzes persist even across container restarts.
    const res = await fetch(`${BACKEND}/api/quiz`, { cache: 'no-store' });
    if (!res.ok) return null;
    
    const data = (await res.json()) as QuizPayload;
    
    // Low-lift randomization: Shuffle the questions array natively on the server side
    if (data && Array.isArray(data.questions)) {
      data.questions = [...data.questions].sort(() => Math.random() - 0.5);
    }
    
    return data;
  } catch {
    return null;
  }
}

export default async function QuizPage() {
  const quiz = await getCurrentQuiz();

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-4 sm:py-12">
      {/* Kept hidden on mobile for optimal tap boundaries, visible on desktop */}
      <header className="hidden sm:block text-center pb-8 border-b border-slate-800/60 space-y-3">
        <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
          Arc Codex
        </div>
        <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
          Pop Quiz{quiz?.quiz_number ? ` #${quiz.quiz_number}` : ''}
        </h1>
        {quiz ? (
          <p className="font-serif text-sm text-slate-400 italic">
            {quiz.week_label} · Random Order
          </p>
        ) : (
          <p className="font-serif text-sm text-slate-400 italic">New quiz dropping soon</p>
        )}
      </header>

      <section className="py-2 sm:py-10">
        {quiz ? (
          <QuizPlayer quiz={quiz} />
        ) : (
          <div className="text-center space-y-4 py-12">
            <p className="font-serif text-lg text-slate-300">
              The quiz is currently being updated.
            </p>
            <p className="font-serif text-base text-slate-500 italic">
              Check back in a few moments.
            </p>
            <Link
              href="/"
              className="inline-block mt-4 font-sans text-[11px] uppercase tracking-[0.3em] text-amber-300 hover:text-amber-200 transition-colors"
            >
              ← Back to feed
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
