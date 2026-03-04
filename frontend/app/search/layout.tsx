import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Search | Arc Codex',
  description: 'Search across all Arc Codex intelligence articles — full-text search powered by Solr.',
};

export default function SearchLayout({ children }: { children: React.ReactNode }) {
  return children;
}
