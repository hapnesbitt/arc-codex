// Next.js not-found.tsx — automatically returns HTTP 404. No changes needed for status code.
import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '404 Not Found — Arc Codex',
  robots: { index: false, follow: false },
};

const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name: '404 Not Found',
  description: 'The requested page could not be found on Arc Codex.',
};

export default function NotFound() {
  return (
    <>
      <span aria-hidden="true" style={{ display: 'none' }} dangerouslySetInnerHTML={{ __html: '<!-- 404: Not Found -->' }} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
        <p className="text-7xl font-black text-slate-200 mb-4">404</p>
        <p className="text-slate-400 mb-8">The page you requested could not be found.</p>
        <div className="flex gap-4">
          <Link
            href="/"
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-300 hover:text-white hover:border-white/20 transition-all text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
          >
            Return to Feed
          </Link>
          <Link
            href="/wiki"
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-300 hover:text-white hover:border-white/20 transition-all text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
          >
            Browse Wiki
          </Link>
        </div>
      </div>
    </>
  );
}
