export const dynamic = "force-dynamic";
import React from 'react';
import { auth } from "@/lib/auth";
import FeedClient from '@/components/FeedClient';
import PageWrapper from '@/components/layout/PageWrapper';

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

async function getInitialFeed(userId: string) {
  try {
    const feedRes = await fetch(`${BACKEND}/api/get_feed`, {
      cache: 'no-store',
      headers: { 'X-User-Id': userId },
    });
    return feedRes.ok ? await feedRes.json() : [];
  } catch (e) {
    console.error("A.R.C. Link Failure:", e);
    return [];
  }
}

export default async function Home() {
  const session = await auth();
  const userId = session?.user?.id ?? "";

  const feed = await getInitialFeed(userId);
  return (
    <PageWrapper>
      <FeedClient
        initialFeed={feed}
        initialComments={[]}
      />
    </PageWrapper>
  );
}
