import { MetadataRoute } from 'next';
import { readFileSync } from 'fs';
import { join } from 'path';

interface DirectiveEntry { name: string }
interface TopicGroup { topic: string; directives: DirectiveEntry[] }

const toSlug = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: 'https://arc-codex.com', changeFrequency: 'hourly', priority: 1 },
    { url: 'https://arc-codex.com/wiki', changeFrequency: 'weekly', priority: 0.8 },
    { url: 'https://arc-codex.com/search', changeFrequency: 'monthly', priority: 0.5 },
  ];

  // Wiki directive pages (static, from directives.json)
  try {
    const directivesPath = join(process.cwd(), 'public', 'directives.json');
    const groups: TopicGroup[] = JSON.parse(readFileSync(directivesPath, 'utf-8'));
    for (const group of groups) {
      if (group.topic === 'System Directives') continue;
      for (const d of group.directives) {
        entries.push({
          url: `https://arc-codex.com/wiki/${toSlug(d.name)}`,
          changeFrequency: 'daily',
          priority: 0.7,
        });
      }
    }
  } catch { /* directives.json missing at build time — skip */ }

  // Article pages (dynamic, from Flask /api/sitemap)
  try {
    const res = await fetch(`${BACKEND}/api/sitemap`, {
      next: { revalidate: 3600 },
    });
    if (res.ok) {
      const ids: string[] = await res.json();
      for (const id of ids) {
        entries.push({
          url: `https://arc-codex.com/article/${id}`,
          changeFrequency: 'weekly',
          priority: 0.6,
        });
      }
    }
  } catch { /* backend offline at build time — skip articles */ }

  return entries;
}
