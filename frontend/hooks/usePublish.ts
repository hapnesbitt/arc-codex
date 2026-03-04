'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';

export const usePublish = () => {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('general');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [progress, setProgress] = useState(0);

  // --- AUTOSAVE RECOVERY ---
  useEffect(() => {
    const saved = localStorage.getItem('hapenews.publish.draft');
    if (saved) {
      try {
        const { title: t, content: c, category: cat } = JSON.parse(saved);
        setTitle(t || ''); setContent(c || ''); setCategory(cat || 'general');
      } catch (e) { console.error("Draft recovery failed"); }
    }
  }, []);

  // --- AUTOSAVE PERSISTENCE (3s Delay) ---
  useEffect(() => {
    const timer = setTimeout(() => {
      localStorage.setItem('hapenews.publish.draft', JSON.stringify({ title, content, category }));
    }, 3000);
    return () => clearTimeout(timer);
  }, [title, content, category]);

  const handlePublish = async () => {
    if (!title.trim()) {
      setStatus('error');
      setMessage("✋ Headline required for A.R.C. indexing.");
      return;
    }
    setStatus('loading');
    setProgress(15);

    try {
      const res = await fetch('/api/submit_content', {
        method: 'POST',
        body: JSON.stringify({ title, content, category, type: 'manual' }),
        headers: { 'Content-Type': 'application/json' }
      });
      if (res.ok) {
        setStatus('success');
        localStorage.removeItem('hapenews.publish.draft');
        setTimeout(() => router.push('/'), 1500);
      } else { throw new Error(); }
    } catch {
      setStatus('error');
      setMessage("Sync failed. Is the Flask backend (Port 5005) alive?");
    }
  };

  return { title, setTitle, content, setContent, category, setCategory, status, message, progress, handlePublish };
};
