"use client";

/**
 * Arc Codex — GradeButton.tsx
 *
 * v1.0 — Editorial grade pill. Mirrors TranslateButton pattern.
 * Click → calls /api/grade/<article_id> → shows TA feedback in place of article text.
 * Grade letter shown in pill after load. Click again to toggle back to original.
 */

import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface GradeResult {
  grade: string;
  feedback: string;
  cached?: boolean;
}

interface GradeButtonProps {
  articleId: string;
  onGraded: (result: GradeResult) => void;
  onReset: () => void;
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function GradeButton({ articleId, onGraded, onReset }: GradeButtonProps) {
  const [loading, setLoading]       = useState(false);
  const [grade, setGrade]           = useState<string | null>(null);
  const [isShowing, setIsShowing]   = useState(false);
  const [error, setError]           = useState<string | null>(null);

  const handleClick = useCallback(async () => {
    // Toggle off if already showing
    if (isShowing) {
      setIsShowing(false);
      onReset();
      return;
    }

    // If we already have the grade, just re-show it
    if (grade) {
      setIsShowing(true);
      // Re-fetch from cache to get feedback text back
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
        const res = await fetch(`${backendUrl}/api/grade/${encodeURIComponent(articleId)}`);
        if (res.ok) {
          const data: GradeResult = await res.json();
          onGraded(data);
          setIsShowing(true);
        }
      } catch { /* silent — use cached grade label */ }
      return;
    }

    // Fetch grade
    setLoading(true);
    setError(null);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
      const res = await fetch(`${backendUrl}/api/grade/${encodeURIComponent(articleId)}`);
      if (!res.ok) throw new Error(`Grade API error: ${res.status}`);
      const data: GradeResult = await res.json();
      setGrade(data.grade);
      setIsShowing(true);
      onGraded(data);
    } catch (err) {
      console.error("Grade error:", err);
      setError("Grade unavailable");
    } finally {
      setLoading(false);
    }
  }, [articleId, grade, isShowing, onGraded, onReset]);

  // Grade color — A=emerald, B=blue, C=yellow, D/F=red
  const gradeColor = (g: string | null) => {
    if (!g) return "";
    const first = g[0].toUpperCase();
    if (first === "A") return "bg-emerald-500/20 border-emerald-500/40 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.2)]";
    if (first === "B") return "bg-blue-500/20 border-blue-500/40 text-blue-400 shadow-[0_0_10px_rgba(59,130,246,0.2)]";
    if (first === "C") return "bg-yellow-500/20 border-yellow-500/40 text-yellow-400 shadow-[0_0_10px_rgba(234,179,8,0.2)]";
    return "bg-red-500/20 border-red-500/40 text-red-400";
  };

  const label = loading ? "Grading..." : isShowing && grade ? grade : "Grade";

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={loading}
        aria-label={
          loading ? "Grading article" :
          isShowing ? `Grade: ${grade}. Click to hide feedback` :
          "Grade this article"
        }
        aria-pressed={isShowing}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all outline-none focus-visible:ring-2 focus-visible:ring-amber-500 disabled:cursor-wait border",
          isShowing && grade
            ? gradeColor(grade)
            : loading
            ? "bg-white/5 border-white/10 text-slate-400 cursor-wait"
            : "bg-white/5 border-white/5 text-slate-400 hover:bg-white/10 hover:text-slate-200"
        )}
      >
        {loading ? (
          <Spinner aria-hidden="true" />
        ) : (
          <PencilIcon aria-hidden="true" />
        )}
        <span aria-hidden="true">{label}</span>
      </button>

      {/* Reset pill — only when showing */}
      {isShowing && (
        <button
          onClick={() => { setIsShowing(false); onReset(); }}
          aria-label="Show original text"
          className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-slate-500 text-[10px] font-bold uppercase tracking-widest hover:text-white hover:bg-white/10 transition-all outline-none focus-visible:ring-2 focus-visible:ring-white"
        >
          Original
        </button>
      )}

      {error && (
        <span className="text-[10px] text-red-400 font-mono" role="alert">{error}</span>
      )}
    </div>
  );
}

// ── Micro-icons ───────────────────────────────────────────────────────────────

function PencilIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function Spinner(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" {...props}>
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}
