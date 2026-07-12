import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { cookies } from "next/headers";

// Wave D R10 (2026-07-11): authed proxy for /api/upload_image.
// Mirrors the submit_content shape — Auth.js session OR shared arc:users
// fallback, then forwards multipart to Flask with X-User-Id set.
// Trust boundary: Caddy strips X-User-Id on every /api/* → Flask hop
// (arc-codex vhost handle /api/* block, request_header -X-User-Id), so an
// external client cannot forge it. Only Next.js runtime on localhost can set
// it — same invariant that submit / submit_content / submit_prompt rely on.

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

async function getLocalAuthUserId(): Promise<string> {
    try {
        const cookieStore = await cookies();
        const cookieHeader = cookieStore.getAll()
            .map(c => `${c.name}=${c.value}`)
            .join('; ');
        const meRes = await fetch(`${BACKEND}/api/me`, {
            cache: 'no-store',
            headers: { Cookie: cookieHeader },
        });
        if (meRes.ok) {
            const me = await meRes.json();
            if (me.logged_in && me.username) return me.username;
        }
    } catch { /* silent */ }
    return "";
}

export async function POST(req: NextRequest): Promise<NextResponse> {
    const session = await auth();
    let userId = session?.user?.id ?? "";

    if (!userId) {
        userId = await getLocalAuthUserId();
    }

    if (!userId) {
        return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const formData = await req.formData();

    const res = await fetch(`${BACKEND}/api/upload_image`, {
        method: "POST",
        headers: {
            "X-User-Id": userId,
        },
        body: formData,
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
}
