// Filename: /frontend/components/IntelligenceCard.tsx
// Version 7.3 - Chimera Difficulty Score
// Changes from v7.2:
// - Fixed mobile action button clipping by ensuring proper alignment/wrapping in flex column
// - Made AnalysisSection headers, content, and footers responsively padded (px-4 sm:px-8) to maximize text width on small screens

'use client';

import React, { useState, useEffect, useId, useMemo, useRef } from 'react';
import Link from 'next/link';
import { AnimatePresence, motion } from 'framer-motion';
import {
    Link2 as LinkIcon,
    Copy,
    Check,
    ChevronDown,
    MessageSquare,
    BrainCircuit,
    Shield,
    Crosshair,
    Combine,
    Share2,
    PlayCircle,
    Mail,
    ScanLine,
    Lock,
    Printer,
    Flashlight,
    GraduationCap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card as ShadCard } from "@/components/ui/card";
import CommentSection from '@/components/CommentSection';
import TranslateButton, { TranslatedFields } from '@/components/TranslateButton';
import { useUserPrefs } from '@/components/UserPrefsContext';
import { linkifyText } from '@/lib/textUtils';
import type { Article, Comment, Dossier } from '@/lib/types';

// --- TYPE DEFINITIONS (local only) ---

interface SentinelIndicator {
    dimension: string;
    signal: string;
    severity: string;
}

interface SentinelData {
    synthetic_confidence: number;
    assessment: 'HUMAN' | 'LIKELY_HUMAN' | 'UNCERTAIN' | 'LIKELY_SYNTHETIC' | 'SYNTHETIC';
    indicators: SentinelIndicator[];
    human_signals: string[];
    summary: string;
}

interface IntelligenceCardProps {
    card: Article;
    comments: Comment[];
    isCompact?: boolean;
    initialLang?: string | null;
    defaultExpandedSection?: keyof ExpandedSections;
    /** Permalink mode: every section open, no accordion chrome, no read-more toggles. */
    fullyExpanded?: boolean;
    /** Hero-image priority: first feed card + permalink pages set true (eager + fetchpriority=high). */
    priority?: boolean;
}

interface AccordionTextProps {
    text: string;
    characterLimit?: number;
    fullyExpanded?: boolean;
}

interface ChimeraGaugeProps {
    score: number;        // 0-100 integer
    readingLabel: string; // e.g. "College"
}

interface AnalysisSectionProps {
    title: string;
    icon: React.ReactNode;
    children: React.ReactNode;
    isExpanded: boolean;
    onToggle: () => void;
    /** Unique id used to wire aria-controls → content region */
    sectionId: string;
    /** When true, render as a static heading with always-visible content (no toggle, no chevron, no animation). */
    fullyExpanded?: boolean;
}

interface ExpandedSections {
    talkingPoints: boolean;
    deepAnalysis: boolean;
    redTeam: boolean;
    blueTeam: boolean;
    purpleTeam: boolean;
    sentinel: boolean;
}

// --- Helper: Ensure a field is a non-empty string ---
const safeText = (field: any): string => {
    if (!field) return '';
    return typeof field === 'string' ? field : JSON.stringify(field);
};

// --- Helper: Directive name → wiki slug (mirrors app/wiki/page.tsx) ---
const toSlug = (name: string) =>
    name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

// --- Helper: Extract clean domain from URL ---
const extractDomain = (url: string): string => {
    try {
        const hostname = new URL(url).hostname;
        return hostname.replace(/^www\./, '');
    } catch {
        return 'External Source';
    }
};

// --- Helper: Convert plain text with newlines to HTML paragraphs ---
// Each line is escapeHtml'd BEFORE linkifyText, mirroring the escape-then-
// linkify pattern markdownToHtml uses (via inlineFormat) so any raw HTML in
// the source (a <meta http-equiv="refresh"> smuggled through an RSS body,
// e.g. the 2026-07-09 incident) renders as literal text, not live markup.
const plainTextToHtml = (text: string): string => {
    if (!text.includes('\n')) return linkifyText(escapeHtml(text));
    const paragraphs = text.split(/\n{2,}/);
    return paragraphs
        .map(para => {
            const trimmed = para.trim();
            if (!trimmed) return '';
            const withBreaks = trimmed.split('\n').map(line => linkifyText(escapeHtml(line))).join('<br>');
            return `<p class="mb-3 text-slate-300 leading-relaxed">${withBreaks}</p>`;
        })
        .filter(Boolean)
        .join('\n');
};

// --- Helper: Escape HTML entities ---
const escapeHtml = (text: string): string =>
    text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// --- Helper: Inline markdown formatting (bold, italic, links) ---
const inlineFormat = (text: string): string =>
    text
        .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
        .replace(/\*\*(.*?)\*\*/g, '<strong class="text-slate-100">$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/(https?:\/\/[^\s<]+)/g, (url) => {
            const clean = url.replace(/[.,;:!?)]+$/, '');
            return `<a href="${clean}" target="_blank" rel="noopener noreferrer" class="text-slate-200 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2 break-all">${clean}</a>`;
        });

// --- Helper: Detect if text contains markdown STRUCTURE ---
const hasMarkdown = (text: string): boolean =>
    /^#{1,6}\s/m.test(text) || /^---+$/m.test(text) || /^>\s+/m.test(text);

// --- Helper: Strip markdown to plain text (for truncated previews) ---
const stripMarkdown = (text: string): string =>
    text
        .replace(/^#{1,6}\s+/gm, '')
        .replace(/\*\*\*(.*?)\*\*\*/g, '$1')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/^[-*]\s+/gm, '• ')
        .replace(/^>\s+/gm, '')
        .replace(/^---+$/gm, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim();

// --- Helper: Convert markdown text to styled HTML ---
const markdownToHtml = (text: string): string => {
    if (!hasMarkdown(text)) return linkifyText(text);

    const lines = text.split('\n');
    const html: string[] = [];
    let inList = false;

    for (const line of lines) {
        const trimmed = line.trim();

        if (!trimmed) {
            if (inList) { html.push('</ul>'); inList = false; }
            html.push('<div class="h-3"></div>');
            continue;
        }

        if (/^---+$/.test(trimmed)) {
            if (inList) { html.push('</ul>'); inList = false; }
            html.push('<hr class="border-slate-600/50 my-4" />');
            continue;
        }

        const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)/);
        if (headingMatch) {
            if (inList) { html.push('</ul>'); inList = false; }
            const level = headingMatch[1].length;
            const content = inlineFormat(escapeHtml(headingMatch[2]));
            const styles: Record<number, string> = {
                1: 'text-2xl font-bold text-slate-100 mt-6 mb-3',
                2: 'text-xl font-bold text-slate-200 mt-5 mb-3',
                3: 'text-lg font-semibold text-slate-100 mt-4 mb-2',
                4: 'text-base font-semibold text-slate-200 mt-4 mb-2',
                5: 'text-sm font-semibold text-slate-200 mt-3 mb-1',
                6: 'text-sm font-semibold text-slate-300 mt-3 mb-1',
            };
            html.push(`<h${level} class="${styles[level]}">${content}</h${level}>`);
            continue;
        }

        if (trimmed.startsWith('> ')) {
            if (inList) { html.push('</ul>'); inList = false; }
            const content = inlineFormat(escapeHtml(trimmed.slice(2)));
            html.push(`<blockquote class="border-l-2 border-slate-600 pl-4 italic text-slate-400 my-3">${content}</blockquote>`);
            continue;
        }

        const listMatch = trimmed.match(/^[-*]\s+(.*)/);
        if (listMatch) {
            if (!inList) { html.push('<ul class="my-3 space-y-1.5 list-disc ml-6">'); inList = true; }
            html.push(`<li class="text-slate-300">${inlineFormat(escapeHtml(listMatch[1]))}</li>`);
            continue;
        }

        if (inList) { html.push('</ul>'); inList = false; }
        html.push(`<p class="mb-3 text-slate-300 leading-relaxed">${inlineFormat(escapeHtml(trimmed))}</p>`);
    }

    if (inList) html.push('</ul>');
    return html.join('\n');
};

// Strip a leading line from `body` if it equals `title` (whitespace + case insensitive).
// Many RSS feeds embed the headline as the first line of original_text; we don't want
// the title rendered twice (visible duplication + screen-reader repeat).
function stripLeadingTitle(body: string, title: string): string {
    if (!body || !title) return body;
    const normalize = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase();
    const target = normalize(title);
    if (!target) return body;
    const lines = body.split(/\r?\n/);
    let i = 0;
    while (i < lines.length && lines[i].trim() === '') i++;
    if (i >= lines.length) return body;
    if (normalize(lines[i]) === target) {
        return lines.slice(i + 1).join('\n').replace(/^[\r\n]+/, '');
    }
    return body;
}

// --- Helper: Text with "Read More" Accordion ---
const AccordionText: React.FC<AccordionTextProps> = ({ text, characterLimit = 400, fullyExpanded = false }) => {
    const [isExpanded, setIsExpanded] = useState<boolean>(false);
    const remainderId = useId();

    useEffect(() => {
        const expand = () => setIsExpanded(true);
        window.addEventListener('beforeprint', expand);
        return () => window.removeEventListener('beforeprint', expand);
    }, []);

    const { needsTruncation, fullHtml } = useMemo(() => {
        const cleanText = safeText(text);
        const isMarkdown = hasMarkdown(cleanText);
        const plainText = isMarkdown ? stripMarkdown(cleanText) : cleanText;
        const fullHtml = isMarkdown ? markdownToHtml(cleanText) : plainTextToHtml(cleanText);
        return { needsTruncation: !fullyExpanded && plainText.length > characterLimit, fullHtml };
    }, [text, characterLimit, fullyExpanded]);

    if (!needsTruncation) {
        return (
            <div
                className="prose prose-invert max-w-prose font-serif text-slate-200 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: fullHtml }}
            />
        );
    }

    const toggleExpansion = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsExpanded(prev => !prev);
    };

    return (
        <div>
            <button
                onClick={toggleExpansion}
                aria-expanded={isExpanded}
                aria-controls={remainderId}
                className={`font-sans text-xs uppercase tracking-[0.2em] transition-colors ring-focus rounded-sm ${
                    isExpanded
                        ? 'text-sky-400 hover:text-sky-200'
                        : 'text-rose-400 hover:text-rose-200'
                }`}
            >
                {isExpanded ? "Read less —" : "— Read more"}
            </button>
            <div
                id={remainderId}
                hidden={!isExpanded}
                className="prose prose-invert max-w-prose font-serif text-slate-200 leading-relaxed mt-4"
                dangerouslySetInnerHTML={{ __html: fullHtml }}
            />
        </div>
    );
};

// --- Video List Component ---
const VideoList: React.FC<{ text: string }> = ({ text }) => {
    const lines = text.split('\n');

    return (
        <div className="space-y-3">
            {lines.map((line, index) => {
                if (line.trim().startsWith('Video:')) {
                    const videoPath = line.replace('Video:', '').trim();
                    const videoName = videoPath
                        .replace(/\.(mkv|mp4|webm|avi|mov|flv|wmv|m4v)$/i, '')
                        .trim();

                    return (
                        <a
                            key={index}
                            href={`/videos/${encodeURIComponent(videoPath)}`}
                            aria-label={`Play video: ${videoName}`}
                            className="flex items-center gap-3 p-3 rounded-sm border border-slate-800 hover:border-slate-600 transition-colors duration-200 group"
                        >
                            <PlayCircle className="h-5 w-5 text-slate-400 flex-shrink-0 group-hover:text-slate-100 transition-colors" aria-hidden="true" />
                            <span className="font-serif text-slate-200 group-hover:text-slate-50 transition-colors" aria-hidden="true">
                                {videoName}
                            </span>
                        </a>
                    );
                } else if (line.trim()) {
                    // Escape first, then linkify — mirrors plainTextToHtml.
                    // Article original_text can carry raw HTML from RSS sources
                    // (2026-07-09 Hak5 incident); this ensures the video-list
                    // non-Video lines can't render live markup either.
                    const linkedLine = linkifyText(escapeHtml(line));
                    return (
                        <div
                            key={index}
                            className="text-slate-300 leading-relaxed"
                            dangerouslySetInnerHTML={{ __html: linkedLine }}
                        />
                    );
                } else {
                    return null;
                }
            })}
        </div>
    );
};

// --- Chimera Difficulty Score Gauge ---
const ChimeraGauge: React.FC<ChimeraGaugeProps> = ({ score, readingLabel }) => {
    const circumference = 2 * Math.PI * 20;
    const strokeDashoffset = circumference - ((score / 100) * circumference);
    const scoreColor =
        score <= 30 ? '#86efac'
        : score <= 45 ? '#22c55e'
        : score <= 55 ? '#10b981'
        : score <= 70 ? '#15803d'
        : '#14532d';

    return (
        <>
        <div className="flex flex-col items-center gap-1" aria-hidden="true">
            <div className="relative h-16 w-16 flex items-center justify-center flex-shrink-0">
                <svg
                    className="absolute inset-0"
                    viewBox="0 0 48 48"
                    style={{ transform: 'rotate(-90deg)' }}
                    aria-hidden="true"
                >
                    <circle
                        cx="24" cy="24" r="20"
                        stroke="#e2e8f0" strokeOpacity="0.1"
                        strokeWidth="3" fill="transparent"
                    />
                    <motion.circle
                        cx="24" cy="24" r="20"
                        stroke={scoreColor} strokeWidth="3"
                        fill="transparent" strokeLinecap="round"
                        strokeDasharray={circumference}
                        initial={{ strokeDashoffset: circumference }}
                        animate={{ strokeDashoffset }}
                        transition={{ duration: 1.5, ease: [0.43, 0.13, 0.23, 0.96] }}
                    />
                </svg>
                <div
                    className="relative font-mono text-base font-bold"
                    style={{ color: scoreColor }}
                >
                    {score}
                </div>
            </div>

            <div className="text-center max-w-[9rem]">
                <div
                    className="font-mono text-xs font-semibold leading-tight"
                    style={{ color: scoreColor }}
                >
                    {readingLabel} reading level
                </div>
            </div>
        </div>
        <span className="sr-only">
            Chimera readability score {score} out of 100, {readingLabel} reading level.
        </span>
        </>
    );
};

// --- Collapsible Analysis Section ---
const AnalysisSection: React.FC<AnalysisSectionProps> = ({
    title,
    icon,
    children,
    isExpanded,
    onToggle,
    sectionId,
    fullyExpanded = false,
}) => {
    const contentId = `${sectionId}-content`;
    if (fullyExpanded) {
        return (
            <div className="border-t border-slate-800">
                <div className="w-full flex items-center px-4 sm:px-8 py-5">
                    <div className="flex items-center gap-3">
                        <div aria-hidden="true">{icon}</div>
                        <h3 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
                            {title}
                        </h3>
                    </div>
                </div>
                <div id={contentId} className="px-4 sm:px-8 pb-6 pt-0">
                    {children}
                </div>
            </div>
        );
    }
    return (
        <div className="border-t border-slate-800">
            <button
                onClick={onToggle}
                aria-expanded={isExpanded}
                aria-controls={contentId}
                className="w-full flex justify-between items-center px-4 sm:px-8 py-5 text-left hover:bg-slate-800/30 transition-colors group ring-focus focus-visible:ring-inset"
            >
                <div className="flex items-center gap-3">
                    <div aria-hidden="true">
                        {icon}
                    </div>
                    <h3 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
                        {title}
                    </h3>
                </div>
                <ChevronDown
                    className={`h-4 w-4 text-slate-500 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}
                    aria-hidden="true"
                />
            </button>
            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        id={contentId}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: 'easeInOut' }}
                        className="overflow-hidden"
                    >
                        <div className="px-4 sm:px-8 pb-6 pt-0">
                            {children}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

// --- Research Menu ---
const ResearchMenu: React.FC<{ title: string; articleId: string; snippet?: string; sourceUrl?: string }> = ({ title, articleId, snippet, sourceUrl }) => {
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';
    const articleUrl = `${backendUrl}/article/${articleId}`;

    const context = snippet
        ? `Article: "${title}"\n\nSource: ${sourceUrl || articleUrl}\n\nContext: ${snippet.slice(0, 500)}`
        : `Article: "${title}"\n\nSource: ${articleUrl}`;

    const close = () => {
        setIsOpen(false);
        triggerRef.current?.focus();
    };

    useEffect(() => {
        if (!isOpen) return;
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) close();
        };
        const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
        document.addEventListener("mousedown", handleClickOutside);
        document.addEventListener("keydown", handleEsc);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
            document.removeEventListener("keydown", handleEsc);
        };
    }, [isOpen]);

    const handleGoogle = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://www.google.com/search?q=${encodeURIComponent(title)}`, "_blank");
        close();
    };

    const handleClaude = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://claude.ai/new?q=${encodeURIComponent(context)}`, "_blank");
        close();
    };

    const handleChatGPT = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://chatgpt.com/?q=${encodeURIComponent(context)}`, "_blank");
        close();
    };

    const handlePerplexity = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://www.perplexity.ai/search?q=${encodeURIComponent(context)}`, "_blank");
        close();
    };

    return (
        <div className="relative" ref={menuRef}>
            <button
                ref={triggerRef}
                onClick={(e) => { e.stopPropagation(); setIsOpen(s => !s); }}
                aria-label="Research"
                data-tooltip="Open this article in Claude, ChatGPT, Perplexity, or Google — with the title and source already teed up in the search box."
                aria-expanded={isOpen}
                aria-haspopup="menu"
                className="inline-flex items-center justify-center rounded-sm h-10 w-10 text-slate-400 hover:text-slate-100 hover:bg-slate-800/40 ring-focus"
            >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/></svg>
            </button>
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        role="menu"
                        aria-label="Research options"
                        initial={{ opacity: 0, scale: 0.98, y: -2 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.98, y: -2 }}
                        transition={{ duration: 0.12 }}
                        className="absolute right-0 top-full mt-2 z-50 w-36 rounded-sm border border-slate-800 bg-slate-950 overflow-hidden"
                    >
                        <button
                            role="menuitem"
                            onClick={handleGoogle}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                            <span>Google</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleChatGPT}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-emerald-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0L4.01 14.23A4.5 4.5 0 0 1 2.34 7.896zm16.597 3.855l-5.843-3.369 2.02-1.168a.076.076 0 0 1 .071 0l4.808 2.773a4.5 4.5 0 0 1-.676 8.115v-5.678a.795.795 0 0 0-.38-.673zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.807-2.774a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"/></svg>
                            <span>ChatGPT</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handlePerplexity}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-teal-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M22.414 0h-8.015L12 2.678 9.601 0H1.586L8.15 7.773 0 16.227h7.875L12 20.843l4.125-4.616H24l-8.15-8.454L22.414 0zM9.977 2.678l1.764 1.927H8.213l1.764-1.927zm4.046 0 1.764 1.927h-3.528l1.764-1.927zM3.414 1.678h4.594L3.414 6.583V1.678zm13.578 0h4.594v4.905l-4.594-4.905zM1.838 14.549l6.406-6.645h7.512l6.406 6.645H1.838zm6.337 1.678H4.05l3.472-3.884-.347 3.884zm7.65 0-.347-3.884 3.472 3.884h-3.125zM12 19.135l-2.912-3.257h5.824L12 19.135z"/></svg>
                            <span>Perplexity</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleClaude}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-amber-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"/></svg>
                            <span>Claude</span>
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

// --- Share Menu ---
const ShareMenu: React.FC<{ title: string; articleId: string; blurb?: string; lang?: string | null; counterComment?: string }> = ({
    title,
    articleId,
    blurb,
    lang,
    counterComment,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [copied, setCopied] = useState(false);
    const [bskyPosted, setBskyPosted] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';
    const baseUrl = `${backendUrl}/article/${articleId}`;
    const fullUrl = lang ? `${baseUrl}?lang=${encodeURIComponent(lang)}` : baseUrl;
    const sharePayload = counterComment
        ? `${title}\n\n${counterComment}\n\n${fullUrl}`
        : `${title}\n\n${fullUrl}`;

    const close = () => {
        setIsOpen(false);
        triggerRef.current?.focus();
    };

    useEffect(() => {
        if (!isOpen) return;
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) close();
        };
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') close();
        };
        document.addEventListener('mousedown', handleClickOutside);
        document.addEventListener('keydown', handleEsc);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleEsc);
        };
    }, [isOpen]);

    const handleShare = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (navigator.share) {
            navigator.share({ title, text: sharePayload, url: fullUrl }).catch(() => {});
            return;
        }
        setIsOpen(prev => !prev);
    };

    const handleFacebook = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://www.facebook.com/sharer.php?u=${encodeURIComponent(fullUrl)}`, '_blank', 'width=600,height=400');
        close();
    };

    const handleBluesky = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://bsky.app/intent/compose?text=${encodeURIComponent(sharePayload)}`, '_blank', 'width=600,height=400');
        close();
    };

    const handleMastodon = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://mastodon.social/share?text=${encodeURIComponent(sharePayload)}`, '_blank', 'width=600,height=400');
        close();
    };

    const handleSubstack = (e: React.MouseEvent) => {
        e.stopPropagation();
        const body = blurb ? `${blurb}\n\nRead the full A.R.C. analysis: ${fullUrl}` : fullUrl;
        navigator.clipboard.writeText(`${title}\n\n${body}`);
        window.open('https://substack.com/publish/post/new', '_blank', 'width=900,height=700');
        close();
    };

    const handleEmail = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.location.href = `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(sharePayload)}`;
        close();
    };

    return (
        <div className="relative" ref={menuRef}>
            <Button
                ref={triggerRef}
                variant="ghost"
                size="icon"
                onClick={handleShare}
                aria-label="Share"
                data-tooltip="Share this article on Bluesky, Mastodon, Reddit, or by email — with a summary of the Purple Team's analysis attached."
                aria-expanded={isOpen}
                aria-haspopup="menu"
                className="rounded-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800/40"
            >
                <Share2 className="h-5 w-5" aria-hidden="true" />
            </Button>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        role="menu"
                        aria-label="Share options"
                        initial={{ opacity: 0, scale: 0.98, y: -2 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.98, y: -2 }}
                        transition={{ duration: 0.12 }}
                        className="absolute right-0 top-full mt-2 z-50 w-48 rounded-sm border border-slate-800 bg-slate-950 overflow-hidden"
                    >
                        <button
                            role="menuitem"
                            onClick={handleFacebook}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-blue-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                            </svg>
                            <span>Facebook</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleBluesky}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-sky-400" viewBox="0 0 360 320" fill="currentColor" aria-hidden="true">
                                <path d="M180 141.964C163.699 110.262 119.308 51.1817 78.0347 26.67C56.326 14.0375 3.49981 -3.09781 3.49981 58.4432C3.49981 70.0484 6.51032 152.417 8.02611 164.966C13.0991 206.358 55.1251 218.468 91.8511 211.868C28.8511 221.896 -1.74363 233.946 21.5634 269.754C55.0434 319.698 119.309 292.734 148.915 278.006C167.735 268.609 178.431 260.768 180 256.477C181.569 260.768 192.265 268.609 211.085 278.006C240.691 292.734 304.957 319.698 338.437 269.754C361.744 233.946 331.149 221.896 268.149 211.868C304.875 218.468 346.901 206.358 351.974 164.966C353.49 152.417 356.5 70.0484 356.5 58.4432C356.5 -3.09781 303.674 14.0375 281.965 26.67C240.692 51.1817 196.301 110.262 180 141.964Z"/>
                            </svg>
                            <span>Bluesky</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleMastodon}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-purple-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M23.268 5.313c-.35-2.578-2.617-4.61-5.304-5.004C17.51.242 15.792 0 11.813 0h-.03c-3.98 0-4.835.242-5.288.309C3.882.692 1.496 2.518.917 5.127.64 6.412.61 7.837.661 9.143c.074 1.874.088 3.745.26 5.611.118 1.24.325 2.47.62 3.68.55 2.237 2.777 4.098 4.96 4.857 2.336.792 4.849.923 7.256.38.265-.061.527-.132.786-.213.585-.184 1.27-.39 1.774-.753a.057.057 0 0 0 .023-.043v-1.809a.052.052 0 0 0-.02-.041.053.053 0 0 0-.046-.01 20.282 20.282 0 0 1-4.709.545c-2.73 0-3.463-1.284-3.674-1.818a5.593 5.593 0 0 1-.319-1.433.053.053 0 0 1 .066-.054c1.517.363 3.072.546 4.632.546.376 0 .75 0 1.125-.01 1.57-.044 3.224-.124 4.768-.422.038-.008.077-.015.11-.024 2.435-.464 4.753-1.92 4.989-5.604.008-.145.03-1.52.03-1.67.002-.512.167-3.63-.024-5.545zm-3.748 9.195h-2.561V8.29c0-1.309-.55-1.976-1.67-1.976-1.23 0-1.846.79-1.846 2.35v3.403h-2.546V8.663c0-1.56-.617-2.35-1.848-2.35-1.112 0-1.668.668-1.67 1.977v6.218H4.822V8.102c0-1.31.337-2.35 1.011-3.12.696-.77 1.608-1.164 2.74-1.164 1.311 0 2.302.5 2.962 1.498l.638 1.06.638-1.06c.66-.999 1.65-1.498 2.96-1.498 1.13 0 2.043.395 2.74 1.164.675.77 1.012 1.81 1.012 3.12z"/>
                            </svg>
                            <span>Mastodon</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleSubstack}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-orange-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M22.539 8.242H1.46V5.406h21.08v2.836zM1.46 10.812V24L12 18.11 22.54 24V10.812H1.46zM22.54 0H1.46v2.836h21.08V0z"/>
                            </svg>
                            <span>Substack</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleEmail}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors ring-focus focus-visible:ring-inset focus-visible:bg-slate-800/80"
                        >
                            <Mail className="h-4 w-4 text-slate-400" aria-hidden="true" />
                            <span>Email</span>
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

// --- The Main Intelligence Card Component ---
const IntelligenceCard: React.FC<IntelligenceCardProps> = ({
    card,
    comments,
    isCompact = false,
    initialLang = null,
    defaultExpandedSection,
    fullyExpanded = false,
    priority = false,
}) => {
    const [hasCopied, setHasCopied] = useState<boolean>(false);
    const [translatedFields, setTranslatedFields] = useState<TranslatedFields | null>(null);
    const [isRTL, setIsRTL] = useState(false);
    const [currentLang, setCurrentLang] = useState<string | null>(null);
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';
    const { prefs } = useUserPrefs();
    const isOwner   = !!prefs?.sub && prefs.sub === (card as any).owner;
    const isPrivate = (card as any).visibility === 'private';

    const handleTranslated = (fields: TranslatedFields, rtl: boolean) => {
        setTranslatedFields(fields);
        setIsRTL(rtl);
    };
    const handleReset = () => {
        setTranslatedFields(null);
        setIsRTL(false);
        setCurrentLang(null);
    };

    useEffect(() => {
        if (!initialLang) return;
        const fetchInitialLang = async () => {
            try {
                const res = await fetch(
                    `${backendUrl}/api/translate/${encodeURIComponent(card.id)}?lang=${encodeURIComponent(initialLang)}`
                );
                if (res.ok) {
                    const data = await res.json();
                    const { rtl = false, ...fields } = data;
                    handleTranslated(fields, Boolean(rtl));
                    setCurrentLang(initialLang);
                }
            } catch { /* silent fallback */ }
        };
        fetchInitialLang();
    }, [initialLang]);

    useEffect(() => {
        const expandAll = () => setExpandedSections({
            talkingPoints: true, deepAnalysis: true, redTeam: true,
            blueTeam: true, purpleTeam: true, sentinel: true,
        });
        window.addEventListener('beforeprint', expandAll);
        return () => window.removeEventListener('beforeprint', expandAll);
    }, []);

    const t = <K extends keyof TranslatedFields>(field: K, original: string): string =>
        translatedFields?.[field] ?? original;

    const [expandedSections, setExpandedSections] = useState<ExpandedSections>({
        talkingPoints: fullyExpanded || defaultExpandedSection === 'talkingPoints',
        deepAnalysis: fullyExpanded || defaultExpandedSection === 'deepAnalysis',
        redTeam: fullyExpanded || defaultExpandedSection === 'redTeam',
        blueTeam: fullyExpanded || defaultExpandedSection === 'blueTeam',
        purpleTeam: fullyExpanded || defaultExpandedSection === 'purpleTeam',
        sentinel: fullyExpanded || defaultExpandedSection === 'sentinel',
    });

    const sourceName = card.source_name || card.source || 'Unknown Source';
    const isManualUpload = sourceName === 'Manual Upload';
    const articleUrl = `${backendUrl}/article/${card.id}`;

    const hasExternalSource = isManualUpload && card.sourceUrl && card.sourceUrl.trim() !== '';
    const displaySource = hasExternalSource ? extractDomain(card.sourceUrl!) : sourceName;
    const sourceUrl = hasExternalSource
        ? card.sourceUrl!
        : (isManualUpload ? articleUrl : (card.sourceUrl || '#'));

    const dossier = useMemo<Dossier>(() => {
        if (!card?.dossier) return {};
        try {
            return typeof card.dossier === 'string' ? JSON.parse(card.dossier) : card.dossier;
        } catch (e) {
            console.error("Failed to parse dossier:", e);
            return {};
        }
    }, [card?.dossier]);

    const formattedDate = useMemo(() =>
        card?.timestamp
            ? new Date(card.timestamp).toLocaleString([], {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit'
              })
            : '',
    [card?.timestamp]);

    const handleCopy = (e: React.MouseEvent) => {
        e.stopPropagation();
        const base = `${backendUrl}/article/${card.id}`;
        const fullArticleUrl = currentLang ? `${base}?lang=${encodeURIComponent(currentLang)}` : base;
        const title = translatedFields?.title ?? card.title;
        const copyText = counterComment
            ? `${title}\n\n${counterComment}\n\n${fullArticleUrl}`
            : `${title}\n\n${fullArticleUrl}`;
        navigator.clipboard.writeText(copyText);
        setHasCopied(true);
        setTimeout(() => setHasCopied(false), 2000);
    };

    const toggleSection = (section: keyof ExpandedSections) => {
        setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
    };

    const chimeraScore: number =
        dossier?.chimera_score != null ? dossier.chimera_score
        : parseInt((card as any).nlp_chimera_score || '0', 10) || 0;
    const readingLabel: string =
        dossier?.reading_label ?? (card as any).nlp_reading_label ?? '';
    const talkingPoints = dossier?.talking_points;
    const deepAnalysisSummary = dossier?.deep_analysis_summary;

    const shareBlurb = card.purple_team_analysis?.substring(0, 200)
        || card.blue_team_analysis?.substring(0, 200)
        || 'Read this on Arc Codex';

    const rawCounterComment = comments.find(c => c.author === 'A.R.C. Counter-Analyst')?.text ?? null;
    const counterComment = rawCounterComment
        ? rawCounterComment.replace(/^The article/i, 'This article')
        : null;

    const sentinelData = useMemo<SentinelData | null>(() => {
        if (!card?.sentinel_analysis) return null;
        try {
            const parsed = typeof card.sentinel_analysis === 'string'
                ? JSON.parse(card.sentinel_analysis)
                : card.sentinel_analysis;
            if (parsed.synthetic_confidence !== undefined && parsed.assessment && parsed.summary) {
                return parsed;
            }
            return null;
        } catch (e) {
            console.error("Failed to parse sentinel data:", e);
            return null;
        }
    }, [card?.sentinel_analysis]);

    const sentinelColor = useMemo(() => {
        if (!sentinelData) return null;
        const conf = sentinelData.synthetic_confidence;
        if (conf <= 0.6) return { label: 'Human' };
        if (conf <= 0.7) return { label: 'Likely Human' };
        if (conf <= 0.8) return { label: 'Uncertain' };
        if (conf <= 0.9) return { label: 'Likely Synthetic' };
        return { label: 'Synthetic' };
    }, [sentinelData]);

    if (!card) return null;

    const uid = card.id;
    const researchSnippet = card.blue_team_analysis || card.purple_team_analysis || card.original_text;

    // ── Minimal video card ─────────────────────
    if (card.origin === 'video') {
        const videoUrl = card.sourceUrl || (card as any).url || '#';
        const videoDomain = (() => {
            try { return new URL(videoUrl).hostname.replace(/^www\./, ''); } catch { return 'vid.arc-codex.com'; }
        })();
        return (
            <article
                aria-labelledby={`card-title-${uid}`}
                className="w-full max-w-2xl mx-auto"
            >
                <div className="w-full overflow-hidden border-b border-slate-800/60 bg-slate-900/30">
                    <div className="p-4 sm:p-8">
                        <header className="flex flex-col-reverse items-end gap-4 sm:flex-row sm:justify-between sm:items-start mb-4">
                            <div className="flex-1 w-full">
                                <a href={videoUrl} target="_blank" rel="noopener noreferrer">
                                    <h2
                                        id={`card-title-${uid}`}
                                        className="font-serif text-2xl sm:text-3xl font-semibold text-slate-50 mb-3 cursor-pointer transition-colors hover:text-slate-100 leading-tight tracking-tight"
                                    >
                                        {card.title}
                                    </h2>
                                </a>
                            </div>
                            <div className="flex items-center gap-2 print:hidden max-w-full flex-wrap justify-end">
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={handleCopy}
                                    className="rounded-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800/40"
                                    aria-label={hasCopied ? "Link copied" : "Copy article link"}
                                >
                                    {hasCopied ? <Check className="text-emerald-400" aria-hidden="true" /> : <Copy aria-hidden="true" />}
                                </Button>
                                <ShareMenu
                                    title={card.title}
                                    articleId={card.id}
                                    blurb={card.description || ''}
                                    lang={null}
                                />
                            </div>
                        </header>
                        {card.description && (
                            <p className="font-serif text-slate-400 leading-relaxed mb-4">{card.description}</p>
                        )}
                        <span className="chip">
                            {videoDomain}
                        </span>
                    </div>
                    <div className="border-t border-slate-800" aria-hidden="true" />
                    <footer className="flex justify-between items-center px-4 sm:px-8 py-5 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
                        <time dateTime={card.timestamp}>{formattedDate}</time>
                    </footer>
                </div>
            </article>
        );
    }

    return (
        <article
            aria-labelledby={`card-title-${uid}`}
            className="w-full max-w-2xl mx-auto"
        >
            <div className="group relative w-full h-full overflow-hidden border-b border-slate-800/60 bg-slate-900/30">
                {card.imageUrl && (
                    <a
                        href={sourceUrl}
                        target={hasExternalSource ? "_blank" : "_self"}
                        rel={hasExternalSource ? "noopener noreferrer" : undefined}
                        tabIndex={-1}
                        aria-hidden="true"
                    >
                        <div className="w-full aspect-video sm:aspect-auto sm:h-80 bg-slate-950 overflow-hidden border-b border-slate-800/60">
                            {(() => {
                                const rawSrc = card.imageUrl!.startsWith('/uploads/')
                                    ? `${process.env.NEXT_PUBLIC_BACKEND_URL ?? ''}${card.imageUrl}`
                                    : card.imageUrl!;
                                const isScrapedJpg =
                                    card.imageUrl!.startsWith('/uploads/scraped/') && card.imageUrl!.endsWith('.jpg');
                                const webpBase = isScrapedJpg ? rawSrc.slice(0, -4) : null;
                                const jpegImg = (
                                    <img
                                        src={rawSrc}
                                        alt=""
                                        width={1200}
                                        height={675}
                                        decoding="async"
                                        loading={priority ? "eager" : "lazy"}
                                        fetchPriority={priority ? "high" : "auto"}
                                        onError={(e) => { (e.target as HTMLImageElement).src = '/uploads/arc-codex-default.jpg'; }}
                                        className="w-full h-full object-cover"
                                    />
                                );
                                return webpBase ? (
                                    <picture>
                                        <source
                                            type="image/webp"
                                            srcSet={`${webpBase}-480.webp 480w, ${webpBase}-800.webp 800w, ${webpBase}-1200.webp 1200w`}
                                            sizes="(min-width: 640px) 600px, 350px"
                                        />
                                        {jpegImg}
                                    </picture>
                                ) : jpegImg;
                            })()}
                        </div>
                    </a>
                )}

                {/* Main Content */}
                <div className="p-4 sm:p-8">
                    <header className="flex flex-col-reverse items-end gap-4 sm:flex-row sm:justify-between sm:items-start mb-6">
                        <div className="flex-1 w-full">
                            <a
                                href={sourceUrl}
                                target={hasExternalSource ? "_blank" : "_self"}
                                rel={hasExternalSource ? "noopener noreferrer" : undefined}
                            >
                                <h2
                                    id={`card-title-${uid}`}
                                    className="font-serif text-2xl sm:text-3xl font-semibold text-slate-50 mb-3 cursor-pointer transition-colors hover:text-slate-100 leading-tight tracking-tight"
                                >
                                    {t('title', card.title)}
                                </h2>
                            </a>
                        </div>

                        {/* Right column: Chimera gauge + action buttons — one row
                            (gauge beside the 2×4 icon grid), not stacked. */}
                        <div className="flex flex-row items-center justify-end gap-3 flex-wrap w-full sm:w-auto">
                            {chimeraScore > 0 && (
                                <ChimeraGauge score={chimeraScore} readingLabel={readingLabel} />
                            )}

                            {/* Action Buttons: on mobile (< sm) a 4-column grid gives 2 clean
                                rows of 4 for the 8 icons — beats the pre-fix "7+1" wrap that
                                happened when 8×40 + 7×gap-2 (376px) exceeded the card's inner
                                width on iPhone 11. On sm+ the original flex layout is
                                unchanged — desktop keeps its right-aligned single-row-plus-wrap.
                                Grid → flex swap is safe because both compile to `display:`
                                and grid-template-columns / flex-wrap are ignored by the
                                inactive display mode. Tooltips (data-tooltip on children)
                                are unaffected — only the container changes. */}
                            <div className="grid grid-cols-4 gap-2 sm:flex sm:items-center sm:flex-wrap sm:justify-end print:hidden max-w-full">
                                <TranslateButton
                                    articleId={card.id}
                                    cachedLangs={(card as any).cached_langs ?? []}
                                    sourceLang={(card as any).source_lang ?? null}
                                    onTranslated={handleTranslated}
                                    onReset={handleReset}
                                    onLangChange={setCurrentLang}
                                />
                                {isPrivate && isOwner && (
                                    <span title="Private — only visible to you" aria-label="Private article" className="text-slate-500">
                                        <Lock className="h-4 w-4" aria-hidden="true" />
                                    </span>
                                )}
                                <Link
                                    href={`/article/${card.id}`}
                                    aria-label="Permalink"
                                    data-tooltip="Open Arc Codex's permanent copy of this article — every A.R.C. section expanded, ready to link or reference later."
                                    className="inline-flex items-center justify-center rounded-sm text-sm font-medium transition-colors h-10 w-10 text-slate-400 hover:text-slate-100 hover:bg-slate-800/40 ring-focus"
                                >
                                    <LinkIcon className="h-5 w-5" aria-hidden="true" />
                                </Link>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={handleCopy}
                                    className="rounded-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800/40"
                                    aria-label={hasCopied ? "Link copied" : "Copy link"}
                                    data-tooltip="Copy this article's Arc Codex permalink to your clipboard, together with a short blurb of the counter-analyst's take."
                                >
                                    {hasCopied ? <Check className="text-emerald-400" aria-hidden="true" /> : <Copy aria-hidden="true" />}
                                </Button>
                                <ResearchMenu
                                    title={translatedFields?.title ?? card.title}
                                    articleId={card.id}
                                    snippet={researchSnippet}
                                    sourceUrl={card.sourceUrl}
                                />
                                <ShareMenu
                                    title={translatedFields?.title ?? card.title}
                                    articleId={card.id}
                                    blurb={shareBlurb}
                                    lang={currentLang}
                                    counterComment={counterComment ?? undefined}
                                />
                                <a
                                    href={card.directive ? `/wiki/${toSlug(card.directive)}#article-${card.id}` : '/wiki'}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    aria-label="Full take"
                                    data-tooltip="Jump to the wiki directive page for this article's topic, showing every related story and its full analysis in one place."
                                    className="tooltip-right inline-flex items-center justify-center rounded-sm text-sm font-medium transition-colors h-10 w-10 text-slate-400 hover:text-slate-100 hover:bg-slate-800/40 ring-focus"
                                >
                                    <Flashlight className="h-5 w-5" aria-hidden="true" />
                                </a>
                                <a
                                    href={`https://soc.arc-codex.com/course/quiz-me/article/${card.id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    aria-label="Quiz me"
                                    data-tooltip="Take a quick quiz on this article at School of Chat and earn a per-article badge for reading it closely."
                                    className="tooltip-right inline-flex items-center justify-center rounded-sm text-sm font-medium transition-colors h-10 w-10 text-slate-400 hover:text-slate-100 hover:bg-slate-800/40 ring-focus"
                                >
                                    <GraduationCap className="h-5 w-5" aria-hidden="true" />
                                </a>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={(e: React.MouseEvent) => { e.stopPropagation(); window.print(); }}
                                    className="tooltip-right rounded-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800/40"
                                    aria-label="Print"
                                    data-tooltip="Expand every section and open the browser's print dialog — good for a paper copy or a clean PDF export."
                                >
                                    <Printer className="h-5 w-5" aria-hidden="true" />
                                </Button>
                            </div>
                        </div>
                    </header>

                    {/* Article Text */}
                    <div
                        className="space-y-2"
                        dir={isRTL ? 'rtl' : 'ltr'}
                        style={isRTL ? { textAlign: 'right' } : undefined}
                    >
                        {((card.original_text ?? '').includes('Video:') || (card.original_text ?? '').includes('<video')) ? (
                            <VideoList text={t('original_text', card.original_text)} />
                        ) : (
                            <AccordionText
                                text={stripLeadingTitle(
                                    t('original_text', card.original_text),
                                    t('title', card.title)
                                )}
                                characterLimit={isCompact ? 180 : 400}
                                fullyExpanded={fullyExpanded}
                            />
                        )}
                    </div>
                </div>

                {/* Analysis Sections */}
                {!isCompact && (
                    <>
                        {talkingPoints && Array.isArray(talkingPoints) && talkingPoints.length > 0 && (
                            <AnalysisSection
                                sectionId={`${uid}-talking`}
                                title="Talking Points"
                                icon={<MessageSquare className="h-4 w-4 text-slate-500" aria-hidden="true" />}
                                isExpanded={expandedSections.talkingPoints}
                                onToggle={() => toggleSection('talkingPoints')}
                                fullyExpanded={fullyExpanded}
                            >
                                <ul className="list-disc pl-5 space-y-3 text-slate-200 font-serif max-w-prose">
                                    {talkingPoints.map((point, index) => (
                                        <li key={index} className="leading-relaxed">{point}</li>
                                    ))}
                                </ul>
                            </AnalysisSection>
                        )}

                        {deepAnalysisSummary && (
                            <AnalysisSection
                                sectionId={`${uid}-deep`}
                                title="Deep Analysis"
                                icon={<BrainCircuit className="h-4 w-4 text-slate-500" aria-hidden="true" />}
                                isExpanded={expandedSections.deepAnalysis}
                                onToggle={() => toggleSection('deepAnalysis')}
                                fullyExpanded={fullyExpanded}
                            >
                                <p className="text-slate-200 font-serif leading-relaxed max-w-prose">{deepAnalysisSummary}</p>
                            </AnalysisSection>
                        )}

                        {card.red_team_analysis && (
                            <AnalysisSection
                                sectionId={`${uid}-red`}
                                title="Facts Only"
                                icon={
                                    <span className="inline-flex items-center gap-2" aria-hidden="true">
                                        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                                        <Crosshair className="h-4 w-4 text-slate-500" />
                                    </span>
                                }
                                isExpanded={expandedSections.redTeam}
                                onToggle={() => toggleSection('redTeam')}
                                fullyExpanded={fullyExpanded}
                            >
                                <AccordionText text={t('red_team_analysis', card.red_team_analysis)} characterLimit={500} fullyExpanded={fullyExpanded} />
                            </AnalysisSection>
                        )}

                        {card.blue_team_analysis && (
                            <AnalysisSection
                                sectionId={`${uid}-blue`}
                                title="Executive Summary"
                                icon={
                                    <span className="inline-flex items-center gap-2" aria-hidden="true">
                                        <span className="h-1.5 w-1.5 rounded-full bg-sky-500" />
                                        <Shield className="h-4 w-4 text-slate-500" />
                                    </span>
                                }
                                isExpanded={expandedSections.blueTeam}
                                onToggle={() => toggleSection('blueTeam')}
                                fullyExpanded={fullyExpanded}
                            >
                                <AccordionText text={t('blue_team_analysis', card.blue_team_analysis)} characterLimit={500} fullyExpanded={fullyExpanded} />
                            </AnalysisSection>
                        )}

                        {card.purple_team_analysis && (
                            <AnalysisSection
                                sectionId={`${uid}-purple`}
                                title="Full Take"
                                icon={
                                    <span className="inline-flex items-center gap-2" aria-hidden="true">
                                        <span className="h-1.5 w-1.5 rounded-full bg-violet-500" />
                                        <Combine className="h-4 w-4 text-slate-500" />
                                    </span>
                                }
                                isExpanded={expandedSections.purpleTeam}
                                onToggle={() => toggleSection('purpleTeam')}
                                fullyExpanded={fullyExpanded}
                            >
                                <AccordionText text={t('purple_team_analysis', card.purple_team_analysis)} characterLimit={500} fullyExpanded={fullyExpanded} />
                            </AnalysisSection>
                        )}

                        {sentinelData && sentinelColor && (
                            <AnalysisSection
                                sectionId={`${uid}-sentinel`}
                                title={`Sentinel — ${sentinelColor.label}`}
                                icon={<ScanLine className="h-4 w-4 text-slate-500" aria-hidden="true" />}
                                isExpanded={expandedSections.sentinel}
                                onToggle={() => toggleSection('sentinel')}
                                fullyExpanded={fullyExpanded}
                            >
                                <div className="space-y-5">
                                    <div className="flex items-center gap-3">
                                        <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 w-24 shrink-0" id={`${uid}-conf-label`}>
                                            Confidence
                                        </span>
                                        <div className="flex-1 h-px bg-slate-800 overflow-hidden">
                                            <div
                                                role="progressbar"
                                                aria-labelledby={`${uid}-conf-label`}
                                                aria-valuenow={Math.round(sentinelData.synthetic_confidence * 100)}
                                                aria-valuemin={0}
                                                aria-valuemax={100}
                                                className="h-full bg-slate-300 transition-all duration-500"
                                                style={{ width: `${Math.round(sentinelData.synthetic_confidence * 100)}%` }}
                                            />
                                        </div>
                                        <span className="font-mono text-xs font-semibold text-slate-300" aria-hidden="true">
                                            {Math.round(sentinelData.synthetic_confidence * 100)}%
                                        </span>
                                    </div>

                                    <p className="font-serif text-slate-200 leading-relaxed max-w-prose">{sentinelData.summary}</p>

                                    {sentinelData.indicators && sentinelData.indicators.length > 0 && (
                                        <div className="space-y-2">
                                            <span className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">Signals Detected</span>
                                            {sentinelData.indicators.map((ind, i) => {
                                                const sev = ind.severity?.toLowerCase();
                                                const dotShade =
                                                    sev === 'high' ? 'bg-slate-200'
                                                    : sev === 'medium' ? 'bg-slate-400'
                                                    : 'bg-slate-600';
                                                return (
                                                    <div key={i} className="flex items-start gap-2 text-sm">
                                                        <span className={`mt-1.5 h-1.5 w-1.5 rounded-full shrink-0 ${dotShade}`} aria-hidden="true" />
                                                        <span className="text-slate-300">
                                                            <span className="sr-only">{ind.severity} severity: </span>
                                                            <span className="font-sans text-[10px] uppercase tracking-widest text-slate-500 mr-2" aria-hidden="true">[{ind.severity}]</span>
                                                            <span className="font-sans text-slate-500 capitalize" aria-hidden="true">{ind.dimension}:</span>
                                                            {' '}<span className="font-serif">{ind.signal}</span>
                                                        </span>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}

                                    {sentinelData.human_signals && sentinelData.human_signals.length > 0 && (
                                        <div className="space-y-2">
                                            <span className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">Human Indicators</span>
                                            {sentinelData.human_signals.map((signal, i) => (
                                                <div key={i} className="flex items-start gap-2 text-sm">
                                                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full shrink-0 bg-emerald-500" aria-hidden="true" />
                                                    <span className="font-serif text-slate-300">{signal}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </AnalysisSection>
                        )}
                    </>
                )}

                {/* Comments */}
                {!isCompact ? (
                    <div className="px-4 sm:px-8 pb-8 pt-6 border-t border-slate-800">
                        <CommentSection comments={comments} articleId={card.id} />
                    </div>
                ) : comments.length > 0 ? (
                    <a href={`/article/${card.id}`} className="block px-4 sm:px-8 pb-3 group">
                        <div className="flex items-center gap-2 font-sans text-xs uppercase tracking-[0.2em] text-slate-500 group-hover:text-slate-200 transition-colors cursor-pointer">
                            <MessageSquare className="h-4 w-4" aria-hidden="true" />
                            <span>{comments.length} Comment{comments.length !== 1 ? 's' : ''}</span>
                        </div>
                    </a>
                ) : null}

                {/* Footer */}
                <div className="border-t border-slate-800" aria-hidden="true" />
                <footer className="flex justify-between items-center px-4 sm:px-8 py-5 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
                    <time dateTime={card.timestamp}>{formattedDate}</time>
                    {card.directive ? (
                        <Link
                            href={`/wiki/${toSlug(card.directive)}`}
                            className="font-semibold text-slate-500 hover:text-slate-200 transition-colors duration-200"
                            aria-label={`View ${card.directive} in wiki`}
                        >
                            {card.directive}
                        </Link>
                    ) : null}
                </footer>
            </div>
        </article>
    );
};

export default React.memo(IntelligenceCard, (prev, next) =>
    prev.card.id === next.card.id &&
    prev.comments.length === next.comments.length &&
    prev.isCompact === next.isCompact &&
    prev.fullyExpanded === next.fullyExpanded
);