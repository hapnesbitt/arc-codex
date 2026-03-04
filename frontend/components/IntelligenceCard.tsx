// Filename: /frontend/components/IntelligenceCard.tsx
// Version 6.0 - Desktop share menu, mobile native share, type fixes, threaded replies

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
        // Remove 'www.' prefix for cleaner display
        return hostname.replace(/^www\./, '');
    } catch {
        return 'External Source';
    }
};

// --- Helper: Convert plain text with newlines to HTML paragraphs ---
const plainTextToHtml = (text: string): string => {
    // No newlines at all — just linkify and return
    if (!text.includes('\n')) return linkifyText(text);
    
    // Split on double-newlines for paragraphs
    const paragraphs = text.split(/\n{2,}/);
    
    return paragraphs
        .map(para => {
            const trimmed = para.trim();
            if (!trimmed) return '';
            // Convert remaining single newlines to <br> within paragraphs
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

// --- Helper: Detect if text contains markdown STRUCTURE (headings, rules, blockquotes) ---
// Only triggers on structural patterns, not just **bold** in normal prose
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

        // Empty line — close list if open, add spacing
        if (!trimmed) {
            if (inList) { html.push('</ul>'); inList = false; }
            html.push('<div class="h-3"></div>');
            continue;
        }

        // Horizontal rule
        if (/^---+$/.test(trimmed)) {
            if (inList) { html.push('</ul>'); inList = false; }
            html.push('<hr class="border-slate-600/50 my-4" />');
            continue;
        }

        // Headings (h1-h6)
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

        // Blockquote
        if (trimmed.startsWith('> ')) {
            if (inList) { html.push('</ul>'); inList = false; }
            const content = inlineFormat(escapeHtml(trimmed.slice(2)));
            html.push(`<blockquote class="border-l-2 border-amber-400/50 pl-4 italic text-slate-400 my-3">${content}</blockquote>`);
            continue;
        }

        // List items (- or *)
        const listMatch = trimmed.match(/^[-*]\s+(.*)/);
        if (listMatch) {
            if (!inList) { html.push('<ul class="my-3 space-y-1.5 list-disc ml-6">'); inList = true; }
            html.push(`<li class="text-slate-300">${inlineFormat(escapeHtml(listMatch[1]))}</li>`);
            continue;
        }

        // Regular paragraph
        if (inList) { html.push('</ul>'); inList = false; }
        html.push(`<p class="mb-3 text-slate-300 leading-relaxed">${inlineFormat(escapeHtml(trimmed))}</p>`);
    }

    if (inList) html.push('</ul>');
    return html.join('\n');
};

// --- Helper: Text with "Read More" Accordion (WITH MARKDOWN RENDERING) ---
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
                className="text-amber-400 hover:text-amber-300 font-semibold mt-3 transition-colors text-sm"
            >
                {isExpanded ? "Show Less" : "Read More"}
            </button>
        </div>
    );
};

// --- Video List Component (styled video links with play icons) ---
const VideoList: React.FC<{ text: string }> = ({ text }) => {
    const lines = text.split('\n');
    
    return (
        <div className="space-y-3">
            {lines.map((line, index) => {
                // Check if this line is a video
                if (line.trim().startsWith('Video:')) {
                    // Extract video filename and clean it
                    const videoPath = line.replace('Video:', '').trim();
                    // Remove any video extension more aggressively
                    const videoName = videoPath
                        .replace(/\.(mkv|mp4|webm|avi|mov|flv|wmv|m4v)$/i, '')
                        .trim();
                    
                    return (
                        <a
                            key={index}
                            href={`/videos/${encodeURIComponent(videoPath)}`}
                            className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 border border-slate-700/50 hover:border-amber-400/50 hover:bg-slate-800/80 transition-all duration-300 group"
                        >
                            <PlayCircle className="h-5 w-5 text-amber-400 flex-shrink-0 group-hover:text-amber-300 group-hover:scale-110 transition-all" />
                            <span className="text-slate-200 group-hover:text-amber-300 transition-colors font-medium">
                                {videoName}
                            </span>
                        </a>
                    );
                } else if (line.trim()) {
                    // Regular text line - linkify it
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
const ChimeraScoreGauge: React.FC<ChimeraScoreGaugeProps> = ({ score }) => {
    const circumference = 2 * Math.PI * 20;
    const strokeDashoffset = circumference - (score * circumference);
    const scoreColor = score >= 0.75 ? '#6ee7b7' : score >= 0.4 ? '#fcd34d' : '#fda4af';
    
    return (
        <div className="relative h-16 w-16 flex items-center justify-center">
            <svg 
                className="absolute inset-0" 
                viewBox="0 0 48 48" 
                style={{ transform: 'rotate(-90deg)' }}
            >
                <circle 
                    cx="24" 
                    cy="24" 
                    r="20" 
                    stroke="#e2e8f0" 
                    strokeOpacity="0.1" 
                    strokeWidth="3" 
                    fill="transparent" 
                />
                <motion.circle 
                    cx="24" 
                    cy="24" 
                    r="20" 
                    stroke={scoreColor} 
                    strokeWidth="3" 
                    fill="transparent" 
                    strokeLinecap="round" 
                    strokeDasharray={circumference} 
                    initial={{ strokeDashoffset: circumference }} 
                    animate={{ strokeDashoffset }} 
                    transition={{ duration: 1.5, ease: [0.43, 0.13, 0.23, 0.96] }} 
                />
            </svg>
            <div 
                className="absolute font-mono text-base font-bold" 
                style={{ color: scoreColor, textShadow: `0 0 6px ${scoreColor}` }}
            >
                {Math.round(score * 100)}
            </div>
        </div>
    );
};

// --- Collapsible Analysis Section ---
const AnalysisSection: React.FC<AnalysisSectionProps> = ({ 
    title, 
    icon, 
    children, 
    isExpanded, 
    onToggle 
}) => (
    <div className="border-t border-slate-700/50">
        <button 
            onClick={onToggle} 
            className="w-full flex justify-between items-center p-5 text-left hover:bg-slate-800/50 transition-colors group"
        >
            <div className="flex items-center gap-3">
                <div className="transition-transform group-hover:scale-110">
                    {icon}
                </div>
                <h3 className="font-semibold text-slate-200 text-base tracking-wide">
                    {title}
                </h3>
            </div>
            <ChevronDown 
                className={`h-5 w-5 text-slate-400 transition-transform duration-300 ${
                    isExpanded ? 'rotate-180' : ''
                }`} 
            />
        </button>
        <AnimatePresence>
            {isExpanded && (
                <motion.div 
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

// --- Share Menu Component (desktop dropdown, mobile native share) ---
const ShareMenu: React.FC<{ title: string; articleId: string; blurb?: string; lang?: string | null }> = ({ 
    title, 
    articleId, 
    blurb,
    lang,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [copied, setCopied] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);
    const baseUrl = `https://arc-codex.com/article/${articleId}`;
    const fullUrl = lang ? `${baseUrl}?lang=${encodeURIComponent(lang)}` : baseUrl;
    const shareText = blurb || 'Read this on Arc Codex';

    // Close menu on outside click
    useEffect(() => {
        if (!isOpen) return;
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen]);

    // Close on Escape
    useEffect(() => {
        if (!isOpen) return;
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setIsOpen(false);
        };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [isOpen]);

    const handleShare = (e: React.MouseEvent) => {
        e.stopPropagation();
        
        // Mobile: use native share sheet
        if (navigator.share) {
            navigator.share({
                title,
                text: shareText,
                url: fullUrl
            }).catch(() => {});
            return;
        }
        
        // Desktop: toggle dropdown menu
        setIsOpen(prev => !prev);
    };

    const handleCopyLink = (e: React.MouseEvent) => {
        e.stopPropagation();
        navigator.clipboard.writeText(`${title}\n${fullUrl}`);
        setCopied(true);
        setTimeout(() => { setCopied(false); setIsOpen(false); }, 1500);
    };

    const handleTwitter = (e: React.MouseEvent) => {
        e.stopPropagation();
        const text = encodeURIComponent(title);
        const url = encodeURIComponent(fullUrl);
        window.open(`https://x.com/intent/tweet?text=${text}&url=${url}`, '_blank', 'width=600,height=400');
        setIsOpen(false);
    };

    const handleFacebook = (e: React.MouseEvent) => {
        e.stopPropagation();
        const url = encodeURIComponent(fullUrl);
        window.open(`https://www.facebook.com/sharer.php?u=${url}`, '_blank', 'width=600,height=400');
        setIsOpen(false);
    };

    const handleEmail = (e: React.MouseEvent) => {
        e.stopPropagation();
        const subject = encodeURIComponent(title);
        const body = encodeURIComponent(`${title}\n\n${fullUrl}`);
        window.location.href = `mailto:?subject=${subject}&body=${body}`;
        setIsOpen(false);
    };

    return (
        <div className="relative" ref={menuRef}>
            <Button 
                variant="ghost" 
                size="icon" 
                onClick={handleShare} 
                className="text-slate-400 hover:text-blue-400 hover:bg-white/10" 
                aria-label="Share article"
            >
                <Share2 className="h-5 w-5" />
            </Button>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: -4 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: -4 }}
                        transition={{ duration: 0.15 }}
                        className="absolute right-0 top-full mt-2 z-50 w-48 rounded-xl border border-slate-700/80 bg-slate-900/95 backdrop-blur-xl shadow-2xl shadow-black/40 overflow-hidden"
                    >
                        <button
                            onClick={handleCopyLink}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors"
                        >
                            {copied ? (
                                <Check className="h-4 w-4 text-emerald-400" />
                            ) : (
                                <Copy className="h-4 w-4 text-slate-400" />
                            )}
                            <span>{copied ? 'Copied!' : 'Copy Link'}</span>
                        </button>
                        <button
                            onClick={handleTwitter}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors"
                        >
                            <svg className="h-4 w-4 text-slate-400" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                            </svg>
                            <span>Post on X</span>
                        </button>
                        <button
                            onClick={handleFacebook}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors"
                        >
                            <svg className="h-4 w-4 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                            </svg>
                            <span>Share on Facebook</span>
                        </button>
                        <button
                            onClick={handleEmail}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white transition-colors"
                        >
                            <Mail className="h-4 w-4 text-amber-400" />
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

    // Auto-fetch translation when ?lang= param is present on load
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
    // Use translated value when available, otherwise fall back to original
    const t = <K extends keyof TranslatedFields>(field: K, original: string): string =>
        translatedFields?.[field] ?? original;
    
    // All sections collapsed by default
    const [expandedSections, setExpandedSections] = useState<ExpandedSections>({
        talkingPoints: false, 
        deepAnalysis: false,
        redTeam: false,
        blueTeam: false,
        purpleTeam: false,
        sentinel: false,
    });

    // Get source name - prefer source_name, fallback to source for backward compatibility
    const sourceName = card.source_name || card.source || 'Unknown Source';
    const isManualUpload = sourceName === 'Manual Upload';
    const articleUrl = `/article/${card.id}`;
    
    // Determine the display source
    const hasExternalSource = isManualUpload && card.sourceUrl && card.sourceUrl.trim() !== '';
    const displaySource = hasExternalSource 
        ? extractDomain(card.sourceUrl!) 
        : sourceName;
    const sourceUrl = hasExternalSource 
        ? card.sourceUrl! 
        : (isManualUpload ? articleUrl : (card.sourceUrl || '#'));

    const dossier = useMemo<Dossier>(() => {
        if (!card?.dossier) return {};
        try { 
            return typeof card.dossier === 'string' 
                ? JSON.parse(card.dossier) 
                : card.dossier; 
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
        const shareText = `${translatedFields?.title ?? card.title}
${fullArticleUrl}`;
        navigator.clipboard.writeText(shareText);
        setHasCopied(true);
        setTimeout(() => setHasCopied(false), 2000);
    };

    const toggleSection = (section: keyof ExpandedSections) => {
        setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
    };

    const score = dossier?.chimera_score || 0;
    const talkingPoints = dossier?.talking_points;
    const deepAnalysisSummary = dossier?.deep_analysis_summary;

    // Share blurb: first 200 chars of purple or blue analysis
    const shareBlurb = card.purple_team_analysis?.substring(0, 200) 
        || card.blue_team_analysis?.substring(0, 200) 
        || 'Read this on Arc Codex';

    // Parse sentinel analysis JSON
    const sentinelData = useMemo<SentinelData | null>(() => {
        if (!card?.sentinel_analysis) return null;
        try {
            const parsed = typeof card.sentinel_analysis === 'string'
                ? JSON.parse(card.sentinel_analysis)
                : card.sentinel_analysis;
            // Validate required fields
            if (parsed.synthetic_confidence !== undefined && parsed.assessment && parsed.summary) {
                return parsed;
            }
            return null;
        } catch (e) {
            console.error("Failed to parse sentinel data:", e);
            return null;
        }
    }, [card?.sentinel_analysis]);

    // Sentinel badge color based on confidence level
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

    return (
        <>
        <motion.div 
                initial={{ opacity: 0, y: 50, scale: 0.98 }} 
                animate={{ opacity: 1, y: 0, scale: 1 }} 
                transition={{ duration: 0.5, ease: "easeOut" }} 
                className="w-full max-w-2xl mx-auto"
            >
                <div className="group relative w-full h-full rounded-2xl overflow-hidden border border-slate-700/80 bg-slate-900/40 backdrop-blur-lg shadow-2xl shadow-black/30">
                    {/* Hover border effect */}
                    <div className="absolute inset-0 border-2 rounded-2xl border-transparent group-hover:border-amber-300/50 transition-colors duration-300 pointer-events-none z-10" />
                    
                    {/* Article Image */}
                    {card.imageUrl && (
                        <a 
                            href={sourceUrl} 
                            target={hasExternalSource ? "_blank" : "_self"} 
                            rel={hasExternalSource ? "noopener noreferrer" : undefined}
                        >
                            <div className="w-full h-64 bg-slate-950 overflow-hidden">
                                <img 
                                    src={card.imageUrl} 
                                    alt={card.title} 
                                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" 
                                />
                            </div>
                        </a>
                    )}

                    {/* Main Content */}
                    <div className="p-6">
                        {/* Header with Title and Actions */}
                        <header className="flex flex-col-reverse items-end gap-4 sm:flex-row sm:justify-between sm:items-start mb-6">
                            <div className="flex-1">
                                <a 
                                    href={sourceUrl} 
                                    target={hasExternalSource ? "_blank" : "_self"} 
                                    rel={hasExternalSource ? "noopener noreferrer" : undefined}
                                >
                                    <h2 className="font-serif text-2xl font-bold text-slate-50 mb-3 cursor-pointer group-hover:text-amber-300 transition-colors hover:text-amber-300 leading-tight">
                                        {t('title', card.title)}
                                    </h2>
                                </a>
                                
                                {/* Translation control (pills + translate button handled inside) */}
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
                                        aria-label="Article Permalink" 
                                        className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors h-10 w-10 text-slate-400 hover:text-white hover:bg-white/10"
                                    >
                                        <LinkIcon className="h-5 w-5" />
                                    </a>
                                </Link>
                                <Button 
                                    variant="ghost" 
                                    size="icon" 
                                    onClick={handleCopy} 
                                    className="text-slate-400 hover:text-white hover:bg-white/10" 
                                    aria-label="Copy article link"
                                >
                                    {hasCopied ? <Check className="text-emerald-400" /> : <Copy />}
                                </Button>
                                <ShareMenu 
                                    title={translatedFields?.title ?? card.title} 
                                    articleId={card.id} 
                                    blurb={shareBlurb}
                                    lang={currentLang}
                                />
                            </div>
                        </header>
                        
                        {/* Article Text */}
                        <div
                            className="space-y-2"
                            dir={isRTL ? 'rtl' : 'ltr'}
                            style={isRTL ? { textAlign: 'right' } : undefined}
                        >
                            {/* For video collections, use styled VideoList component */}
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

                    {/* Analysis Sections - Only show if not compact */}
                    {!isCompact && (
                        <>
                            {/* Optional: Talking Points */}
                            {talkingPoints && Array.isArray(talkingPoints) && talkingPoints.length > 0 && (
                                <AnalysisSection 
                                    title="Talking Points" 
                                    icon={<MessageSquare className="h-5 w-5 text-amber-400" />} 
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
                            
                            {/* Optional: Deep Analysis */}
                            {deepAnalysisSummary && (
                                <AnalysisSection 
                                    title="Deep Analysis" 
                                    icon={<BrainCircuit className="h-5 w-5 text-amber-400" />} 
                                    isExpanded={expandedSections.deepAnalysis} 
                                    onToggle={() => toggleSection('deepAnalysis')}
                                >
                                    <p className="text-slate-300 font-serif leading-relaxed">{deepAnalysisSummary}</p>
                                </AnalysisSection>
                            )}
                            
                            {/* RED TEAM - Facts Only (FIRST) */}
                            {card.red_team_analysis && (
                                <AnalysisSection 
                                    title="Facts Only" 
                                    icon={<Crosshair className="h-5 w-5 text-red-400" />} 
                                    isExpanded={expandedSections.redTeam} 
                                    onToggle={() => toggleSection('redTeam')}
                                >
                                    <AccordionText text={t('red_team_analysis', card.red_team_analysis)} characterLimit={500} />
                                </AnalysisSection>
                            )}
                            
                            {/* BLUE TEAM - Executive Summary (SECOND) */}
                            {card.blue_team_analysis && (
                                <AnalysisSection 
                                    title="Executive Summary" 
                                    icon={<Shield className="h-5 w-5 text-blue-400" />} 
                                    isExpanded={expandedSections.blueTeam} 
                                    onToggle={() => toggleSection('blueTeam')}
                                >
                                    <AccordionText text={t('blue_team_analysis', card.blue_team_analysis)} characterLimit={500} />
                                </AnalysisSection>
                            )}
                            
                            {/* PURPLE TEAM - Full Take (THIRD/LAST) */}
                            {card.purple_team_analysis && (
                                <AnalysisSection 
                                    title="Full Take" 
                                    icon={<Combine className="h-5 w-5 text-purple-400" />} 
                                    isExpanded={expandedSections.purpleTeam} 
                                    onToggle={() => toggleSection('purpleTeam')}
                                >
                                    <AccordionText text={t('purple_team_analysis', card.purple_team_analysis)} characterLimit={500} />
                                </AnalysisSection>
                            )}

                            {/* SENTINEL - AI Content Detection */}
                            {sentinelData && sentinelColor && (
                                <AnalysisSection 
                                    title={`Sentinel — ${sentinelColor.label}`}
                                    icon={<ScanLine className={`h-5 w-5 ${sentinelColor.text}`} />} 
                                    isExpanded={expandedSections.sentinel} 
                                    onToggle={() => toggleSection('sentinel')}
                                >
                                    <div className="space-y-4">
                                        {/* Confidence bar */}
                                        <div className="flex items-center gap-3">
                                            <span className="text-xs text-slate-500 w-24 shrink-0">Confidence</span>
                                            <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                                                <div 
                                                    className={`h-full rounded-full transition-all duration-500 ${
                                                        sentinelData.synthetic_confidence <= 0.4 ? 'bg-emerald-500' :
                                                        sentinelData.synthetic_confidence <= 0.6 ? 'bg-amber-500' : 'bg-red-500'
                                                    }`}
                                                    style={{ width: `${Math.round(sentinelData.synthetic_confidence * 100)}%` }}
                                                />
                                            </div>
                                            <span className={`text-sm font-mono font-bold ${sentinelColor.text}`}>
                                                {Math.round(sentinelData.synthetic_confidence * 100)}%
                                            </span>
                                        </div>

                                        {/* Summary */}
                                        <p className="text-slate-300 leading-relaxed">{sentinelData.summary}</p>

                                        {/* Indicators */}
                                        {sentinelData.indicators && sentinelData.indicators.length > 0 && (
                                            <div className="space-y-2">
                                                <span className="text-xs text-slate-500 uppercase tracking-wider">Signals Detected</span>
                                                {sentinelData.indicators.map((ind, i) => (
                                                    <div key={i} className="flex items-start gap-2 text-sm">
                                                        <span className={`mt-0.5 h-2 w-2 rounded-full shrink-0 ${
                                                            ind.severity === 'high' ? 'bg-red-400' :
                                                            ind.severity === 'medium' ? 'bg-amber-400' : 'bg-slate-500'
                                                        }`} />
                                                        <span className="text-slate-400">
                                                            <span className="text-slate-500 capitalize">{ind.dimension}:</span>{' '}
                                                            {ind.signal}
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {/* Human signals */}
                                        {sentinelData.human_signals && sentinelData.human_signals.length > 0 && (
                                            <div className="space-y-2">
                                                <span className="text-xs text-slate-500 uppercase tracking-wider">Human Indicators</span>
                                                {sentinelData.human_signals.map((signal, i) => (
                                                    <div key={i} className="flex items-start gap-2 text-sm">
                                                        <span className="mt-0.5 h-2 w-2 rounded-full shrink-0 bg-emerald-400" />
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

                    {/* Comments — full section on article page, count only on feed */}
                    {!isCompact ? (
                        <div className="px-6 pb-6 pt-4">
                            <CommentSection 
                                comments={comments} 
                                articleId={card.id} 
                            />
                        </div>
                    ) : comments.length > 0 ? (
                        <a href={`/article/${card.id}`} className="block px-6 pb-2 group">
                            <div className="flex items-center gap-2 text-slate-400 text-sm group-hover:text-amber-300 transition-colors cursor-pointer">
                                <MessageSquare className="h-4 w-4" />
                                <span>{comments.length} Comment{comments.length !== 1 ? 's' : ''}</span>
                            </div>
                        </a>
                    ) : null}
                    
                    {/* Footer */}
                    <div className="border-t border-slate-700/50" />
                    <footer className="flex justify-between items-center text-xs text-slate-500 p-4">
                        <span className="font-medium">{formattedDate}</span>
                        <span className="font-semibold uppercase tracking-wider">
                            {card.directive}
                        </span>
                    </footer>
                </div>
            </motion.div>
        </>
    );
};

export default React.memo(IntelligenceCard, (prev, next) => prev.card.id === next.card.id && prev.comments.length === next.comments.length && prev.isCompact === next.isCompact);
