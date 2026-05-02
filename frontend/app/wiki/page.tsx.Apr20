import React from 'react';
import { readFileSync } from 'fs';
import { join } from 'path';
import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Wiki — Arc Codex',
  description: 'Arc Codex intelligence organized by topic: AI, finance, geopolitics, health, and more.',
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
  const groups = rawGroups.filter(g => g.topic !== 'System Directives');

  return (
    <div className="min-h-screen bg-[#050505] text-slate-200">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <header className="mb-10">
          <nav aria-label="Breadcrumb" className="mb-4 text-sm text-slate-500">
            <Link href="/" className="hover:text-amber-400 transition-colors">Home</Link>
            <span className="mx-2">/</span>
            <span className="text-slate-300">Wiki</span>
          </nav>
          <h1 className="font-serif text-3xl font-bold text-slate-50 mb-2">Arc Codex Wiki</h1>
          <p className="text-slate-400 text-sm">Intelligence organized by topic</p>
        </header>

        <div className="space-y-10">
          {groups.map(group => (
            <section key={group.topic} aria-labelledby={`topic-${toSlug(group.topic)}`}>
              <h2
                id={`topic-${toSlug(group.topic)}`}
                className="text-xs font-bold uppercase tracking-widest text-amber-400 mb-4 border-b border-slate-700/50 pb-2"
              >
                {group.topic}
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {group.directives.map(directive => (
                  <Link
                    key={directive.name}
                    href={`/wiki/${toSlug(directive.name)}`}
                    className="block p-4 rounded-xl border border-slate-700/60 bg-slate-900/40 hover:border-amber-400/50 hover:bg-slate-800/60 transition-all duration-200 group"
                  >
                    <span className="text-slate-200 font-medium group-hover:text-amber-300 transition-colors text-sm leading-snug">
                      {directive.name}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
