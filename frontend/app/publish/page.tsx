// Filename: /frontend/app/publish/page.tsx
// v9.0 - Publish confirmation modal + image selection
//
// Changes from v8.0:
//   - Confirmation modal: "Share Story" — Make Public / Keep Private (disabled)
//     Validation runs first; modal opens only when form is valid
//     handleRequestSubmit = validate + open modal
//     handleConfirmedPublish = actual API call (was handleSubmit body)
//   - Image selection: browse local file or take photo (mobile camera)
//     Uploads to /api/upload_image → saved to frontend/public/uploads/
//     Preview shown before publish; og_image set on article
//     Optional — falls back to OG image from URL if not provided

'use client';

import React, { Suspense, useEffect, useState, useCallback, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import {
  Send, Loader, CheckCircle, RefreshCw, Upload,
  Sparkles, FileText, Link2, Wand2,
  Rocket, Globe, Crown, Shield, PenLine, ImagePlus, X as XIcon,
  ChevronDown, ChevronUp, Video,
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
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/vnd.oasis.opendocument.text',                                  // .odt
];

const DOC_EXTENSIONS = ['.pdf', '.docx', '.odt'];

// --- TYPES ---
type ContentType = 'text' | 'url' | 'file' | 'prompt';
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
  icon: React.ReactNode;
  className?: string;
  sectionId?: string;
}

interface SelectorConfig {
  id: string;
  label: string;
  icon: React.ReactNode;
  ariaDescription: string;
}

// --- CONTENT TYPE CONFIGURATIONS ---
const CONTENT_TYPES: SelectorConfig[] = [
  {
    id: 'url',
    label: 'Share URL',
    icon: <Link2 className="h-4 w-4" aria-hidden="true" />,
    ariaDescription: 'Submit a web URL for A.R.C. analysis',
  },
  {
    id: 'text',
    label: 'Write Text',
    icon: <FileText className="h-4 w-4" aria-hidden="true" />,
    ariaDescription: 'Write or paste article text directly',
  },
  {
    id: 'file',
    label: 'Upload File',
    icon: <Upload className="h-4 w-4" aria-hidden="true" />,
    ariaDescription: 'Upload a document file for analysis',
  },
  {
    id: 'prompt',
    label: 'Write Prompt',
    icon: <PenLine className="h-4 w-4" aria-hidden="true" />,
    ariaDescription: 'Describe what you want Arc Codex to write for you',
  },
];

// --- REUSABLE SECTION COMPONENT ---
// Librarian aesthetic: section flows as a horizontal band on the page, separated
// by a single thin border. No card chrome — title sits as a small uppercase
// label above generous body whitespace.
const Section: React.FC<SectionProps> = ({ title, children, icon, className = "", sectionId }) => {
  const headingId = sectionId ? `${sectionId}-heading` : undefined;
  return (
    <section
      aria-labelledby={headingId}
      className={`py-10 border-b border-slate-800/60 ${className}`}
    >
      <div className="flex items-center gap-3 mb-6">
        <div className="text-slate-500" aria-hidden="true">
          {icon}
        </div>
        <h2 id={headingId} className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
          {title}
        </h2>
      </div>
      <div className="max-w-none text-slate-200 font-serif leading-relaxed space-y-6">
        {children}
      </div>
    </section>
  );
};

// --- SELECTOR BUTTON ---
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
    tabIndex={isActive ? 0 : -1}
    className={`px-4 py-3 border transition-colors duration-200 flex items-center gap-3 rounded-sm font-sans text-xs uppercase tracking-[0.18em]
      outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40
      ${isActive
        ? 'border-emerald-500/60 text-slate-100 bg-slate-800/40'
        : 'border-slate-800 hover:border-slate-700 text-slate-500 hover:text-slate-300'
      }`}
  >
    <span className="text-slate-500" aria-hidden="true">{config.icon}</span>
    {config.label}
  </button>
);

// --- RADIO GROUP WRAPPER ---
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
      className="flex flex-wrap gap-3"
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
function PublishPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const isAuthed = !!session?.user;
  const [title, setTitle]               = useState('');
  const [content, setContent]           = useState('');
  const [contentType, setContentType]   = useState<ContentType>('url');
  const [file, setFile]                 = useState<File | null>(null);
  const [status, setStatus]             = useState<Status>('idle');
  const [message, setMessage]           = useState('');
  const [autosavedAt, setAutosavedAt]   = useState<string | null>(null);
  const [showConfetti, setShowConfetti] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingVisibility, setPendingVisibility] = useState<'public' | 'private'>('public');
  const [imageFile, setImageFile]           = useState<File | null>(null);
  const [imagePreview, setImagePreview]     = useState<string | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [imageOpen, setImageOpen] = useState(false);
  const [urlFetchFailed, setUrlFetchFailed] = useState(false);
  const [description, setDescription]       = useState(() => searchParams.get('body') ?? '');
  const [isVideoMode, setIsVideoMode]       = useState(false);
  const [mounted, setMounted]               = useState(false);
  const submitBtnRef     = useRef<HTMLButtonElement>(null);
  const imageInputRef    = useRef<HTMLInputElement>(null);
  const fileInputRef     = useRef<HTMLInputElement>(null);
  const liveRegionRef    = useRef<HTMLDivElement>(null);
  const confirmModalRef  = useRef<HTMLDivElement>(null);
  const pollTimerRef     = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (message && liveRegionRef.current) {
      liveRegionRef.current.textContent = message;
    }
  }, [message, status]);

  useEffect(() => {
    if (showConfirmModal) {
      setTimeout(() => confirmModalRef.current?.focus(), 50);
    }
  }, [showConfirmModal]);

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

  // Poll /api/job/<id> up to maxAttempts × intervalMs for URL fetch result
  const pollJobStatus = useCallback((jobId: string, submittedUrl: string) => {
    let attempts = 0;
    const MAX_ATTEMPTS = 10; // 10 × 3 s = 30 s
    const INTERVAL_MS  = 3000;

    const tick = async () => {
      attempts++;
      try {
        const res  = await fetch(`/api/job/${jobId}`);
        const data = await res.json();

        if (data.status === 'published') {
          setStatus('success');
          setMessage('Published! Your article is live.');
          setShowConfetti(true);
          clearDraft();
          setTitle('');
          setContent('');
          setTimeout(() => {
            setShowConfetti(false);
            router.push(data.article_id ? `/article/${data.article_id}` : '/');
          }, 2000);
          return; // stop polling

        } else if (data.status === 'failed') {
          setUrlFetchFailed(true);
          setStatus('error');
          setMessage(data.reason ?? 'URL could not be fetched — please paste the article text directly.');
          return; // stop polling
        }
      } catch {
        // network error during poll — treat as pending
      }

      if (attempts < MAX_ATTEMPTS) {
        pollTimerRef.current = setTimeout(tick, INTERVAL_MS);
      } else {
        // Timed out — article is probably still being analysed; leave success message
        setMessage('Submitted! Your article will appear in the feed shortly.');
      }
    };

    pollTimerRef.current = setTimeout(tick, INTERVAL_MS);
  }, [clearDraft, router]);

  // Clean up any running poll on unmount
  useEffect(() => {
    return () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current); };
  }, []);

  useEffect(() => { setMounted(true); }, []);

  // Pre-fill from ?url, ?title, ?origin, ?description query params (e.g. deep-link from LightBox)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlParam    = params.get('url');
    const titleParam  = params.get('title');
    const originParam = params.get('origin');
    const descParam   = params.get('description');
    if (urlParam) {
      setContent(urlParam);
      setContentType('url');
    }
    if (titleParam) setTitle(titleParam);
    if (originParam === 'video') {
      setIsVideoMode(true);
      if (descParam) setDescription(descParam);
    }
  }, []);

  const isProbablyUrl = useCallback((s: string): boolean => {
    try {
      const u = new URL(s);
      return ['http:', 'https:'].includes(u.protocol);
    } catch {
      return false;
    }
  }, []);

  // Step 1: validate, then open confirmation modal
  const handleRequestSubmit = useCallback((e?: React.FormEvent) => {
    if (e?.preventDefault) e.preventDefault();

    // Video mode — only title required
    if (isVideoMode) {
      if (!title.trim()) {
        setStatus('error');
        setMessage('A title is required.');
        return;
      }
      setShowConfirmModal(true);
      return;
    }

    // Validation — title optional for prompt mode (scribe derives it)
    if (contentType !== 'prompt' && !title.trim() && !imageFile && !uploadedImageUrl) {
      setStatus('error');
      setMessage('A title is required.');
      return;
    }
    if (contentType === 'text' && !content.trim() && !imageFile && !uploadedImageUrl) {
      setStatus('error');
      setMessage('Content is required.');
      return;
    }
    if (contentType === 'url' && !description.trim() && (!content.trim() || !isProbablyUrl(content.trim())) && !imageFile && !uploadedImageUrl) {
      setStatus('error');
      setMessage('Please provide a valid URL (starting with http:// or https://)');
      return;
    }
    if (contentType === 'file' && !file) {
      setStatus('error');
      setMessage('Please select a file to upload.');
      return;
    }
    if (contentType === 'prompt' && !content.trim()) {
      setStatus('error');
      setMessage('Please write a prompt describing what you want Arc Codex to create.');
      return;
    }
    if (contentType === 'prompt' && content.trim().length < 10) {
      setStatus('error');
      setMessage('Prompt is too short — please be more descriptive.');
      return;
    }

    // Validation passed — open confirmation modal
    setShowConfirmModal(true);
  }, [title, content, contentType, file, description, isProbablyUrl, imageFile, uploadedImageUrl, isVideoMode]);

  // Step 2: user confirmed — actually publish
  const handleConfirmedPublish = useCallback(async (visibility: 'public' | 'private' = 'public') => {
    setShowConfirmModal(false);
    setStatus('loading');

    // ── Video mode: POST origin=video directly, no scribe ──────────────────────
    if (isVideoMode) {
      setMessage('Publishing video collection to Arc Codex...');
      try {
        const resp = await fetch('/api/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            origin: 'video',
            content: content.trim(),
            title: title.trim(),
            description: description.trim(),
            visibility,
          }),
        });
        const resData = await resp.json();
        if (!resp.ok) throw new Error(resData.error || 'Unknown error from server.');
        setStatus('success');
        setMessage('Published! Your video collection is live on Arc Codex.');
        setShowConfetti(true);
        setTimeout(() => {
          setShowConfetti(false);
          router.push(resData.article_id ? `/article/${resData.article_id}` : '/');
        }, 2000);
      } catch (err) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : 'Something went wrong.');
      }
      return;
    }

    // Upload image if selected (inlined to avoid forward reference)
    let resolvedImageUrl: string | null = uploadedImageUrl;
    if (imageFile && !uploadedImageUrl) {
      try {
        const fd = new FormData();
        fd.append('image', imageFile);
        const imgResp = await fetch('/api/upload_image', { method: 'POST', body: fd });
        if (imgResp.ok) {
          const imgData = await imgResp.json();
          resolvedImageUrl = imgData.url || null;
          if (resolvedImageUrl) setUploadedImageUrl(resolvedImageUrl);
        }
      } catch {
        // Image upload failed — continue without image (non-fatal)
      }
    }

    // --- PROMPT mode → /api/submit_prompt (async, 202) ---
    if (contentType === 'prompt') {
      setMessage('Sending prompt to Arc Codex...');
      try {
        const resp = await fetch('/api/submit_prompt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: content.trim(), title: title.trim(), image_url: resolvedImageUrl || undefined, visibility }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Unknown error from server.');

        setStatus('success');
        setMessage('Prompt queued! Arc Codex is generating your article — it will appear in the feed shortly.');
        setShowConfetti(true);
        clearDraft();
        setTitle('');
        setContent('');
        setTimeout(() => {
          setShowConfetti(false);
          router.push('/');
        }, 3000);
      } catch (err) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : 'Something went wrong.');
      }
      return;
    }

    // --- URL / TEXT mode → /api/submit (async, 202) ---
    if (contentType === 'url' || contentType === 'text') {
      setUrlFetchFailed(false);
      setMessage('Submitting to Arc Codex...');
      try {
        const trimmedDescription = description.trim();
        // If description provided, send as text submission (URL stored separately as sourceUrl)
        // If image attached but no valid URL, also fall back to text
        const effectiveContentType = (contentType === 'url' && (trimmedDescription || !isProbablyUrl(content.trim())))
          ? 'text' : contentType;
        // For description-backed submissions use description as content; fall back to title/placeholder for image-only
        const effectiveContent = trimmedDescription
          ? trimmedDescription
          : effectiveContentType === 'text' && !content.trim()
            ? (title.trim() || 'Photo submission')
            : content.trim();
        const resp = await fetch('/api/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content_type: effectiveContentType,
            content: effectiveContent,
            title: title.trim(),
            image_url: resolvedImageUrl || undefined,
            visibility,
            // When description is the body, carry the original URL as source_url
            ...(trimmedDescription && contentType === 'url' && content.trim() ? { source_url: content.trim() } : {}),
          }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Unknown error from server.');

        if (effectiveContentType === 'url' && data.job_id && !trimmedDescription) {
          // URL submissions without a description: show optimistic message and poll for fetch result
          setStatus('loading');
          setMessage('Submitted! Verifying article fetch…');
          pollJobStatus(data.job_id, effectiveContent);
        } else {
          // Text/image submissions: no fetch step — success immediately
          setStatus('success');
          setMessage(visibility === 'private' ? 'Saved privately! Only you can see this article.' : 'Submitted! Your content will be published shortly.');
          setShowConfetti(true);
          clearDraft();
          setTitle('');
          setContent('');
          setTimeout(() => {
            setShowConfetti(false);
            router.push('/');
          }, 2000);
        }
      } catch (err) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : 'Something went wrong.');
      }
      return;
    }

    // --- FILE mode ---
    const isDocFile = file && DOC_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext));
    if (isDocFile) {
      // PDF / DOCX / ODT: extract text server-side, then queue via priority queue
      setMessage('Extracting text from document...');
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', title.trim());
        formData.append('visibility', visibility);

        const resp = await fetch('/api/submit_doc', {
          method: 'POST',
          body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Unknown error from server.');

        setStatus('success');
        setMessage('Document extracted and queued! Your article will be published shortly.');
        setShowConfetti(true);
        clearDraft();
        setTitle('');
        setContent('');
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
        setTimeout(() => {
          setShowConfetti(false);
          router.push('/');
        }, 2000);
      } catch (err) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : 'Something went wrong.');
      }
      return;
    }

    // Plain-text / markdown → existing /api/submit_content (multipart)
    setMessage('Processing with A.R.C. analysis...');
    try {
      const formData = new FormData();
      formData.append('title', title.trim());
      formData.append('content_type', contentType);
      formData.append('category', 'general');
      if (file) formData.append('file', file);

      const resp = await fetch('/api/submit_content', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unknown error from server.');

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
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Something went wrong.');
    }
  }, [title, content, contentType, file, description, clearDraft, router, isProbablyUrl, imageFile, uploadedImageUrl, pollJobStatus, isVideoMode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (status !== 'loading' && status !== 'success') handleRequestSubmit();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        clearDraft();
        setTitle('');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [clearDraft, handleRequestSubmit, status]);

  const handleFileChange = useCallback((selectedFile: File | null) => {
    if (!selectedFile) return;
    if (!ALLOWED_FILE_TYPES.includes(selectedFile.type)) {
      setMessage('Please upload a supported file type (.txt, .md, .pdf, .docx, .odt)');
      setStatus('error');
      setFile(null);
      return;
    }
    if (selectedFile.size > 35 * 1024 * 1024) {
      setMessage('File must be under 35 MB.');
      setStatus('error');
      setFile(null);
      return;
    }
    setFile(selectedFile);
    setContent(selectedFile.name);
    setMessage('File ready.');
    setStatus('idle');
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

  const handleImageChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.type.startsWith('image/')) {
      setStatus('error');
      setMessage('Please select an image file.');
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setStatus('error');
      setMessage('Image must be under 10MB.');
      return;
    }
    setImageFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => setImagePreview(ev.target?.result as string);
    reader.readAsDataURL(f);
    setUploadedImageUrl(null);
  }, []);

  const clearImage = useCallback(() => {
    setImageFile(null);
    setImagePreview(null);
    setUploadedImageUrl(null);
    if (imageInputRef.current) imageInputRef.current.value = '';
  }, []);

  const submitLabel =
    status === 'loading' ? 'Publishing, please wait'
    : status === 'success' ? 'Published successfully'
    : 'Publish';

  // --- CONTENT TYPE RENDERERS ---
  const renderTextInput = () => (
    <Section
      title="Body"
      icon={<Sparkles className="w-4 h-4" />}
      sectionId="content-text"
    >
      <div className="space-y-3">
        <label htmlFor="content-textarea" className="sr-only">Article content</label>
        <Textarea
          id="content-textarea"
          value={content}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setContent(e.target.value)}
          rows={16}
          placeholder="Start writing…"
          aria-describedby="text-stats"
          className="bg-transparent border border-slate-800 rounded-sm px-4 py-3 text-slate-100 font-serif text-base leading-relaxed focus:border-emerald-500 focus:ring-0 focus-visible:ring-0 placeholder:text-slate-600 resize-none transition-colors"
          disabled={status === 'loading' || status === 'success'}
        />
        <div id="text-stats" className="flex justify-between items-center font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
          <div>
            {content.trim() === '' ? 0 : content.trim().split(/\s+/).filter(w => w.length > 0).length} Words · {content.length} Chars
          </div>
          <span>⌃⏎ to submit</span>
        </div>
      </div>
    </Section>
  );

  const renderUrlInput = () => (
    <Section
      title="From the Web"
      icon={<Globe className="w-4 h-4" />}
      sectionId="content-url"
    >
      <div className="space-y-4">
        <label htmlFor="content-url-input" className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 block">URL</label>
        <Input
          id="content-url-input"
          value={content}
          type="url"
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setContent(e.target.value)}
          placeholder="https://example.com/article"
          aria-describedby="url-hint"
          className="bg-transparent border-0 border-b border-slate-700 rounded-none px-0 text-slate-100 text-base h-auto py-3 focus:border-emerald-500 focus:ring-0 focus-visible:ring-0 focus:outline-none font-sans placeholder:text-slate-600 transition-colors"
          disabled={status === 'loading' || status === 'success'}
        />
        <div id="url-hint" className="flex justify-between items-center font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
          <span className="italic normal-case tracking-normal font-serif text-sm text-slate-400">
            Paste any article or YouTube URL — A.R.C. will fetch and analyze it.
          </span>
          {content && isProbablyUrl(content) && (
            <span className="inline-flex items-center gap-1.5 text-emerald-400" aria-label="URL is valid">
              <CheckCircle className="h-3 w-3" aria-hidden="true" />
              Valid
            </span>
          )}
        </div>

        {mounted && (
          <div className="space-y-3 pt-4">
            <label htmlFor="url-description" className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 block">
              Description / Transcript <span className="text-slate-600 normal-case tracking-normal">(optional)</span>
            </label>
            <Textarea
              id="url-description"
              value={description}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
              rows={6}
              placeholder="Describe the content, paste a transcript, or summarize what you want A.R.C. to analyze"
              aria-describedby="url-description-hint"
              className="bg-transparent border border-slate-800 rounded-sm px-4 py-3 text-slate-100 font-serif text-base leading-relaxed focus:border-emerald-500 focus:ring-0 focus-visible:ring-0 placeholder:text-slate-600 resize-none transition-colors"
              disabled={status === 'loading' || status === 'success'}
              maxLength={10000}
            />
            <div id="url-description-hint" className="flex justify-between items-center font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
              <span className="italic normal-case tracking-normal font-serif text-sm text-slate-400">If provided, A.R.C. analyzes this text directly — no URL fetch needed.</span>
              <span>{description.length} / 10000</span>
            </div>
          </div>
        )}
      </div>
    </Section>
  );

  const renderFileUpload = () => (
    <Section
      title="Document"
      icon={<Upload className="w-4 h-4" />}
      sectionId="content-file"
    >
      <UploadArea
        file={file}
        onFileChange={handleFileChange}
        disabled={status === 'loading' || status === 'success'}
      />
    </Section>
  );

  const renderPromptInput = () => (
    <Section
      title="Prompt"
      icon={<Wand2 className="w-4 h-4" />}
      sectionId="content-prompt"
    >
      <div className="space-y-4">
        <p className="font-serif text-base text-slate-400 italic leading-relaxed">
          Arc Codex will write a full article based on your prompt, then publish it with A.R.C. analysis.
        </p>
        <label htmlFor="prompt-textarea" className="sr-only">Writing prompt</label>
        <Textarea
          id="prompt-textarea"
          value={content}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setContent(e.target.value)}
          rows={6}
          placeholder="Write a long article explaining how someone should decide whether a cat or dog would be better for them…"
          aria-describedby="prompt-stats"
          className="bg-transparent border border-slate-800 rounded-sm px-4 py-3 text-slate-100 font-serif text-base leading-relaxed focus:border-emerald-500 focus:ring-0 focus-visible:ring-0 placeholder:text-slate-600 resize-none transition-colors"
          disabled={status === 'loading' || status === 'success'}
          maxLength={2000}
        />
        <div id="prompt-stats" className="flex justify-between items-center font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
          <div className="flex items-center gap-2">
            <span>{content.length} / 2000</span>
            {content.length > 0 && content.length < 10 && (
              <span className="inline-flex items-center gap-1.5 text-slate-300 italic normal-case tracking-normal font-serif text-sm">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500" aria-hidden="true" />
                be more descriptive
              </span>
            )}
          </div>
          <span>⌃⏎ to submit</span>
        </div>
        <p className="font-serif text-sm text-slate-400 italic leading-relaxed pt-2 border-t border-slate-800/60">
          Title is optional in prompt mode — Arc Codex will derive one from the generated article.
        </p>
      </div>
    </Section>
  );

  return (
    <PageWrapper>
      {/* Skip link */}
      <a
        href="#publish-form"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-4 focus-visible:left-4 focus-visible:z-[300] focus-visible:px-4 focus-visible:py-2 focus-visible:bg-emerald-600 focus-visible:text-slate-50 focus-visible:font-semibold focus-visible:rounded-sm focus-visible:text-xs focus-visible:uppercase focus-visible:tracking-[0.2em] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-300"
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

      <main aria-label="Publish content to Arc Codex" className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header — text-first, library plate styling */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500" aria-hidden="true">
            Compose · A.R.C. Cognitive Framework
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Create &amp; Share
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
            Transform your ideas with A.R.C. cognitive analysis.
          </p>
          <div className="flex items-center justify-center gap-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 pt-2">
            <Shield className="h-3 w-3" aria-hidden="true" />
            <span>PII Protection · Names &amp; Locations Redacted</span>
          </div>
        </header>

        <form id="publish-form" onSubmit={handleRequestSubmit} aria-label="Publish content">

          {/* Title Section */}
          <Section
            title="Title"
            icon={<Crown className="w-4 h-4" />}
            sectionId="title-section"
          >
            <div className="space-y-3">
              <label htmlFor="title" className="sr-only">
                Article title{contentType === 'prompt' ? ' (optional)' : ''}
              </label>
              <Input
                id="title"
                value={title}
                type="text"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
                placeholder={
                  contentType === 'prompt'
                    ? 'Optional — Arc Codex will generate one if left blank'
                    : 'Give your article a title…'
                }
                aria-describedby="title-hint title-counter"
                aria-required={contentType !== 'prompt'}
                className="bg-transparent border-0 border-b border-slate-700 rounded-none px-0 text-slate-100 text-2xl py-3 h-auto focus:border-emerald-500 focus:ring-0 focus-visible:ring-0 focus:outline-none font-serif placeholder:text-slate-600 transition-colors"
                disabled={status === 'loading' || status === 'success'}
                maxLength={200}
              />
              <div className="flex justify-between items-center font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                <span id="title-hint" className="italic normal-case tracking-normal font-serif text-sm">
                  {contentType === 'prompt' ? 'Optional in prompt mode' : 'Clear and descriptive works best'}
                </span>
                <span id="title-counter" aria-label={`${title.length} of 200 characters used`}>
                  {title.length} / 200
                </span>
              </div>
            </div>
          </Section>

          {/* Video mode: description textarea instead of medium selector */}
          {isVideoMode && (
            <Section
              title="Video Collection"
              icon={<Video className="w-4 h-4" />}
              sectionId="video-section"
            >
              <div className="space-y-4">
                <p className="font-serif text-sm text-slate-400 italic leading-relaxed">
                  Publishing a LightBox video collection to Arc Codex. No scribe analysis — the collection link is the content.
                </p>
                <div>
                  <div className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 block mb-2">Collection URL</div>
                  <p className="font-mono text-sm text-slate-400 break-all">{content}</p>
                </div>
                <div className="space-y-3 pt-2">
                  <label htmlFor="video-description" className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 block">
                    Description <span className="text-slate-600 normal-case tracking-normal">(optional)</span>
                  </label>
                  <Textarea
                    id="video-description"
                    value={description}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
                    rows={4}
                    placeholder="Describe this video collection…"
                    aria-describedby="video-desc-hint"
                    className="bg-transparent border border-slate-800 rounded-sm px-4 py-3 text-slate-100 font-serif text-base leading-relaxed focus:border-emerald-500 focus:ring-0 focus-visible:ring-0 placeholder:text-slate-600 resize-none transition-colors"
                    disabled={status === 'loading' || status === 'success'}
                    maxLength={500}
                  />
                  <div id="video-desc-hint" className="flex justify-between items-center font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                    <span className="italic normal-case tracking-normal font-serif text-sm text-slate-400">Appears as a caption on the Arc Codex card.</span>
                    <span>{description.length} / 500</span>
                  </div>
                </div>
              </div>
            </Section>
          )}

          {/* Content Type Selector — hidden in video mode */}
          {!isVideoMode && (
            <Section
              title="Medium"
              icon={<Link2 className="w-4 h-4" />}
              sectionId="medium-section"
            >
              <RadioGroup value={contentType} onChange={setContentType} />
            </Section>
          )}

          {/* Content Input — hidden in video mode */}
          {!isVideoMode && (
            <div>
              {contentType === 'text'   && renderTextInput()}
              {contentType === 'url'    && renderUrlInput()}
              {contentType === 'file'   && renderFileUpload()}
              {contentType === 'prompt' && renderPromptInput()}
            </div>
          )}

          {/* Cover Image Accordion */}
          <section
            aria-labelledby="image-section-heading"
            className="py-10 border-b border-slate-800/60"
          >
            <button
              type="button"
              id="image-section-heading"
              onClick={() => setImageOpen(v => !v)}
              aria-expanded={mounted ? imageOpen : false}
              aria-controls="image-accordion-body"
              className="w-full flex items-center justify-between gap-4 outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40 rounded-sm"
            >
              <div className="flex items-center gap-3">
                <div className="text-slate-500" aria-hidden="true">
                  <ImagePlus className="w-4 h-4" />
                </div>
                <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
                  Cover Image <span className="text-slate-500 font-normal">— optional</span>
                </h2>
              </div>
              <div className="flex items-center gap-3">
                {!imageOpen && imagePreview && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={imagePreview}
                    alt=""
                    aria-hidden="true"
                    className="w-16 h-9 object-cover border border-slate-800 shrink-0"
                  />
                )}
                {imageOpen
                  ? <ChevronUp className="w-4 h-4 text-slate-500 shrink-0" aria-hidden="true" />
                  : <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" aria-hidden="true" />
                }
              </div>
            </button>

            <div
              id="image-accordion-body"
              role="region"
              aria-labelledby="image-section-heading"
              className={`grid transition-[grid-template-rows] duration-200 ${mounted && imageOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
            >
              <div className="overflow-hidden">
                <div className="pt-6 space-y-4">
                  <p className="font-serif text-sm text-slate-400 italic leading-relaxed">
                    Optional — if not set, Arc Codex will use the article&apos;s OG image automatically.
                  </p>
                  <div className="flex flex-col gap-4">
                    {/* Hidden file input — accepts images + camera on mobile */}
                    <input
                      ref={imageInputRef}
                      type="file"
                      accept="image/*,image/heic,image/heif"
                      className="hidden"
                      aria-label="Select cover image"
                      onChange={handleImageChange}
                      disabled={status === 'loading' || status === 'success'}
                    />

                    {imagePreview ? (
                      <div className="relative group w-full max-w-md mx-auto">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={imagePreview}
                          alt="Cover image preview"
                          className="w-full h-48 object-cover border border-slate-800"
                        />
                        <button
                          type="button"
                          onClick={clearImage}
                          aria-label="Remove image"
                          className="absolute top-2 right-2 p-1.5 rounded-sm bg-slate-950/80 border border-slate-700 text-slate-300 hover:text-slate-100 hover:border-slate-500 transition-colors focus-visible:ring-1 focus-visible:ring-emerald-400/40"
                        >
                          <XIcon className="h-4 w-4" aria-hidden="true" />
                        </button>
                        <div className="mt-3 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 text-center">
                          {imageFile?.name} · {imageFile ? (imageFile.size / 1024).toFixed(0) : 0} KB
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => imageInputRef.current?.click()}
                        disabled={status === 'loading' || status === 'success'}
                        className="w-full max-w-md mx-auto h-32 border border-dashed border-slate-800 hover:border-slate-600 text-slate-500 hover:text-slate-300 flex flex-col items-center justify-center gap-2 transition-colors rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40"
                        aria-label="Browse for cover image or take photo"
                      >
                        <ImagePlus className="h-6 w-6" aria-hidden="true" />
                        <span className="font-sans text-xs uppercase tracking-[0.2em]">Browse or take photo</span>
                        <span className="font-sans text-[10px] uppercase tracking-[0.18em] text-slate-600">JPG · PNG · WebP · max 10MB</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Status Message */}
          <StatusMessage status={status} message={message} />

          {/* URL fetch failure recovery */}
          {urlFetchFailed && (
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 py-6 border-b border-slate-800/60">
              <div className="flex items-start gap-2 flex-1">
                <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" aria-hidden="true" />
                <span className="font-serif text-sm text-slate-300 italic leading-relaxed">
                  Tip: paste the article text directly using <span className="not-italic font-semibold text-slate-100">Write Text</span> mode below.
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setUrlFetchFailed(false);
                  setStatus('idle');
                  setMessage('');
                  setContentType('text');
                  setContent('');
                }}
                className="shrink-0 px-4 py-2 rounded-sm border border-slate-700 hover:border-slate-500 text-slate-300 hover:text-slate-100 font-sans text-xs uppercase tracking-[0.2em] transition-colors outline-none focus-visible:ring-1 focus-visible:ring-emerald-400/40"
              >
                Switch to Write Text
              </button>
            </div>
          )}

          {/* Publish Controls */}
          <Section
            title="Publish"
            icon={<Rocket className="w-4 h-4" />}
            sectionId="publish-controls"
          >
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
              <div className="flex flex-wrap items-center gap-4">
                <div className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                  {autosavedAt ? (
                    <>Autosaved · <time dateTime={autosavedAt}>{new Date(autosavedAt).toLocaleTimeString()}</time></>
                  ) : (
                    'Not yet saved'
                  )}
                </div>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="font-sans text-xs uppercase tracking-[0.2em] text-slate-500 hover:text-slate-200 hover:bg-slate-800/40 rounded-sm focus-visible:ring-1 focus-visible:ring-emerald-400/40"
                    >
                      Clear All
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="bg-slate-950 border border-slate-800 rounded-sm">
                    <AlertDialogHeader className="space-y-2">
                      <AlertDialogTitle className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
                        Clear everything?
                      </AlertDialogTitle>
                      <AlertDialogDescription className="font-serif text-slate-300 leading-relaxed">
                        This will permanently delete your current draft and reset the form.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter className="flex gap-2">
                      <AlertDialogCancel className="font-sans text-xs uppercase tracking-[0.2em] rounded-sm">Keep it</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => {
                          clearDraft();
                          setTitle('');
                          setMessage('Fresh start.');
                          setStatus('idle');
                        }}
                        className="bg-slate-800 hover:bg-slate-700 text-slate-100 font-sans text-xs uppercase tracking-[0.2em] rounded-sm"
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
                        className="font-sans text-xs uppercase tracking-[0.2em] text-slate-500 hover:text-slate-200 hover:bg-slate-800/40 rounded-sm focus-visible:ring-1 focus-visible:ring-emerald-400/40"
                      >
                        <RefreshCw className="h-3.5 w-3.5 mr-2" aria-hidden="true" />
                        Restore
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent className="bg-slate-900 border border-slate-800 rounded-sm">
                      <p className="font-serif text-sm">Restore your last saved draft</p>
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
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 text-slate-50 font-sans text-xs uppercase tracking-[0.25em] font-semibold px-8 py-5 h-auto rounded-sm transition-colors duration-200 focus-visible:ring-1 focus-visible:ring-emerald-300"
                >
                  <div className="flex items-center gap-3">
                    {status === 'loading' ? (
                      <Loader className="animate-spin h-4 w-4" aria-hidden="true" />
                    ) : status === 'success' ? (
                      <CheckCircle className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Rocket className="h-4 w-4" aria-hidden="true" />
                    )}
                    <span>
                      {status === 'loading'
                        ? (contentType === 'prompt' ? 'Queuing…' : 'Submitting…')
                        : status === 'success'
                        ? 'Submitted'
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
        <footer className="text-center pt-10 pb-6 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <p>© {new Date().getFullYear()} Arc Codex · Protected by A.R.C. Cognitive Framework</p>
        </footer>
      </main>

      {/* Mobile Floating Submit Button */}
      <div className="fixed bottom-8 right-8 z-40 md:hidden">
        <Button
          variant="default"
          size="icon"
          onClick={() => handleRequestSubmit()}
          disabled={status === 'loading' || status === 'success'}
          aria-label={submitLabel}
          className="h-14 w-14 rounded-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 text-slate-50 transition-colors duration-200 focus-visible:ring-1 focus-visible:ring-emerald-300"
        >
          <Send className="h-5 w-5" aria-hidden="true" />
        </Button>
      </div>

      {/* Publish Confirmation Modal */}
      {showConfirmModal && (
        <div
          ref={confirmModalRef}
          tabIndex={-1}
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-slate-950/90 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-modal-title"
        >
          <div className="w-full max-w-md rounded-sm bg-slate-950 border border-slate-800 p-8 space-y-6">
            <div className="space-y-3 pb-4 border-b border-slate-800/60">
              <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">Confirm</div>
              <h2 id="confirm-modal-title" className="font-serif text-2xl font-semibold text-slate-50 tracking-tight">
                Share Story
              </h2>
              <p className="font-serif text-sm text-slate-400 italic leading-relaxed">
                Choose how you want to publish this content.
              </p>
            </div>

            <div className="space-y-3">
              {/* Make Public — primary action */}
              <button
                type="button"
                onClick={() => handleConfirmedPublish('public')}
                className="w-full p-4 rounded-sm border border-emerald-500/60 bg-emerald-600/10 text-slate-100 text-left transition-colors hover:bg-emerald-600/20 focus-visible:ring-1 focus-visible:ring-emerald-400/60 focus-visible:outline-none"
              >
                <div className="font-sans text-xs uppercase tracking-[0.2em] font-semibold text-emerald-300">Make Public</div>
                <div className="font-serif text-sm text-slate-400 mt-1">
                  {isVideoMode
                    ? 'Published to the Arc Codex feed as a video collection.'
                    : 'Published to the Arc Codex feed with full A.R.C. analysis.'}
                </div>
              </button>

              {/* Keep Private — disabled when not signed in */}
              <button
                type="button"
                onClick={() => isAuthed && handleConfirmedPublish('private')}
                disabled={!isAuthed}
                aria-disabled={!isAuthed}
                title={!isAuthed ? 'Sign in to publish privately' : undefined}
                className={`w-full p-4 rounded-sm border text-left transition-colors focus-visible:ring-1 focus-visible:outline-none
                  ${isAuthed
                    ? 'border-slate-700 hover:border-slate-500 hover:bg-slate-800/40 focus-visible:ring-emerald-400/40'
                    : 'border-slate-800 cursor-not-allowed'
                  }`}
              >
                <div className={`font-sans text-xs uppercase tracking-[0.2em] font-semibold flex items-center gap-2 ${isAuthed ? 'text-slate-300' : 'text-slate-600'}`}>
                  Keep Private
                  <span aria-hidden="true">🔒</span>
                  {!isAuthed && (
                    <span className="font-sans text-[10px] tracking-[0.2em] font-normal text-slate-600 ml-1">— sign in required</span>
                  )}
                </div>
                <div className={`font-serif text-sm mt-1 ${isAuthed ? 'text-slate-400' : 'text-slate-600'}`}>Saved privately — visible only to you when logged in.</div>
              </button>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800/60 gap-4">
              <p className="font-serif text-xs text-slate-500 italic leading-relaxed">
                Don&apos;t share personal information or third-party content without permission.{' '}
                <a href="/about/terms" className="text-slate-300 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2 not-italic">
                  Usage Policy
                </a>
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowConfirmModal(false)}
                className="font-sans text-xs uppercase tracking-[0.2em] text-slate-500 hover:text-slate-200 hover:bg-slate-800/40 rounded-sm shrink-0 focus-visible:ring-1 focus-visible:ring-emerald-400/40"
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confetti — emerald, the one accent for success */}
      {showConfetti && (
        <div className="fixed inset-0 pointer-events-none z-50" aria-hidden="true">
          {Array.from({ length: 50 }).map((_, i) => (
            <div
              key={i}
              className="absolute w-2 h-2 bg-emerald-500 rounded-full animate-confetti"
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 0.5}s`,
              }}
            />
          ))}
        </div>
      )}

      {/* Loading overlay */}
      {status === 'loading' && (
        <div
          className="fixed inset-0 bg-slate-950/95 z-40 flex items-center justify-center transition-opacity duration-300"
          role="status"
          aria-live="polite"
          aria-label="Processing your content"
        >
          <div className="text-center px-8 max-w-lg">
            <div className="w-16 h-16 border border-slate-800 border-t-emerald-500 rounded-full mx-auto mb-8 animate-spin" aria-hidden="true" />
            <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500 mb-3">
              {isVideoMode ? 'Publishing' : contentType === 'prompt' ? 'Sending to Arc Codex' : 'Processing'}
            </div>
            <h3 className="font-serif text-2xl font-semibold text-slate-100 tracking-tight mb-3">
              {isVideoMode
                ? 'Publishing your video collection'
                : contentType === 'prompt'
                ? 'Your article is being generated'
                : 'A.R.C. is analyzing your content'}
            </h3>
            <p className="font-serif text-sm text-slate-400 italic leading-relaxed">
              {isVideoMode
                ? 'It will appear in the Arc Codex feed shortly.'
                : contentType === 'prompt'
                ? 'It will appear in the feed shortly.'
                : 'Forty-eight cognitive patterns are at work.'}
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

export default function PublishPage() {
  return (
    <Suspense>
      <PublishPageInner />
    </Suspense>
  );
}
