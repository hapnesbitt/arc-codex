// Filename: /frontend/components/IntelligenceCard.tsx
// Version 7.0 - Accessibility pass
// Changes from v6.0:
// - Card root changed from motion.div to <article> (correct semantic element)
// - AnalysisSection: aria-expanded + aria-controls on toggle button
// - AccordionText: aria-expanded on Read More button
// - ChimeraScoreGauge: aria-hidden on SVG, visually-hidden score label for AT
// - Article image: alt="" (decorative — title already in adjacent h2)
// - ShareMenu: aria-expanded, aria-haspopup, focus returns to trigger on close
// - Sentinel confidence bar: role=progressbar with aria-valuenow/min/max/label
// - Sentinel severity/human dots: aria-hidden, severity surfaced as sr-only text
// - All decorative icons: aria-hidden="true"
// - Copy button: aria-label updates on copied state
// - Video links: aria-label includes "Play video:"
// - Comments compact link: icon aria-hidden

'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import Link from 'next/link';
import { AnimatePresence, motion } from 'framer-motion';
import {
    Link as LinkIcon,
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
    ScanLine
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card as ShadCard } from "@/components/ui/card";
import CommentSection from '@/components/CommentSection';
import TranslateButton, { TranslatedFields } from '@/components/TranslateButton';
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
}

interface AccordionTextProps {
    text: string;
    characterLimit?: number;
}

interface ChimeraScoreGaugeProps {
    score: number;
}

interface AnalysisSectionProps {
    title: string;
    icon: React.ReactNode;
    children: React.ReactNode;
    isExpanded: boolean;
    onToggle: () => void;
    /** Unique id used to wire aria-controls → content region */
    sectionId: string;
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
const plainTextToHtml = (text: string): string => {
    if (!text.includes('\n')) return linkifyText(text);
    const paragraphs = text.split(/\n{2,}/);
    return paragraphs
        .map(para => {
            const trimmed = para.trim();
            if (!trimmed) return '';
            const withBreaks = trimmed.split('\n').map(line => linkifyText(line)).join('<br>');
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
            return `<a href="${clean}" target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:text-blue-300 underline break-all">${clean}</a>`;
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
                1: 'text-2xl font-bold text-amber-200 mt-6 mb-3',
                2: 'text-xl font-bold text-amber-300 mt-5 mb-3',
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
            html.push(`<blockquote class="border-l-2 border-amber-400/50 pl-4 italic text-slate-400 my-3">${content}</blockquote>`);
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

// --- Helper: Text with "Read More" Accordion ---
const AccordionText: React.FC<AccordionTextProps> = ({ text, characterLimit = 400 }) => {
    const [isExpanded, setIsExpanded] = useState<boolean>(false);

    const { plainText, needsTruncation, fullHtml } = useMemo(() => {
        const cleanText = safeText(text);
        const isMarkdown = hasMarkdown(cleanText);
        const plainText = isMarkdown ? stripMarkdown(cleanText) : cleanText;
        const fullHtml = isMarkdown ? markdownToHtml(cleanText) : plainTextToHtml(cleanText);
        return { plainText, needsTruncation: plainText.length > characterLimit, fullHtml };
    }, [text, characterLimit]);

    if (!needsTruncation) {
        return (
            <div
                className="prose prose-invert max-w-none text-slate-300 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: fullHtml }}
            />
        );
    }

    const toggleExpansion = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsExpanded(!isExpanded);
    };

    const displayHtml = isExpanded
        ? fullHtml
        : linkifyText(`${plainText.slice(0, characterLimit)}...`);

    return (
        <div>
            <div
                className="prose prose-invert max-w-none text-slate-300 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: displayHtml }}
            />
            <button
                onClick={toggleExpansion}
                aria-expanded={isExpanded}
                className="text-amber-400 hover:text-amber-300 font-semibold mt-3 transition-colors text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50 rounded"
            >
                {isExpanded ? "Show Less" : "Read More"}
            </button>
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
                            className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 border border-slate-700/50 hover:border-amber-400/50 hover:bg-slate-800/80 transition-all duration-300 group"
                        >
                            <PlayCircle className="h-5 w-5 text-amber-400 flex-shrink-0 group-hover:text-amber-300 group-hover:scale-110 transition-all" aria-hidden="true" />
                            <span className="text-slate-200 group-hover:text-amber-300 transition-colors font-medium" aria-hidden="true">
                                {videoName}
                            </span>
                        </a>
                    );
                } else if (line.trim()) {
                    const linkedLine = linkifyText(line);
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

// --- Holographic Score Gauge ---
// aria-hidden on the SVG — the score value is surfaced as a visually-hidden
// text label so AT users get "Tone score: 74" not SVG path noise.
const ChimeraScoreGauge: React.FC<ChimeraScoreGaugeProps> = ({ score }) => {
    const circumference = 2 * Math.PI * 20;
    const strokeDashoffset = circumference - (score * circumference);
    const scoreColor = score >= 0.75 ? '#6ee7b7' : score >= 0.4 ? '#fcd34d' : '#fda4af';
    const scorePercent = Math.round(score * 100);

    return (
        <div className="relative h-16 w-16 flex items-center justify-center">
            {/* Visually hidden label for screen readers */}
            <span className="sr-only">Tone score: {scorePercent}</span>
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
            {/* Visual number — aria-hidden since sr-only label above covers it */}
            <div
                className="absolute font-mono text-base font-bold"
                style={{ color: scoreColor, textShadow: `0 0 6px ${scoreColor}` }}
                aria-hidden="true"
            >
                {scorePercent}
            </div>
        </div>
    );
};

// --- Collapsible Analysis Section ---
// aria-expanded on toggle button, aria-controls linking to content region.
const AnalysisSection: React.FC<AnalysisSectionProps> = ({
    title,
    icon,
    children,
    isExpanded,
    onToggle,
    sectionId,
}) => {
    const contentId = `${sectionId}-content`;
    return (
        <div className="border-t border-slate-700/50">
            <button
                onClick={onToggle}
                aria-expanded={isExpanded}
                aria-controls={contentId}
                className="w-full flex justify-between items-center p-5 text-left hover:bg-slate-800/50 transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-400/40"
            >
                <div className="flex items-center gap-3">
                    <div className="transition-transform group-hover:scale-110" aria-hidden="true">
                        {icon}
                    </div>
                    <h3 className="font-semibold text-slate-200 text-base tracking-wide">
                        {title}
                    </h3>
                </div>
                <ChevronDown
                    className={`h-5 w-5 text-slate-400 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}
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
                        <div className="px-5 pb-5 pt-0">
                            {children}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

// --- Share Menu ---
// aria-expanded + aria-haspopup on trigger, focus returns to trigger on close.
const ShareMenu: React.FC<{ title: string; articleId: string; blurb?: string; lang?: string | null; counterComment?: string }> = ({
    title,
    articleId,
    blurb,
    lang,
    counterComment,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [copied, setCopied] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const baseUrl = `https://arc-codex.com/article/${articleId}`;
    const fullUrl = lang ? `${baseUrl}?lang=${encodeURIComponent(lang)}` : baseUrl;
    // Share payload: title + counter-analyst comment (if available) + URL
    const sharePayload = counterComment
        ? `${title}\n\n${counterComment}\n\n${fullUrl}`
        : `${title}\n\n${fullUrl}`;
    const shareText = blurb || 'Read this on Arc Codex';

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

    const handleCopyLink = (e: React.MouseEvent) => {
        e.stopPropagation();
        navigator.clipboard.writeText(sharePayload);
        setCopied(true);
        setTimeout(() => { setCopied(false); close(); }, 1500);
    };

    const handleTwitter = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(sharePayload)}&url=${encodeURIComponent(fullUrl)}`, '_blank', 'width=600,height=400');
        close();
    };

    const handleFacebook = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(`https://www.facebook.com/sharer.php?u=${encodeURIComponent(fullUrl)}`, '_blank', 'width=600,height=400');
        close();
    };

    const handleLinkedIn = (e: React.MouseEvent) => {
        e.stopPropagation();
        navigator.clipboard.writeText(sharePayload).catch(() => {});
        window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(fullUrl)}`, '_blank', 'width=600,height=600');
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
                aria-label="Share article"
                aria-expanded={isOpen}
                aria-haspopup="menu"
                className="text-slate-400 hover:text-blue-400 hover:bg-white/10"
            >
                <Share2 className="h-5 w-5" aria-hidden="true" />
            </Button>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        role="menu"
                        aria-label="Share options"
                        initial={{ opacity: 0, scale: 0.95, y: -4 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: -4 }}
                        transition={{ duration: 0.15 }}
                        className="absolute right-0 top-full mt-2 z-50 w-48 rounded-xl border border-slate-700/80 bg-slate-900/95 backdrop-blur-xl shadow-2xl shadow-black/40 overflow-hidden"
                    >
                        <button
                            role="menuitem"
                            onClick={handleCopyLink}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors focus-visible:outline-none focus-visible:bg-slate-800/80"
                        >
                            {copied ? (
                                <Check className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                            ) : (
                                <Copy className="h-4 w-4 text-slate-400" aria-hidden="true" />
                            )}
                            <span>{copied ? 'Copied!' : 'Copy Link'}</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleTwitter}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors focus-visible:outline-none focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-slate-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                            </svg>
                            <span>Post on X</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleFacebook}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors focus-visible:outline-none focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-blue-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                            </svg>
                            <span>Share on Facebook</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleLinkedIn}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors focus-visible:outline-none focus-visible:bg-slate-800/80"
                        >
                            <svg className="h-4 w-4 text-blue-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                            </svg>
                            <span>Share on LinkedIn</span>
                        </button>
                        <button
                            role="menuitem"
                            onClick={handleEmail}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors focus-visible:outline-none focus-visible:bg-slate-800/80"
                        >
                            <Mail className="h-4 w-4 text-amber-400" aria-hidden="true" />
                            <span>Send via Email</span>
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
}) => {
    const [hasCopied, setHasCopied] = useState<boolean>(false);
    const [translatedFields, setTranslatedFields] = useState<TranslatedFields | null>(null);
    const [isRTL, setIsRTL] = useState(false);
    const [currentLang, setCurrentLang] = useState<string | null>(null);
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? '';

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
            } catch { /* silent — fall back to original */ }
        };
        fetchInitialLang();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialLang]);

    const t = <K extends keyof TranslatedFields>(field: K, original: string): string =>
        translatedFields?.[field] ?? original;

    const [expandedSections, setExpandedSections] = useState<ExpandedSections>({
        talkingPoints: false,
        deepAnalysis: false,
        redTeam: false,
        blueTeam: false,
        purpleTeam: false,
        sentinel: false,
    });

    const sourceName = card.source_name || card.source || 'Unknown Source';
    const isManualUpload = sourceName === 'Manual Upload';
    const articleUrl = `/article/${card.id}`;

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
        const base = `https://arc-codex.com/article/${card.id}`;
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

    const score = dossier?.chimera_score || 0;
    const talkingPoints = dossier?.talking_points;
    const deepAnalysisSummary = dossier?.deep_analysis_summary;

    const shareBlurb = card.purple_team_analysis?.substring(0, 200)
        || card.blue_team_analysis?.substring(0, 200)
        || 'Read this on Arc Codex';

    // Counter-Analyst comment for share payload — normalize "The article" → "This article"
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
        if (conf <= 0.6) return { bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', text: 'text-emerald-400', label: 'Human' };
        if (conf <= 0.7) return { bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', text: 'text-emerald-300', label: 'Likely Human' };
        if (conf <= 0.8) return { bg: 'bg-amber-500/15', border: 'border-amber-500/30', text: 'text-amber-400', label: 'Uncertain' };
        if (conf <= 0.9) return { bg: 'bg-orange-500/15', border: 'border-orange-500/30', text: 'text-orange-400', label: 'Likely Synthetic' };
        return { bg: 'bg-red-500/15', border: 'border-red-500/30', text: 'text-red-400', label: 'Synthetic' };
    }, [sentinelData]);

    if (!card) return null;

    // Unique prefix for aria-controls wiring on this card instance
    const uid = card.id;

    return (
        // <article> is the correct semantic element for a self-contained piece of content.
        // aria-labelledby points to the h2 title so AT announces "Article: [title]"
        // when navigating by landmarks.
        <motion.article
            aria-labelledby={`card-title-${uid}`}
            initial={{ opacity: 0, y: 50, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full max-w-2xl mx-auto"
        >
            <div className="group relative w-full h-full rounded-2xl overflow-hidden border border-slate-700/80 bg-slate-900/40 backdrop-blur-lg shadow-2xl shadow-black/30">
                {/* Hover border effect — decorative */}
                <div className="absolute inset-0 border-2 rounded-2xl border-transparent group-hover:border-amber-300/50 transition-colors duration-300 pointer-events-none z-10" aria-hidden="true" />

                {/* Article Image — alt="" because title h2 adjacent covers it */}
                {card.imageUrl && (
                    <a
                        href={sourceUrl}
                        target={hasExternalSource ? "_blank" : "_self"}
                        rel={hasExternalSource ? "noopener noreferrer" : undefined}
                        tabIndex={-1}
                        aria-hidden="true"
                    >
                        <div className="w-full h-64 bg-slate-950 overflow-hidden">
                            <img
                                src={card.imageUrl}
                                alt=""
                                className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                            />
                        </div>
                    </a>
                )}

                {/* Main Content */}
                <div className="p-6">
                    <header className="flex flex-col-reverse items-end gap-4 sm:flex-row sm:justify-between sm:items-start mb-6">
                        <div className="flex-1">
                            <a
                                href={sourceUrl}
                                target={hasExternalSource ? "_blank" : "_self"}
                                rel={hasExternalSource ? "noopener noreferrer" : undefined}
                            >
                                <h2
                                    id={`card-title-${uid}`}
                                    className="font-serif text-2xl font-bold text-slate-50 mb-3 cursor-pointer group-hover:text-amber-300 transition-colors hover:text-amber-300 leading-tight"
                                >
                                    {t('title', card.title)}
                                </h2>
                            </a>

                            <div className="mt-2">
                                <TranslateButton
                                    articleId={card.id}
                                    cachedLangs={(card as any).cached_langs ?? []}
                                    onTranslated={handleTranslated}
                                    onReset={handleReset}
                                    onLangChange={setCurrentLang}
                                />
                            </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-2">
                            <Link href={articleUrl} passHref legacyBehavior>
                                <a
                                    aria-label="Permalink to this article"
                                    className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors h-10 w-10 text-slate-400 hover:text-white hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
                                >
                                    <LinkIcon className="h-5 w-5" aria-hidden="true" />
                                </a>
                            </Link>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={handleCopy}
                                className="text-slate-400 hover:text-white hover:bg-white/10"
                                aria-label={hasCopied ? "Link copied" : "Copy article link"}
                            >
                                {hasCopied
                                    ? <Check className="text-emerald-400" aria-hidden="true" />
                                    : <Copy aria-hidden="true" />
                                }
                            </Button>
                            <ShareMenu
                                title={translatedFields?.title ?? card.title}
                                articleId={card.id}
                                blurb={shareBlurb}
                                lang={currentLang}
                                counterComment={counterComment ?? undefined}
                            />
                        </div>
                    </header>

                    {/* Article Text */}
                    <div
                        className="space-y-2"
                        dir={isRTL ? 'rtl' : 'ltr'}
                        style={isRTL ? { textAlign: 'right' } : undefined}
                    >
                        {(card.original_text.includes('Video:') || card.original_text.includes('<video')) ? (
                            <VideoList text={t('original_text', card.original_text)} />
                        ) : (
                            <AccordionText
                                text={t('original_text', card.original_text)}
                                characterLimit={isCompact ? 180 : 400}
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
                                icon={<MessageSquare className="h-5 w-5 text-amber-400" aria-hidden="true" />}
                                isExpanded={expandedSections.talkingPoints}
                                onToggle={() => toggleSection('talkingPoints')}
                            >
                                <ul className="list-disc pl-5 space-y-2 text-slate-300 font-serif">
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
                                icon={<BrainCircuit className="h-5 w-5 text-amber-400" aria-hidden="true" />}
                                isExpanded={expandedSections.deepAnalysis}
                                onToggle={() => toggleSection('deepAnalysis')}
                            >
                                <p className="text-slate-300 font-serif leading-relaxed">{deepAnalysisSummary}</p>
                            </AnalysisSection>
                        )}

                        {card.red_team_analysis && (
                            <AnalysisSection
                                sectionId={`${uid}-red`}
                                title="Facts Only"
                                icon={<Crosshair className="h-5 w-5 text-red-400" aria-hidden="true" />}
                                isExpanded={expandedSections.redTeam}
                                onToggle={() => toggleSection('redTeam')}
                            >
                                <AccordionText text={t('red_team_analysis', card.red_team_analysis)} characterLimit={500} />
                            </AnalysisSection>
                        )}

                        {card.blue_team_analysis && (
                            <AnalysisSection
                                sectionId={`${uid}-blue`}
                                title="Executive Summary"
                                icon={<Shield className="h-5 w-5 text-blue-400" aria-hidden="true" />}
                                isExpanded={expandedSections.blueTeam}
                                onToggle={() => toggleSection('blueTeam')}
                            >
                                <AccordionText text={t('blue_team_analysis', card.blue_team_analysis)} characterLimit={500} />
                            </AnalysisSection>
                        )}

                        {card.purple_team_analysis && (
                            <AnalysisSection
                                sectionId={`${uid}-purple`}
                                title="Full Take"
                                icon={<Combine className="h-5 w-5 text-purple-400" aria-hidden="true" />}
                                isExpanded={expandedSections.purpleTeam}
                                onToggle={() => toggleSection('purpleTeam')}
                            >
                                <AccordionText text={t('purple_team_analysis', card.purple_team_analysis)} characterLimit={500} />
                            </AnalysisSection>
                        )}

                        {sentinelData && sentinelColor && (
                            <AnalysisSection
                                sectionId={`${uid}-sentinel`}
                                title={`Sentinel — ${sentinelColor.label}`}
                                icon={<ScanLine className={`h-5 w-5 ${sentinelColor.text}`} aria-hidden="true" />}
                                isExpanded={expandedSections.sentinel}
                                onToggle={() => toggleSection('sentinel')}
                            >
                                <div className="space-y-4">
                                    {/* Confidence bar — role=progressbar with accessible value */}
                                    <div className="flex items-center gap-3">
                                        <span className="text-xs text-slate-500 w-24 shrink-0" id={`${uid}-conf-label`}>
                                            Confidence
                                        </span>
                                        <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                                            <div
                                                role="progressbar"
                                                aria-labelledby={`${uid}-conf-label`}
                                                aria-valuenow={Math.round(sentinelData.synthetic_confidence * 100)}
                                                aria-valuemin={0}
                                                aria-valuemax={100}
                                                className={`h-full rounded-full transition-all duration-500 ${
                                                    sentinelData.synthetic_confidence <= 0.4 ? 'bg-emerald-500' :
                                                    sentinelData.synthetic_confidence <= 0.6 ? 'bg-amber-500' : 'bg-red-500'
                                                }`}
                                                style={{ width: `${Math.round(sentinelData.synthetic_confidence * 100)}%` }}
                                            />
                                        </div>
                                        <span className={`text-sm font-mono font-bold ${sentinelColor.text}`} aria-hidden="true">
                                            {Math.round(sentinelData.synthetic_confidence * 100)}%
                                        </span>
                                    </div>

                                    <p className="text-slate-300 leading-relaxed">{sentinelData.summary}</p>

                                    {sentinelData.indicators && sentinelData.indicators.length > 0 && (
                                        <div className="space-y-2">
                                            <span className="text-xs text-slate-500 uppercase tracking-wider">Signals Detected</span>
                                            {sentinelData.indicators.map((ind, i) => (
                                                <div key={i} className="flex items-start gap-2 text-sm">
                                                    {/* Colored dot is decorative — severity surfaced as sr-only text */}
                                                    <span
                                                        className={`mt-0.5 h-2 w-2 rounded-full shrink-0 ${
                                                            ind.severity === 'high' ? 'bg-red-400' :
                                                            ind.severity === 'medium' ? 'bg-amber-400' : 'bg-slate-500'
                                                        }`}
                                                        aria-hidden="true"
                                                    />
                                                    <span className="text-slate-400">
                                                        <span className="sr-only">{ind.severity} severity: </span>
                                                        <span className="text-slate-500 capitalize" aria-hidden="true">{ind.dimension}:</span>
                                                        {' '}{ind.signal}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {sentinelData.human_signals && sentinelData.human_signals.length > 0 && (
                                        <div className="space-y-2">
                                            <span className="text-xs text-slate-500 uppercase tracking-wider">Human Indicators</span>
                                            {sentinelData.human_signals.map((signal, i) => (
                                                <div key={i} className="flex items-start gap-2 text-sm">
                                                    <span className="mt-0.5 h-2 w-2 rounded-full shrink-0 bg-emerald-400" aria-hidden="true" />
                                                    <span className="text-slate-400">{signal}</span>
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
                    <div className="px-6 pb-6 pt-4">
                        <CommentSection comments={comments} articleId={card.id} />
                    </div>
                ) : comments.length > 0 ? (
                    <a href={`/article/${card.id}`} className="block px-6 pb-2 group">
                        <div className="flex items-center gap-2 text-slate-400 text-sm group-hover:text-amber-300 transition-colors cursor-pointer">
                            <MessageSquare className="h-4 w-4" aria-hidden="true" />
                            <span>{comments.length} Comment{comments.length !== 1 ? 's' : ''}</span>
                        </div>
                    </a>
                ) : null}

                {/* Footer */}
                <div className="border-t border-slate-700/50" aria-hidden="true" />
                <footer className="flex justify-between items-center text-xs text-slate-500 p-4">
                    <time dateTime={card.timestamp}>{formattedDate}</time>
                    <span className="font-semibold uppercase tracking-wider">{card.directive}</span>
                </footer>
            </div>
        </motion.article>
    );
};

export default React.memo(IntelligenceCard, (prev, next) =>
    prev.card.id === next.card.id &&
    prev.comments.length === next.comments.length &&
    prev.isCompact === next.isCompact
);
