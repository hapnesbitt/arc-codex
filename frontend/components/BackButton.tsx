'use client';

import { useRouter } from 'next/navigation';
import { ChevronLeft } from 'lucide-react';

export default function BackButton() {
  const router = useRouter();

  const handleClick = () => {
    if (typeof window === 'undefined') return;
    let sameOrigin = false;
    try {
      sameOrigin =
        !!document.referrer &&
        new URL(document.referrer).origin === window.location.origin;
    } catch {
      sameOrigin = false;
    }
    if (sameOrigin && window.history.length > 1) {
      router.back();
    } else {
      router.push('/');
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label="Back to feed"
      className="group flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/5 text-slate-400 hover:text-amber-400 hover:border-amber-500/30 transition-all duration-300"
    >
      <ChevronLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
      <span className="text-[10px] font-black uppercase tracking-widest">Back to feed</span>
    </button>
  );
}
