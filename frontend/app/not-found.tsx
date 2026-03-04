"use client"; // This is mandatory in v16 for custom 404s with layout components

import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#0c1e3a] text-yellow-400 p-4">
      <div className="font-mono border border-yellow-400/30 p-8 bg-black/20 backdrop-blur-md">
        <h2 className="text-2xl mb-4 text-cyan-400">🦊 [FOX-01] SECURE_LOG: 404</h2>
        <p className="text-slate-400 mb-6">Requested intelligence node is offline or restricted.</p>
        <Link 
          href="/" 
          className="text-yellow-400 hover:text-white border-b border-yellow-400 transition-all"
        >
          RETURN TO MAIN FEED
        </Link>
      </div>
    </div>
  );
}
