// Filename: /frontend/app/wiki/page.tsx
// Wiki — Library Index
// Librarian aesthetic: alphabetized table of contents over directives.json.

import React from 'react';
import { readFileSync } from 'fs';
import { join } from 'path';
import Link from 'next/link';
import type { Metadata } from 'next';
import { ChevronRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Library — Arc Codex',
  description: 'A formal classification of intelligence and discourse patterns.',
  alternates: {
    canonical: 'https://arc-codex.com/wiki',
    types: {
      'application/opensearchdescription+xml': '/opensearch.xml',
      'application/rss+xml': '/rss.xml',
    },
  },
};

interface DirectiveEntry {
  name: string;
}

interface TopicGroup {
  topic: string;
  directives: DirectiveEntry[];
}

const toSlug = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export default function WikiPage() {
  const directivesPath = join(process.cwd(), 'public', 'directives.json');
  const rawGroups: TopicGroup[] = JSON.parse(readFileSync(directivesPath, 'utf-8'));
  const groups = rawGroups
    .filter(g => g.topic !== 'System Directives')
    .map(g => ({
      ...g,
      directives: [...g.directives].sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => a.topic.localeCompare(b.topic));

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Library · Arc Codex
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Taxonomy
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
            A formal classification of intelligence and discourse patterns — the complete index of A.R.C. directives, alphabetized by topic.
          </p>
        </header>

        {/* Topic groups */}
        {groups.map((group) => (
          <section key={group.topic} className="py-10 border-b border-slate-800/60">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">
                {group.topic}
              </h2>
              <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500">
                {group.directives.length} {group.directives.length === 1 ? 'Directive' : 'Directives'}
              </span>
            </div>

            <ul className="border-t border-slate-800/40">
              {group.directives.map((directive) => (
                <li key={directive.name} className="border-b border-slate-800/40">
                  <Link
                    href={`/wiki/${toSlug(directive.name)}`}
                    className="flex items-center justify-between gap-4 py-4 px-2 -mx-2 hover:bg-slate-800/30 transition-colors group rounded-sm ring-focus"
                  >
                    <h3 className="font-serif text-lg text-slate-100 group-hover:text-slate-50 transition-colors leading-snug">
                      {directive.name}
                    </h3>
                    <ChevronRight
                      className="h-4 w-4 text-slate-600 group-hover:text-slate-300 transition-colors shrink-0"
                      aria-hidden="true"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}

        {/* Footer */}
        <footer className="text-center pt-10 pb-6 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <p>A.R.C. Codex · Directive Registry · {new Date().getFullYear()}</p>
        </footer>
      </main>
    </div>
  );
}
