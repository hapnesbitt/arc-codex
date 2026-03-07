// Filename: /frontend/app/publish/page.tsx
// v7.0 - Accessibility fixes
//
// Changes from v6.0:
//   - Skip link: focus: → focus-visible: (no flash on mouse click)
//   - Loading overlay: role="alert" → role="status" aria-live="polite"
//     (loading is not an assertive interruption — errors are, spinners aren't)
//   - SelectorButton / radiogroup: arrow key navigation implemented
//     (ARIA radiogroup spec requires Left/Right/Up/Down to move between options)
//   - autosavedAt display wrapped in <time> element
//   - Mobile FAB aria-label clarified to match form submit label by state

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import {
  Send, Loader, CheckCircle, RefreshCw, Upload,
  Sparkles, FileText, Link2, Wand2,
  Rocket, Globe, Crown, Shield,
} from 'lucide-react';
import UploadArea from '@/components/UploadArea';
import StatusMessage from '@/components/StatusMessage';
import PageWrapper from '@/components/layout/PageWrapper';

// --- CONSTANTS ---
const AUTOSAVE_KEY = 'arc-codex.publish.draft';
const ALLOWED_FILE_TYPES = [
  'text/plain',
  'text/markdown',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

// --- TYPES ---
type ContentType = 'text' | 'url' | 'file';
type Status = 'idle' | 'loading' | 'success' | 'error';

interface DraftData {
  title: string;
  content: string;
  contentType: ContentType;
  at: string;
}

interface SectionProps {
  title: string;
  children: React.ReactNode;
  gradient?: string;
  icon: React.ReactNode;
  className?: string;
  sectionId?: string;
}

interface SelectorConfig {
  id: string;
  label: string;
  icon: React.ReactNode;
  borderColor: string;
  bgColor: string;
  textColor: string;
  shadowColor: string;
  ariaDescription: string;
}

// --- CONTENT TYPE CONFIGURATIONS ---
const CONTENT_TYPES: SelectorConfig[] = [
  {
    id: 'url',
    label: 'Share URL',
    icon: <Link2 className="h-5 w-5" aria-hidden="true" />,
    borderColor: 'border-blue-400',
    bgColor: 'bg-blue-400/10',
    textColor: 'text-blue-300',
    shadowColor: 'shadow-[0_0_20px_rgba(59,130,246,0.3)]',
    ariaDescription: 'Submit a web URL for A.R.C. analysis',
  },
  {
    id: 'text',
    label: 'Write Text',
    icon: <FileText className="h-5 w-5" aria-hidden="true" />,
    borderColor: 'border-amber-400',
    bgColor: 'bg-amber-400/10',
    textColor: 'text-amber-300',
    shadowColor: 'shadow-[0_0_20px_rgba(251,191,36,0.3)]',
    ariaDescription: 'Write or paste article text directly',
  },
  {
    id: 'file',
    label: 'Upload File',
    icon: <Upload className="h-5 w-5" aria-hidden="true" />,
    borderColor: 'border-green-400',
    bgColor: 'bg-green-400/10',
    textColor: 'text-green-300',
    shadowColor: 'shadow-[0_0_20px_rgba(34,197,94,0.3)]',
    ariaDescription: 'Upload a document file for analysis',
  },
];

// --- REUSABLE SECTION COMPONENT ---
const Section: React.FC<SectionProps> = ({ title, children, gradient, icon, className = "", sectionId }) => {
  const headingId = sectionId ? `${sectionId}-heading` : undefined;
  return (
    <section
      aria-labelledby={headingId}
      className={`p-8 rounded-2xl bg-slate-900/30 border ${gradient ?? 'border-amber-400/50'} backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.3)] transition-colors duration-300 ${className}`}
    >
      <div className="flex items-center gap-4 mb-6">
        <div className="relative" aria-hidden="true">
          {icon}
        </div>
        <h2 id={headingId} className="text-2xl font-bold text-slate-50 font-sans tracking-tight">{title}</h2>
      </div>
      <div className="prose prose-invert prose-lg max-w-none text-slate-200 font-serif leading-relaxed space-y-5">
        {children}
      </div>
    </section>
  );
};

// --- SELECTOR BUTTON ---
// Individual radio option — focus and checked state managed by parent RadioGroup
const SelectorButton: React.FC<{
  config: SelectorConfig;
  isActive: boolean;
  onClick: () => void;
  buttonRef?: React.Ref<HTMLButtonElement>;
}> = ({ config, isActive, onClick, buttonRef }) => (
  <button
    type="button"
    role="radio"
    aria-checked={isActive}
    aria-label={config.ariaDescription}
    onClick={onClick}
    ref={buttonRef}
    // tabIndex managed by parent: only the active/first option is in tab order
    tabIndex={isActive ? 0 : -1}
    className={`p-4 rounded-xl border-2 transition-colors duration-200 flex items-center gap-3 font-serif
      outline-none focus-visible:ring-2 focus-visible:ring-amber-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950
      ${isActive
        ? `${config.borderColor} ${config.bgColor} ${config.textColor} ${config.shadowColor}`
        : 'border-slate-600/50 hover:border-slate-500 text-slate-400 hover:text-slate-300'
      }`}
  >
    {config.icon}
    {config.label}
  </button>
);

// --- RADIO GROUP WRAPPER ---
// Implements ARIA radiogroup keyboard pattern:
// Arrow keys move focus+selection between options (roving tabindex).
const RadioGroup: React.FC<{
  value: ContentType;
  onChange: (value: ContentType) => void;
}> = ({ value, onChange }) => {
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const currentIndex = CONTENT_TYPES.findIndex(c => c.id === value);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const total = CONTENT_TYPES.length;
    let nextIndex: number | null = null;

    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % total;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      nextIndex = (currentIndex - 1 + total) % total;
    } else if (e.key === 'Home') {
      e.preventDefault();
      nextIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      nextIndex = total - 1;
    }

    if (nextIndex !== null) {
      onChange(CONTENT_TYPES[nextIndex].id as ContentType);
      buttonRefs.current[nextIndex]?.focus();
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label="Content submission type"
      className="flex flex-wrap gap-4 justify-center"
      onKeyDown={handleKeyDown}
    >
      {CONTENT_TYPES.map((config, i) => (
        <SelectorButton
          key={config.id}
          config={config}
          isActive={value === config.id}
          onClick={() => onChange(config.id as ContentType)}
          buttonRef={el => { buttonRefs.current[i] = el; }}
        />
      ))}
    </div>
  );
};

// --- MAIN COMPONENT ---
export default function PublishPage() {
  const router = useRouter();
  const [title, setTitle]               = useState('');
  const [content, setContent]           = useState('');
  const [contentType, setContentType]   = useState<ContentType>('url');
  const [file, setFile]                 = useState<File | null>(null);
  const [status, setStatus]             = useState<Status>('idle');
  const [message, setMessage]           = useState('');
  const [autosavedAt, setAutosavedAt]   = useState<string | null>(null);
  const [showConfetti, setShowConfetti] = useState(false);
  const submitBtnRef  = useRef<HTMLButtonElement>(null);
  const fileInputRef  = useRef<HTMLInputElement>(null);
  const liveRegionRef = useRef<HTMLDivElement>(null);

  // Announce status changes to screen readers via live region
  useEffect(() => {
    if (message && liveRegionRef.current) {
      liveRegionRef.current.textContent = message;
    }
  }, [message, status]);

  // Load draft from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(AUTOSAVE_KEY);
      if (raw) {
        const data: DraftData = JSON.parse(raw);
        if (data.title)       setTitle(data.title);
        if (data.content)     setContent(data.content);
        if (data.contentType) setContentType(data.contentType);
        if (data.at)          setAutosavedAt(data.at);
      }
    } catch (err) {
      console.warn('Failed to load draft:', err);
    }
  }, []);

  // Autosave to localStorage (3s debounce)
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        const payload: DraftData = {
          title,
          content,
          contentType,
          at: new Date().toISOString(),
        };
        localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(payload));
        setAutosavedAt(payload.at);
      } catch (err) {
        console.warn('Autosave failed:', err);
      }
    }, 3000);
    return () => clearTimeout(id);
  }, [title, content, contentType]);

  const clearDraft = useCallback(() => {
    localStorage.removeItem(AUTOSAVE_KEY);
    setAutosavedAt(null);
    setContent('');
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const isProbablyUrl = useCallback((s: string): boolean => {
    try {
      const u = new URL(s);
      return ['http:', 'https:'].includes(u.protocol);
    } catch {
      return false;
    }
  }, []);

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    if (e?.preventDefault) e.preventDefault();

    if (!title.trim()) {
      setStatus('error');
      setMessage('A title is required.');
      return;
    }
    if (contentType === 'text' && !content.trim()) {
      setStatus('error');
      setMessage('Content is required.');
      return;
    }
    if (contentType === 'url' && (!content.trim() || !isProbablyUrl(content.trim()))) {
      setStatus('error');
      setMessage('Please provide a valid URL (starting with http:// or https://)');
      return;
    }
    if (contentType === 'file' && !file) {
      setStatus('error');
      setMessage('Please select a file to upload.');
      return;
    }

    setStatus('loading');
    setMessage('Processing with A.R.C. analysis...');

    try {
      const formData = new FormData();
      formData.append('title', title.trim());
      formData.append('content_type', contentType);
      formData.append('category', 'general');
      if (contentType === 'file' && file) {
        formData.append('file', file);
      } else {
        formData.append('content', content.trim());
      }

      const resp = await fetch('/api/submit_content', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.error || 'Unknown error from server.');
      }

      setStatus('success');
      setMessage('Published! Your content is live with full A.R.C. analysis.');
      setShowConfetti(true);
      clearDraft();
      setTitle('');
      setContent('');
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';

      setTimeout(() => {
        setShowConfetti(false);
        const redirectTo = data.redirectUrl || '/';
        router.push(redirectTo);
      }, 2000);
    } catch (err) {
      console.error('Submit failed:', err);
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Something went wrong.');
    }
  }, [title, content, contentType, file, clearDraft, router, isProbablyUrl]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (status !== 'loading' && status !== 'success') handleSubmit();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        clearDraft();
        setTitle('');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [clearDraft, handleSubmit, status]);

  const handleFileChange = useCallback((selectedFile: File | null) => {
    if (selectedFile && ALLOWED_FILE_TYPES.includes(selectedFile.type)) {
      setFile(selectedFile);
      setContent(selectedFile.name);
      setMessage('File ready.');
      setStatus('idle');
    } else {
      setMessage('Please upload a supported file type (.txt, .md, .pdf, .docx)');
      setStatus('error');
      setFile(null);
    }
  }, []);

  const handleRestoreDraft = useCallback(() => {
    try {
      const raw = localStorage.getItem(AUTOSAVE_KEY);
      if (raw) {
        const data: DraftData = JSON.parse(raw);
        setTitle(data.title || '');
        setContent(data.content || '');
        setContentType(data.contentType || 'url');
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
        setMessage('Draft restored.');
        setStatus('idle');
      }
    } catch {
      setMessage('No drafts found.');
      setStatus('error');
    }
  }, []);

  // Submit button label by state
  const submitLabel =
    status === 'loading' ? 'Publishing, please wait'
    : status === 'success' ? 'Published successfully'
    : 'Publish';

  // --- CONTENT TYPE RENDERERS ---
  const renderTextInput = () => (
    <Section
      title="Write Your Story"
      icon={<Sparkles className="w-8 h-8 text-purple-400" />}
      gradient="border-purple-400/50"
      sectionId="content-text"
    >
      <div className="space-y-4">
        <label htmlFor="content-textarea" className="sr-only">Article content</label>
        <Textarea
          id="content-textarea"
          value={content}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setContent(e.target.value)}
          rows={16}
          placeholder="Start writing..."
          aria-describedby="text-stats"
          className="bg-slate-800/20 border-slate-600/50 text-slate-100 font-serif text-base leading-relaxed focus:border-purple-400/50 focus:ring-purple-400/25 resize-none transition-colors"
          disabled={status === 'loading' || status === 'success'}
        />
        <div id="text-stats" className="flex justify-between items-center">
          <div className="text-sm text-slate-400 font-serif">
            {content.trim() === '' ? 0 : content.trim().split(/\s+/).filter(w => w.length > 0).length} words · {content.length} characters
          </div>
          <Badge variant="outline" className="border-purple-400/30 text-purple-300 font-mono text-xs">
            Ctrl+Enter to submit
          </Badge>
        </div>
      </div>
    </Section>
  );

  const renderUrlInput = () => (
    <Section
      title="Share from the Web"
      icon={<Globe className="w-8 h-8 text-blue-400" />}
      gradient="border-blue-400/50"
      sectionId="content-url"
    >
      <div className="space-y-4">
        <label htmlFor="content-url-input" className="sr-only">Article URL</label>
        <Input
          id="content-url-input"
          value={content}
          type="url"
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setContent(e.target.value)}
          placeholder="https://example.com/article"
          aria-describedby="url-hint"
          className="bg-slate-800/20 border-slate-600/50 text-slate-100 text-lg h-14 focus:border-blue-400/50 focus:ring-blue-400/25 font-mono transition-colors"
          disabled={status === 'loading' || status === 'success'}
        />
        <div id="url-hint" className="flex justify-between items-center h-8">
          <span className="text-sm text-slate-400 font-serif italic">
            Paste any article URL — A.R.C. will fetch and analyze it
          </span>
          {content && isProbablyUrl(content) && (
            <Badge variant="outline" className="bg-green-600/20 text-green-300 border-green-500/30 font-serif">
              <CheckCircle className="h-3 w-3 mr-1" aria-hidden="true" />
              Valid URL
            </Badge>
          )}
        </div>
      </div>
    </Section>
  );

  const renderFileUpload = () => (
    <Section
      title="Upload Your Document"
      icon={<Upload className="w-8 h-8 text-green-400" />}
      gradient="border-green-400/50"
      sectionId="content-file"
    >
      <UploadArea
        file={file}
        onFileChange={handleFileChange}
        disabled={status === 'loading' || status === 'success'}
      />
    </Section>
  );

  return (
    <PageWrapper>
      {/* Skip link — focus-visible only, no flash on mouse click */}
      <a
        href="#publish-form"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-4 focus-visible:left-4 focus-visible:z-[300] focus-visible:px-4 focus-visible:py-2 focus-visible:bg-amber-500 focus-visible:text-black focus-visible:font-bold focus-visible:rounded-lg focus-visible:text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
      >
        Skip to publish form
      </a>

      {/* Live region for screen reader announcements */}
      <div
        ref={liveRegionRef}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      />

      <main aria-label="Publish content to Arc Codex" className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-12">

        {/* Hero Header */}
        <header className="flex flex-col items-center text-center space-y-6 py-10">
          <div className="p-4 rounded-2xl bg-gradient-to-br from-amber-500/50 via-purple-500/40 to-blue-500/50 backdrop-blur-2xl border border-amber-400/60 shadow-[0_0_40px_rgba(251,191,36,0.5)]" aria-hidden="true">
            <Wand2 className="h-12 w-12 text-amber-300" />
          </div>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-sans tracking-tight text-slate-50 drop-shadow-[0_0_10px_rgba(251,191,36,0.8)]">
            Create & Share
          </h1>
          <p className="text-xl md:text-2xl text-amber-300/90 font-serif italic drop-shadow-sm leading-relaxed">
            Transform your ideas with A.R.C. cognitive analysis
          </p>
          <div className="flex items-center gap-3 text-sm text-slate-400">
            <Shield className="h-4 w-4 text-green-400" aria-hidden="true" />
            <span className="font-serif">PII Protection Enabled · Names & Locations Redacted</span>
          </div>
          <div className="w-24 h-1 bg-gradient-to-r from-amber-400 to-purple-500 rounded-full" aria-hidden="true" />
        </header>

        <form id="publish-form" onSubmit={handleSubmit} aria-label="Publish content" className="space-y-12">

          {/* Title Section */}
          <Section
            title="Title Your Creation"
            icon={<Crown className="w-8 h-8 text-amber-400" />}
            gradient="border-amber-400/50"
            sectionId="title-section"
          >
            <div className="space-y-4">
              <label htmlFor="title" className="sr-only">Article title</label>
              <Input
                id="title"
                value={title}
                type="text"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
                placeholder="Give your article a title..."
                aria-describedby="title-hint title-counter"
                aria-required="true"
                className="bg-slate-800/30 border-slate-600/50 text-slate-100 text-lg h-14 focus:border-amber-400/50 focus:ring-amber-400/25 font-serif transition-colors"
                disabled={status === 'loading' || status === 'success'}
                maxLength={200}
              />
              <div className="flex justify-between items-center">
                <span id="title-hint" className="text-sm text-slate-400 font-serif italic">Clear and descriptive works best</span>
                <Badge
                  id="title-counter"
                  variant="outline"
                  className="border-amber-400/30 text-amber-300 font-mono text-xs"
                  aria-label={`${title.length} of 200 characters used`}
                >
                  {title.length}/200
                </Badge>
              </div>
            </div>
          </Section>

          {/* Content Type Selector */}
          <Section
            title="Choose Your Medium"
            icon={<Link2 className="w-8 h-8 text-blue-400" />}
            gradient="border-blue-400/50"
            sectionId="medium-section"
          >
            <RadioGroup value={contentType} onChange={setContentType} />
          </Section>

          {/* Content Input */}
          <div>
            {contentType === 'text' && renderTextInput()}
            {contentType === 'url'  && renderUrlInput()}
            {contentType === 'file' && renderFileUpload()}
          </div>

          {/* Status Message */}
          <StatusMessage status={status} message={message} />

          {/* Publish Controls */}
          <Section
            title="Publish Controls"
            icon={<Rocket className="w-8 h-8 text-amber-400" />}
            gradient="border-amber-400/50"
            sectionId="publish-controls"
          >
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
              <div className="flex flex-wrap items-center gap-4">
                {/* Autosave timestamp — not a live region, just ambient info */}
                <div className="text-sm text-slate-400 font-serif">
                  {autosavedAt ? (
                    <>Autosaved: <time dateTime={autosavedAt}>{new Date(autosavedAt).toLocaleTimeString()}</time></>
                  ) : (
                    'Not yet saved'
                  )}
                </div>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-slate-400 hover:text-slate-200 font-serif focus-visible:ring-2 focus-visible:ring-amber-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                    >
                      Clear All
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="bg-slate-900/95 border-slate-700 backdrop-blur-xl">
                    <AlertDialogHeader className="space-y-2">
                      <AlertDialogTitle className="text-slate-50 font-sans">
                        Clear everything?
                      </AlertDialogTitle>
                      <AlertDialogDescription className="text-slate-400 font-serif">
                        This will permanently delete your current draft and reset the form.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter className="flex gap-2">
                      <AlertDialogCancel className="font-serif">Keep it</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => {
                          clearDraft();
                          setTitle('');
                          setMessage('Fresh start.');
                          setStatus('idle');
                        }}
                        className="bg-red-600 hover:bg-red-700 font-serif"
                      >
                        Clear All
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>

                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleRestoreDraft}
                        aria-label="Restore last saved draft"
                        className="text-slate-400 hover:text-slate-200 font-serif focus-visible:ring-2 focus-visible:ring-amber-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                      >
                        <RefreshCw className="h-4 w-4 mr-2" aria-hidden="true" />
                        Restore
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent className="bg-slate-800 border-slate-700">
                      <p className="font-serif">Restore your last saved draft</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>

              <div>
                <Button
                  type="submit"
                  variant="default"
                  size="lg"
                  ref={submitBtnRef}
                  disabled={status === 'loading' || status === 'success'}
                  aria-label={submitLabel}
                  className="relative overflow-hidden bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-900 font-bold text-lg px-8 py-6 h-auto shadow-xl shadow-amber-500/25 border border-amber-400/50 font-serif transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  <div className="flex items-center gap-3">
                    {status === 'loading' ? (
                      <Loader className="animate-spin h-5 w-5" aria-hidden="true" />
                    ) : status === 'success' ? (
                      <CheckCircle className="h-5 w-5" aria-hidden="true" />
                    ) : (
                      <Rocket className="h-5 w-5" aria-hidden="true" />
                    )}
                    <span>
                      {status === 'loading'
                        ? 'Analyzing...'
                        : status === 'success'
                        ? 'Published!'
                        : <><span className="sm:hidden">Publish</span><span className="hidden sm:inline">Publish to Arc Codex</span></>
                      }
                    </span>
                  </div>
                </Button>
              </div>
            </div>
          </Section>
        </form>

        {/* Footer */}
        <footer className="text-center text-sm text-slate-400 pt-8 pb-4 border-t border-slate-700/50">
          <p className="font-serif">
            © {new Date().getFullYear()} Arc Codex. Protected by A.R.C. Cognitive Framework.
          </p>
        </footer>
      </main>

      {/* Mobile Floating Submit Button — outside form, calls handleSubmit directly */}
      <div className="fixed bottom-8 right-8 z-40 md:hidden">
        <Button
          variant="default"
          size="icon"
          onClick={() => handleSubmit()}
          disabled={status === 'loading' || status === 'success'}
          aria-label={submitLabel}
          className="h-16 w-16 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 shadow-2xl shadow-amber-500/50 border border-amber-400/50 transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
        >
          <Send className="h-6 w-6" aria-hidden="true" />
        </Button>
      </div>

      {/* Confetti — purely decorative */}
      {showConfetti && (
        <div className="fixed inset-0 pointer-events-none z-50" aria-hidden="true">
          {Array.from({ length: 50 }).map((_, i) => (
            <div
              key={i}
              className="absolute w-3 h-3 bg-gradient-to-r from-amber-400 to-orange-400 rounded-full animate-confetti"
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 0.5}s`,
              }}
            />
          ))}
        </div>
      )}

      {/* Loading overlay — role="status" + aria-live="polite" (not assertive) */}
      {status === 'loading' && (
        <div
          className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-40 flex items-center justify-center transition-opacity duration-300"
          role="status"
          aria-live="polite"
          aria-label="Processing your content"
        >
          <div className="text-center p-8 rounded-2xl bg-slate-900/50 border border-amber-400/50 backdrop-blur-xl shadow-[0_0_40px_rgba(251,191,36,0.5)]">
            <div className="w-24 h-24 border-4 border-amber-500/30 border-t-amber-500 rounded-full mx-auto mb-6 animate-spin" aria-hidden="true" />
            <h3 className="text-2xl font-bold text-amber-300 mb-2 font-sans tracking-tight">
              Processing Your Content
            </h3>
            <p className="text-slate-400 font-serif italic">
              A.R.C. is analyzing with 48 cognitive patterns...
            </p>
          </div>
        </div>
      )}

      <style jsx>{`
        @keyframes confetti {
          0% { transform: translateY(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
        }
        .animate-confetti {
          animation: confetti 3s ease-out forwards;
        }
      `}</style>
    </PageWrapper>
  );
}
