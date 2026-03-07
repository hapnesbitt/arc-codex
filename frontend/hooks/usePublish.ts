'use client';
// Filename: /frontend/hooks/usePublish.ts
//
// v2 — Fixes:
//   - localStorage key renamed hapenews.publish.draft → arc-codex.publish.draft
//   - handlePublish reads error response body before throwing
//   - progress removed — was stuck at 15 and never advanced, misleading to UI

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

const DRAFT_KEY = 'arc-codex.publish.draft';

export const usePublish = () => {
  const router = useRouter();
  const [title, setTitle]       = useState('');
  const [content, setContent]   = useState('');
  const [category, setCategory] = useState('general');
  const [status, setStatus]     = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage]   = useState('');

  // --- AUTOSAVE RECOVERY ---
  useEffect(() => {
    const saved = localStorage.getItem(DRAFT_KEY);
    if (saved) {
      try {
        const { title: t, content: c, category: cat } = JSON.parse(saved);
        setTitle(t || '');
        setContent(c || '');
        setCategory(cat || 'general');
      } catch (e) {
        console.error("Draft recovery failed:", e);
      }
    }
  }, []);

  // --- AUTOSAVE PERSISTENCE (3s debounce) ---
  useEffect(() => {
    const timer = setTimeout(() => {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ title, content, category }));
    }, 3000);
    return () => clearTimeout(timer);
  }, [title, content, category]);

  const handlePublish = async () => {
    if (!title.trim()) {
      setStatus('error');
      setMessage("Headline required for A.R.C. indexing.");
      return;
    }

    setStatus('loading');
    setMessage('');

    try {
      const res = await fetch('/api/submit_content', {
        method: 'POST',
        body: JSON.stringify({ title, content, category, type: 'manual' }),
        headers: { 'Content-Type': 'application/json' },
      });

      if (res.ok) {
        setStatus('success');
        localStorage.removeItem(DRAFT_KEY);
        setTimeout(() => router.push('/'), 1500);
      } else {
        // Surface whatever the backend said — much more useful than a generic message
        let errorDetail = `Server error (${res.status})`;
        try {
          const body = await res.json();
          if (body?.error) errorDetail = body.error;
          else if (body?.message) errorDetail = body.message;
        } catch {
          // Response wasn't JSON — use status text
          if (res.statusText) errorDetail = `${res.status}: ${res.statusText}`;
        }
        throw new Error(errorDetail);
      }
    } catch (err) {
      setStatus('error');
      const msg = err instanceof Error ? err.message : "Sync failed. Is the Flask backend (port 5005) alive?";
      setMessage(msg);
    }
  };

  return {
    title, setTitle,
    content, setContent,
    category, setCategory,
    status,
    message,
    handlePublish,
  };
};
