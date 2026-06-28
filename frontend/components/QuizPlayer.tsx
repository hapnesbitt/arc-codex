'use client';

// frontend/components/QuizPlayer.tsx
// Pop Quiz — interactive one-card-at-a-time flow.
// Anonymous; no persistence; React state only.

import { useMemo, useState } from 'react';
import QuizCard from './QuizCard';
import QuizResult from './QuizResult';

export interface QuizQuestion {
  id: number;
  question: string;
  options: string[];
  correct: number;
  explanation: string;
  source_article_id: string;
  source_title: string;
  source_url: string;
  source_name: string;
}

export interface QuizPayload {
  week: string;
  week_label: string;
  generated_at: string;
  quiz_number?: number;
  questions: QuizQuestion[];
}

interface Props {
  quiz: QuizPayload;
}

export default function QuizPlayer({ quiz }: Props) {
  const total = quiz.questions.length;
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>(() => Array(total).fill(null));

  const score = useMemo(
    () => answers.reduce<number>((acc, a, i) => acc + (a === quiz.questions[i].correct ? 1 : 0), 0),
    [answers, quiz.questions]
  );

  if (step >= total) {
    return (
      <QuizResult
        score={score}
        total={total}
        weekLabel={quiz.week_label}
        onReplay={() => {
          setAnswers(Array(total).fill(null));
          setStep(0);
        }}
      />
    );
  }

  const q = quiz.questions[step];
  return (
    <QuizCard
      index={step}
      total={total}
      question={q}
      chosen={answers[step]}
      onChoose={(idx) => {
        setAnswers((prev) => {
          if (prev[step] !== null) return prev;
          const next = [...prev];
          next[step] = idx;
          return next;
        });
      }}
      onNext={() => setStep((s) => s + 1)}
    />
  );
}
