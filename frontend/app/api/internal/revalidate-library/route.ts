import { timingSafeEqual } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { revalidateLibraryLanding } from '@/lib/library-cache';

export const dynamic = 'force-dynamic';

function isAuthorized(request: NextRequest, expected: string): boolean {
  const authorization = request.headers.get('authorization') ?? '';
  if (!authorization.startsWith('Bearer ')) return false;

  const supplied = authorization.slice('Bearer '.length);
  const suppliedBytes = Buffer.from(supplied);
  const expectedBytes = Buffer.from(expected);
  return suppliedBytes.length === expectedBytes.length
    && timingSafeEqual(suppliedBytes, expectedBytes);
}

export async function POST(request: NextRequest) {
  const secret = process.env.LIBRARY_REVALIDATE_SECRET ?? '';
  if (!secret) {
    return NextResponse.json(
      { error: 'Library revalidation is not configured' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }
  if (!isAuthorized(request, secret)) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  revalidateLibraryLanding();
  return NextResponse.json(
    { revalidated: true, path: '/library' },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
