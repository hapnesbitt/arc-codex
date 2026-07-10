// Filename: /frontend/app/plants/page.tsx
// The Plantorium — curated table of contents over arc-codex plant articles.
// Sister surface to /syndromes; reuse this pattern for any (name, name2, url)
// catalog backed by a Python source file on the host.

import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronRight, Leaf, Home } from 'lucide-react';

export const metadata: Metadata = {
  title: 'The Plantorium — Arc Codex',
  description:
    'A curated index of annual and perennial plants profiled in Arc Codex, paired by common and botanical name.',
};

// 5-minute revalidation matches the backend cache window.
export const revalidate = 300;

interface PlantEntry {
  common: string;
  latin: string;
  url: string;
}

interface PlantCatalog {
  annuals: PlantEntry[];
  perennials: PlantEntry[];
}

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  'https://arc-codex.com';

async function getCatalog(): Promise<PlantCatalog> {
  try {
    const res = await fetch(`${BACKEND}/api/plants`, { next: { revalidate: 300 } });
    if (!res.ok) return { annuals: [], perennials: [] };
    return await res.json();
  } catch {
    return { annuals: [], perennials: [] };
  }
}

function PlantRow({ plant }: { plant: PlantEntry }) {
  return (
    <li className="border-b border-slate-800/40">
      <Link
        href={plant.url}
        className="group flex items-baseline gap-3 py-3 px-3 -mx-3 rounded-sm hover:bg-slate-800/40 transition-colors ring-focus"
      >
        <span className="font-serif text-base sm:text-lg font-semibold text-amber-300 group-hover:text-amber-200 transition-colors leading-snug">
          {plant.common}
        </span>
        <span className="font-serif italic text-sm text-slate-400 group-hover:text-slate-300 transition-colors leading-snug truncate">
          {plant.latin}
        </span>
      </Link>
    </li>
  );
}

function CatalogSection({
  id,
  title,
  protocol,
  plants,
}: {
  id: string;
  title: string;
  protocol: string;
  plants: PlantEntry[];
}) {
  return (
    <section id={id} className="scroll-mt-20 py-8 border-b border-slate-800/60">
      <header className="flex items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <Leaf className="h-3.5 w-3.5 text-amber-400/70" aria-hidden="true" />
          <h2 className="font-sans text-xs uppercase tracking-[0.4em] font-semibold text-slate-300">
            {title}
          </h2>
        </div>
        <span className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          {plants.length} {plants.length === 1 ? 'entry' : 'entries'} · {protocol}
        </span>
      </header>

      {plants.length === 0 ? (
        <p className="py-10 text-center font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          Catalog unavailable.
        </p>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 border-t border-slate-800/40">
          {plants.map((p) => (
            <PlantRow key={`${p.common}-${p.latin}`} plant={p} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default async function PlantoriumPage() {
  const { annuals, perennials } = await getCatalog();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-slate-50 font-sans">
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl" />
      </div>

      <nav
        aria-label="Breadcrumb"
        className="relative z-10 border-b border-white/5 bg-slate-900/60 backdrop-blur-sm"
      >
        <ol className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 h-10 flex items-center gap-1 text-sm text-slate-500">
          <li>
            <Link
              href="/"
              className="inline-flex items-center gap-1 hover:text-slate-300 transition-colors focus-visible:outline-none focus-visible:text-amber-400"
              aria-label="Arc Codex home"
            >
              <Home className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Arc Codex</span>
            </Link>
          </li>
          <li aria-hidden="true"><ChevronRight className="h-3.5 w-3.5" /></li>
          <li className="text-slate-400">The Plantorium</li>
        </ol>
      </nav>

      <main className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12 pb-20">
        <header className="text-center py-10 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Curated Botany
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            The Plantorium
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-xl mx-auto">
            A field index of {annuals.length + perennials.length} plants profiled across Arc Codex, paired by common and botanical name.
          </p>
          <nav
            aria-label="Section navigation"
            className="flex items-center justify-center gap-3 pt-2"
          >
            <a
              href="#annuals"
              className="inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-500/5 px-4 py-1.5 font-sans text-[10px] uppercase tracking-[0.25em] text-amber-300 hover:bg-amber-500/10 hover:border-amber-400/50 hover:text-amber-200 transition-colors ring-focus"
            >
              <Leaf className="h-3 w-3 text-amber-400/70" aria-hidden="true" />
              Annuals
            </a>
            <a
              href="#perennials"
              className="inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-500/5 px-4 py-1.5 font-sans text-[10px] uppercase tracking-[0.25em] text-amber-300 hover:bg-amber-500/10 hover:border-amber-400/50 hover:text-amber-200 transition-colors ring-focus"
            >
              <Leaf className="h-3 w-3 text-amber-400/70" aria-hidden="true" />
              Perennials
            </a>
          </nav>
        </header>

        <CatalogSection id="annuals" title="Annuals" protocol="LIFECYCLE_ONE_SEASON" plants={annuals} />
        <CatalogSection id="perennials" title="Perennials" protocol="LIFECYCLE_RECURRING" plants={perennials} />

        <footer className="text-center pt-10 pb-4 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 space-y-2">
          <p>
            {annuals.length} {annuals.length === 1 ? 'annual' : 'annuals'} ·{' '}
            {perennials.length} {perennials.length === 1 ? 'perennial' : 'perennials'} · more coming
          </p>
          <p className="text-slate-600">A.R.C. Botanical Registry · {new Date().getFullYear()}</p>
        </footer>
      </main>
    </div>
  );
}
