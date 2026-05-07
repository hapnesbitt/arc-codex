'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Search, X } from 'lucide-react';

interface SearchResult {
  gutenberg_id: string;
  title: string;
  author: string;
  language: string;
  download_count: number;
  year_published: string;
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

export default function LibrarySearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      fetch(`${BACKEND}/api/library/search?q=${encodeURIComponent(q)}`)
        .then((res) => (res.ok ? res.json() : []))
        .then((data: SearchResult[]) => {
          if (!cancelled) setResults(data);
        })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  return (
    <div className="my-8">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by title or author…"
          className="w-full pl-10 pr-10 py-3 bg-slate-900/50 border border-slate-800 rounded-sm font-serif text-base text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-400/40 focus:border-emerald-700"
          aria-label="Search the Library"
        />
        {query && (
          <button
            onClick={() => setQuery('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {loading && (
        <p className="mt-4 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 text-center">
          Searching…
        </p>
      )}

      {!loading && query.trim().length >= 2 && results.length === 0 && (
        <p className="mt-4 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 text-center">
          No matches.
        </p>
      )}

      {results.length > 0 && (
        <ul className="mt-4 border-t border-slate-800/40">
          {results.map((work) => (
            <li key={work.gutenberg_id} className="border-b border-slate-800/40">
              <Link
                href={`/library/${work.gutenberg_id}`}
                className="block py-3 px-2 -mx-2 hover:bg-slate-800/30 transition-colors rounded-sm"
              >
                <div className="font-serif text-base text-slate-100">{work.title}</div>
                <div className="font-serif italic text-sm text-slate-400">{work.author}</div>
                <div className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 mt-1">
                  {work.language} · {work.download_count.toLocaleString()} Gutenberg downloads
                  {work.year_published && ` · ${work.year_published}`}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
