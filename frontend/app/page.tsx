export const dynamic = "force-dynamic";
import React from 'react';
import FeedClient from '@/components/FeedClient';
import PageWrapper from '@/components/layout/PageWrapper';

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

async function getInitialData() {
  try {
    const [feedRes, commentsRes] = await Promise.all([
      fetch(`${BACKEND}/api/get_feed`,     { cache: 'no-store' }),
      fetch(`${BACKEND}/api/get_comments`, { cache: 'no-store' })
    ]);
    const feed     = feedRes.ok     ? await feedRes.json()     : [];
    const comments = commentsRes.ok ? await commentsRes.json() : [];
    return { feed, comments };
  } catch (e) {
    console.error("A.R.C. Link Failure:", e);
    return { feed: [], comments: [] };
  }
}

export default async function Home() {
  const data = await getInitialData();
  return (
    <PageWrapper>
      <FeedClient
        initialFeed={data.feed}
        initialComments={data.comments}
      />
    </PageWrapper>
  );
}
