/**
 * Arc Codex — User Prefs Proxy
 * frontend/app/api/user/prefs/route.ts
 *
 * Server-side proxy between the browser and the Flask /api/user/prefs endpoint.
 * This is the only place X-User-Id is set — never in browser-side code.
 *
 * Routes:
 *   GET    /api/user/prefs   → GET    Flask /api/user/prefs
 *   POST   /api/user/prefs   → POST   Flask /api/user/prefs  (full upsert)
 *   PATCH  /api/user/prefs   → PATCH  Flask /api/user/prefs  (partial update)
 *   DELETE /api/user/prefs   → DELETE Flask /api/user/prefs
 */

import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

async function proxyToFlask(
    method: string,
    userId: string,
    body?: object
): Promise<NextResponse> {
    const res = await fetch(`${BACKEND}/api/user/prefs`, {
        method,
        headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
        },
        body: body ? JSON.stringify(body) : undefined,
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
}

export async function GET(): Promise<NextResponse> {
    const session = await auth();
    if (!session?.user?.id) {
        return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }
    return proxyToFlask("GET", session.user.id);
}

export async function POST(req: NextRequest): Promise<NextResponse> {
    const session = await auth();
    if (!session?.user?.id) {
        return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }
    const body = await req.json().catch(() => ({}));
    return proxyToFlask("POST", session.user.id, body);
}

export async function PATCH(req: NextRequest): Promise<NextResponse> {
    const session = await auth();
    if (!session?.user?.id) {
        return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }
    const body = await req.json().catch(() => ({}));
    return proxyToFlask("PATCH", session.user.id, body);
}

export async function DELETE(): Promise<NextResponse> {
    const session = await auth();
    if (!session?.user?.id) {
        return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }
    return proxyToFlask("DELETE", session.user.id);
}
