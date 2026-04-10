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

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import {
  Send, Loader, CheckCircle, RefreshCw, Upload,
  Sparkles, FileText, Link2, Wand2,
  Rocket, Globe, Crown, Shield, PenLine, ImagePlus, X as XIcon,
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
  {
    id: 'prompt',
    label: 'Write Prompt',
    icon: <PenLine className="h-5 w-5" aria-hidden="true" />,
    borderColor: 'border-purple-400',
    bgColor: 'bg-purple-400/10',
    textColor: 'text-purple-300',
    shadowColor: 'shadow-[0_0_20px_rgba(168,85,247,0.3)]',
    ariaDescription: 'Describe what you want Arc Codex to write for you',
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
  const { data: session } = useSession();
  const isAuthed = !!session?.user;
  const [title, setTitle]               = useState('');
  const [content, setContent]           = useState('');
  const [contentType, setContentType]   = useState<ContentType>('text');
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
  const [urlFetchFailed, setUrlFetchFailed] = useState(false);
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
    if (contentType === 'url' && (!content.trim() || !isProbablyUrl(content.trim())) && !imageFile && !uploadedImageUrl) {
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
  }, [title, content, contentType, file, isProbablyUrl]);

  // Step 2: user confirmed — actually publish
  const handleConfirmedPublish = useCallback(async (visibility: 'public' | 'private' = 'public') => {
    setShowConfirmModal(false);
    setStatus('loading');

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
        // If image attached but no valid URL, submit as text
        const effectiveContentType = (contentType === 'url' && !isProbablyUrl(content.trim()))
          ? 'text' : contentType;
        const effectiveContent = effectiveContentType === 'text' && !content.trim()
          ? (title.trim() || 'Photo submission') : content.trim();
        const resp = await fetch('/api/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content_type: effectiveContentType,
            content: effectiveContent,
            title: title.trim(),
            image_url: resolvedImageUrl || undefined,
            visibility,
          }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Unknown error from server.');

        if (effectiveContentType === 'url' && data.job_id) {
          // URL submissions: show optimistic message and poll for fetch result
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
  }, [title, content, contentType, file, clearDraft, router, isProbablyUrl, imageFile, uploadedImageUrl, pollJobStatus]);

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
    if (selectedFile && ALLOWED_FILE_TYPES.includes(selectedFile.type)) {
      setFile(selectedFile);
      setContent(selectedFile.name);
      setMessage('File ready.');
      setStatus('idle');
    } else {
      setMessage('Please upload a supported file type (.txt, .md, .pdf, .docx, .odt)');
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
            Paste any article or YouTube URL — A.R.C. will fetch and analyze it
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

  const renderPromptInput = () => (
    <Section
      title="Describe What You Want"
      icon={<Wand2 className="w-8 h-8 text-purple-400" />}
      gradient="border-purple-400/50"
      sectionId="content-prompt"
    >
      <div className="space-y-4">
        <p className="text-sm text-slate-400 font-serif italic">
          Arc Codex will write a full article based on your prompt, then publish it with A.R.C. analysis.
        </p>
        <label htmlFor="prompt-textarea" className="sr-only">Writing prompt</label>
        <Textarea
          id="prompt-textarea"
          value={content}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setContent(e.target.value)}
          rows={6}
          placeholder="Write a long article explaining how someone should decide whether a cat or dog would be better for them..."
          aria-describedby="prompt-stats"
          className="bg-slate-800/20 border-slate-600/50 text-slate-100 font-serif text-base leading-relaxed focus:border-purple-400/50 focus:ring-purple-400/25 resize-none transition-colors"
          disabled={status === 'loading' || status === 'success'}
          maxLength={2000}
        />
        <div id="prompt-stats" className="flex justify-between items-center">
          <div className="text-sm text-slate-400 font-serif">
            {content.length}/2000 characters
            {content.length > 0 && content.length < 10 && (
              <span className="text-amber-400 ml-2">— be more descriptive</span>
            )}
          </div>
          <Badge variant="outline" className="border-purple-400/30 text-purple-300 font-mono text-xs">
            Ctrl+Enter to submit
          </Badge>
        </div>
        <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-400/20 text-sm text-purple-300 font-serif">
          💡 Title is optional in prompt mode — Arc Codex will derive one from the generated article.
        </div>
      </div>
    </Section>
  );

  return (
    <PageWrapper>
      {/* Skip link */}
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

        <form id="publish-form" onSubmit={handleRequestSubmit} aria-label="Publish content" className="space-y-12">

          {/* Title Section */}
          <Section
            title="Title Your Creation"
            icon={<Crown className="w-8 h-8 text-amber-400" />}
            gradient="border-amber-400/50"
            sectionId="title-section"
          >
            <div className="space-y-4">
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
                    : 'Give your article a title...'
                }
                aria-describedby="title-hint title-counter"
                aria-required={contentType !== 'prompt'}
                className="bg-slate-800/30 border-slate-600/50 text-slate-100 text-lg h-14 focus:border-amber-400/50 focus:ring-amber-400/25 font-serif transition-colors"
                disabled={status === 'loading' || status === 'success'}
                maxLength={200}
              />
              <div className="flex justify-between items-center">
                <span id="title-hint" className="text-sm text-slate-400 font-serif italic">
                  {contentType === 'prompt' ? 'Optional in prompt mode' : 'Clear and descriptive works best'}
                </span>
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
            {contentType === 'text'   && renderTextInput()}
            {contentType === 'url'    && renderUrlInput()}
            {contentType === 'file'   && renderFileUpload()}
            {contentType === 'prompt' && renderPromptInput()}
          </div>

          {/* Image Selection */}
          <Section
            title="Cover Image"
            icon={<ImagePlus className="w-8 h-8 text-pink-400" />}
            gradient="border-pink-400/50"
            sectionId="image-section"
          >
            <p className="text-sm text-slate-400 font-serif italic">
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
                    className="w-full h-48 object-cover rounded-xl border border-pink-400/30"
                  />
                  <button
                    type="button"
                    onClick={clearImage}
                    aria-label="Remove image"
                    className="absolute top-2 right-2 p-1.5 rounded-full bg-slate-900/80 border border-slate-600 text-slate-300 hover:text-white hover:border-red-400 transition-colors focus-visible:ring-2 focus-visible:ring-red-400"
                  >
                    <XIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <div className="mt-2 text-sm text-slate-400 font-serif text-center">
                    {imageFile?.name} · {imageFile ? (imageFile.size / 1024).toFixed(0) : 0}KB
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => imageInputRef.current?.click()}
                  disabled={status === 'loading' || status === 'success'}
                  className="w-full max-w-md mx-auto h-32 rounded-xl border-2 border-dashed border-pink-400/30 hover:border-pink-400/60 text-slate-400 hover:text-pink-300 flex flex-col items-center justify-center gap-2 transition-colors focus-visible:ring-2 focus-visible:ring-pink-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                  aria-label="Browse for cover image or take photo"
                >
                  <ImagePlus className="h-8 w-8" aria-hidden="true" />
                  <span className="font-serif text-sm">Browse or take photo</span>
                  <span className="font-serif text-xs opacity-60">JPG, PNG, WebP · max 10MB</span>
                </button>
              )}
            </div>
          </Section>

          {/* Status Message */}
          <StatusMessage status={status} message={message} />

          {/* URL fetch failure recovery */}
          {urlFetchFailed && (
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 p-4 rounded-xl border border-amber-500/30 bg-amber-600/10">
              <span className="text-sm text-amber-300 font-serif flex-1">
                Tip: paste the article text directly using the <strong>Write Text</strong> mode below.
              </span>
              <button
                type="button"
                onClick={() => {
                  setUrlFetchFailed(false);
                  setStatus('idle');
                  setMessage('');
                  setContentType('text');
                  setContent('');
                }}
                className="shrink-0 px-4 py-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-sm font-semibold transition-colors outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
              >
                Switch to Write Text
              </button>
            </div>
          )}

          {/* Publish Controls */}
          <Section
            title="Publish Controls"
            icon={<Rocket className="w-8 h-8 text-amber-400" />}
            gradient="border-amber-400/50"
            sectionId="publish-controls"
          >
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
              <div className="flex flex-wrap items-center gap-4">
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
                        ? (contentType === 'prompt' ? 'Queuing...' : 'Submitting...')
                        : status === 'success'
                        ? 'Submitted!'
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

      {/* Mobile Floating Submit Button */}
      <div className="fixed bottom-8 right-8 z-40 md:hidden">
        <Button
          variant="default"
          size="icon"
          onClick={() => handleRequestSubmit()}
          disabled={status === 'loading' || status === 'success'}
          aria-label={submitLabel}
          className="h-16 w-16 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 shadow-2xl shadow-amber-500/50 border border-amber-400/50 transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
        >
          <Send className="h-6 w-6" aria-hidden="true" />
        </Button>
      </div>

      {/* Publish Confirmation Modal */}
      {showConfirmModal && (
        <div
          ref={confirmModalRef}
          tabIndex={-1}
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-modal-title"
        >
          <div className="w-full max-w-md rounded-2xl bg-slate-900/95 border border-amber-400/40 backdrop-blur-xl shadow-[0_0_40px_rgba(251,191,36,0.3)] p-8 space-y-6">
            <div className="space-y-2">
              <h2 id="confirm-modal-title" className="text-2xl font-bold text-slate-50 font-sans tracking-tight">
                Share Story
              </h2>
              <p className="text-slate-400 font-serif text-sm">
                Choose how you want to publish this content.
              </p>
            </div>

            <div className="space-y-3">
              {/* Make Public — primary action */}
              <button
                type="button"
                onClick={() => handleConfirmedPublish('public')}
                className="w-full p-4 rounded-xl border-2 border-amber-400 bg-amber-400/10 text-amber-300 font-serif text-left transition-colors hover:bg-amber-400/20 focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:outline-none"
              >
                <div className="font-bold text-base">Make Public</div>
                <div className="text-sm opacity-75 mt-0.5">Published to the Arc Codex feed with full A.R.C. analysis</div>
              </button>

              {/* Keep Private — disabled when not signed in */}
              <button
                type="button"
                onClick={() => isAuthed && handleConfirmedPublish('private')}
                disabled={!isAuthed}
                aria-disabled={!isAuthed}
                title={!isAuthed ? 'Sign in to publish privately' : undefined}
                className={`w-full p-4 rounded-xl border-2 font-serif text-left transition-colors focus-visible:ring-2 focus-visible:outline-none
                  ${isAuthed
                    ? 'border-slate-500/60 bg-slate-800/30 text-slate-300 hover:border-slate-400/60 hover:bg-slate-800/50 focus-visible:ring-slate-400'
                    : 'border-slate-700/30 bg-slate-800/10 text-slate-600 cursor-not-allowed'
                  }`}
              >
                <div className="font-bold text-base flex items-center gap-2">
                  Keep Private
                  <span className="text-xs">🔒</span>
                  {!isAuthed && (
                    <span className="text-xs font-normal text-slate-500 ml-1">— sign in required</span>
                  )}
                </div>
                <div className="text-sm opacity-75 mt-0.5">Saved privately — visible only to you when logged in</div>
              </button>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-700/50">
              <p className="text-xs text-slate-500 font-serif">
                Don&apos;t share personal information or third-party content without permission.{' '}
                <a href="/about/terms" className="text-amber-400/70 hover:text-amber-400 underline underline-offset-2">
                  Usage Policy
                </a>
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowConfirmModal(false)}
                className="text-slate-400 hover:text-slate-200 font-serif ml-4 shrink-0 focus-visible:ring-2 focus-visible:ring-amber-400/70"
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confetti */}
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

      {/* Loading overlay */}
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
              {contentType === 'prompt' ? 'Sending to Arc Codex...' : 'Processing Your Content'}
            </h3>
            <p className="text-slate-400 font-serif italic">
              {contentType === 'prompt'
                ? 'Your article will be generated and appear in the feed shortly.'
                : 'A.R.C. is analyzing with 48 cognitive patterns...'}
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
