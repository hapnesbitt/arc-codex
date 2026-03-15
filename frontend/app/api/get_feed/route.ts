/**
 * Arc Codex — Get Feed Proxy
 * frontend/app/api/get_feed/route.ts
 *
 * Server-side proxy between the browser and Flask /api/get_feed.
 * Injects X-User-Id from session so Flask can include the user's
 * private articles in the feed response.
 * If user is not authenticated, proxies with empty X-User-Id
 * (private articles will be filtered out).
 */

import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

export async function GET(req: NextRequest): Promise<NextResponse> {
    const session = await auth();
    const userId = session?.user?.id ?? "";

    // Forward all query params to Flask
    const { searchParams } = new URL(req.url);
    const queryString = searchParams.toString();
    const url = `${BACKEND}/api/get_feed${queryString ? `?${queryString}` : ""}`;

    const res = await fetch(url, {
        method: "GET",
        headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
        },
    });

    const data = await res.json().catch(() => ([]));
    return NextResponse.json(data, { status: res.status });
}
