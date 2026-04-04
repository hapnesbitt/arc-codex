'use client';

import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import type { Article, Comment, Dossier } from '@/lib/types';

interface CopyAllButtonProps {
  article: Article;
  comments: Comment[];
}

export default function CopyAllButton({ article, comments }: CopyAllButtonProps) {
  const [copied, setCopied] = useState(false);

  function buildText() {
    const lines: string[] = [];

    lines.push(`TITLE: ${article.title}`);
    if (article.source_name || article.source) {
      lines.push(`SOURCE: ${article.source_name || article.source}`);
    }
    if (article.timestamp) {
      lines.push(`DATE: ${new Date(article.timestamp).toLocaleString()}`);
    }
    lines.push('');
    lines.push('--- ARTICLE ---');
    lines.push(article.original_text || '');

    if (article.blue_team_analysis) {
      lines.push('');
      lines.push('--- BLUE TEAM ANALYSIS ---');
      lines.push(article.blue_team_analysis);
    }
    if (article.red_team_analysis) {
      lines.push('');
      lines.push('--- RED TEAM ANALYSIS ---');
      lines.push(article.red_team_analysis);
    }
    if (article.purple_team_analysis) {
      lines.push('');
      lines.push('--- PURPLE TEAM SYNTHESIS ---');
      lines.push(article.purple_team_analysis);
    }
    if (article.sentinel_analysis) {
      lines.push('');
      lines.push('--- SENTINEL FORENSIC ANALYSIS ---');
      lines.push(article.sentinel_analysis);
    }

    // Dossier
    const dossier: Dossier = article.dossier
      ? typeof article.dossier === 'string'
        ? JSON.parse(article.dossier)
        : article.dossier
      : {};
    if (Object.keys(dossier).length > 0) {
      lines.push('');
      lines.push('--- DOSSIER ---');
      if (dossier.chimera_score != null) lines.push(`Chimera Score: ${Math.round(dossier.chimera_score * 100)}/100`);
      if (dossier.reading_level) lines.push(`Reading Level: ${dossier.reading_level}`);
      if (dossier.deep_analysis_summary) lines.push(`Deep Analysis: ${dossier.deep_analysis_summary}`);
      if (dossier.talking_points?.length) {
        lines.push('Talking Points:');
        dossier.talking_points.forEach((tp: string) => lines.push(`  • ${tp}`));
      }
      if (dossier.entities_found?.length) {
        lines.push(`Entities: ${dossier.entities_found.join(', ')}`);
      }
    }

    // Comments
    if (comments.length > 0) {
      lines.push('');
      lines.push('--- COMMENTS ---');
      comments.forEach(c => {
        const author = c.author || 'Anonymous';
        const date = new Date(c.timestamp).toLocaleString();
        lines.push(`[${author} — ${date}]`);
        lines.push(c.text);
        lines.push('');
      });
    }

    lines.push('');
    lines.push(`URL: ${process.env.NEXT_PUBLIC_BACKEND_URL ?? "https://arc-codex.com"}/article/${article.id}`);

    return lines.join('\n');
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(buildText());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={handleCopy}
      aria-label={copied ? "Copied to clipboard" : "Copy full article and all analysis to clipboard"}
      aria-live="polite"
      className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md
                 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-amber-400
                 border border-slate-700 hover:border-amber-400/50 transition-all duration-200
                 outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
    >
      {copied ? (
        <>
          <Check aria-hidden="true" className="h-3.5 w-3.5 text-green-400" />
          <span className="text-green-400">Copied</span>
        </>
      ) : (
        <>
          <Copy aria-hidden="true" className="h-3.5 w-3.5" />
          Copy All
        </>
      )}
    </button>
  );
}
