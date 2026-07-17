import React, { Suspense } from 'react';
import type { Metadata } from 'next';
import FeedClient from '@/components/FeedClient';
import PageWrapper from '@/components/layout/PageWrapper';

// Anonymous ISR: SSR render is stable for all visitors between scribe cycles
// (~13 min). No cookies/headers/auth in this path, so Next.js cannot
// personalize and then cache. Client-side FeedClient + ClientLayout still
// handle sign-in state and authed feed loads via useSession.
export const revalidate = 60;

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

export const metadata: Metadata = {
  alternates: {
    canonical: 'https://arc-codex.com/',
    types: {
      'application/opensearchdescription+xml': '/opensearch.xml',
      'application/rss+xml': '/rss.xml',
    },
  },
};

async function getInitialFeed() {
  try {
    const feedRes = await fetch(`${BACKEND}/api/get_feed?limit=1`, {
      next: { revalidate: 60 },
    });
    return feedRes.ok ? await feedRes.json() : [];
  } catch (e) {
    console.error("A.R.C. Link Failure:", e);
    return [];
  }
}

export default async function Home() {
  const feed = await getInitialFeed();
  return (
    <PageWrapper>
      <Suspense fallback={null}>
        <FeedClient
          initialFeed={feed}
          initialComments={[]}
        />
      </Suspense>
    </PageWrapper>
  );
}
