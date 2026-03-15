export const dynamic = "force-dynamic";
import React from 'react';
import { auth } from "@/lib/auth";
import FeedClient from '@/components/FeedClient';
import PageWrapper from '@/components/layout/PageWrapper';

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

async function getInitialData(userId: string) {
  try {
    const [feedRes, commentsRes] = await Promise.all([
      fetch(`${BACKEND}/api/get_feed`, {
        cache: 'no-store',
        headers: { 'X-User-Id': userId },
      }),
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
  const session = await auth();
  const userId = session?.user?.id ?? "";
  const data = await getInitialData(userId);
  return (
    <PageWrapper>
      <FeedClient
        initialFeed={data.feed}
        initialComments={data.comments}
      />
    </PageWrapper>
  );
}
