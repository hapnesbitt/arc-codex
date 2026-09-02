'use client';

import { useEffect, useState } from 'react';

export function ListenButton({ text, label }: { text: string; label: string }) {
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  function toggle() {
    if (!('speechSynthesis' in window)) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`${speaking ? 'Stop' : 'Listen to'} ${label}`}
      className="inline-flex items-center gap-2 border border-amber-300/50 px-4 py-2.5 font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 transition-colors hover:border-amber-200 ring-focus"
    >
      {speaking ? '■ Stop' : '▶ Listen'}
    </button>
  );
}
