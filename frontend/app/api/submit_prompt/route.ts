/**
 * Arc Codex — Submit Prompt Proxy
 * frontend/app/api/submit_prompt/route.ts
 *
 * Server-side proxy between the browser and Flask /api/submit_prompt.
 * Injects X-User-Id from session so Flask can store owner on the article.
 * If user is not authenticated, still proxies but with empty X-User-Id.
 */

import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

export async function POST(req: NextRequest): Promise<NextResponse> {
    const session = await auth();
    const userId = session?.user?.id ?? "";

    const body = await req.json().catch(() => ({}));

    const res = await fetch(`${BACKEND}/api/submit_prompt`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
        },
        body: JSON.stringify(body),
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
}
