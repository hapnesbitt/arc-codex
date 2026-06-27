// Filename: /frontend/app/quiz/[week]/page.tsx
// Pop Quiz — archived week. Server component. ISR 3600s (archived weeks don't change).

import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import QuizPlayer, { type QuizPayload } from '@/components/QuizPlayer';

export const revalidate = 3600;

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  'https://arc-codex.com';

const WEEK_RE = /^\d{4}-W\d{2}$/;

interface PageProps {
  params: Promise<{ week: string }>;
}

async function getQuiz(week: string): Promise<QuizPayload | null> {
  if (!WEEK_RE.test(week)) return null;
  try {
    const res = await fetch(`${BACKEND}/api/quiz/${week}`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return (await res.json()) as QuizPayload;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { week } = await params;
  return {
    title: `Pop Quiz — ${week} — Arc Codex`,
    description: `Archived Pop Quiz for ${week}.`,
  };
}

export default async function ArchivedQuizPage({ params }: PageProps) {
  const { week } = await params;
  const quiz = await getQuiz(week);
  if (!quiz) notFound();

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <header className="text-center pb-8 border-b border-slate-800/60 space-y-3">
        <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
          Archive · Arc Codex
        </div>
        <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
          Pop Quiz
        </h1>
        <p className="font-serif text-sm text-slate-400 italic">
          {quiz.week_label} · 7 questions
        </p>
      </header>

      <section className="py-10">
        <QuizPlayer quiz={quiz} />
      </section>

      <footer className="pt-6 text-center print:hidden">
        <Link
          href="/quiz"
          className="font-sans text-[11px] uppercase tracking-[0.3em] text-amber-300 hover:text-amber-200 transition-colors"
        >
          ← This week's quiz
        </Link>
      </footer>
    </div>
  );
}
