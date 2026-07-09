import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { cookies } from "next/headers";

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
    const sessionName = session?.user?.name ?? "";

    if (!userId) {
        userId = await getLocalAuthUserId();
    }

    if (!userId) {
        return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    // Author is derived from the session, never from the request body — this
    // closes the impersonation vector where an anon POST could claim to be
    // "A.R.C. Counter-Analyst" or another user. Body's `author` (if any) is
    // ignored; sessionName wins.
    const body = await req.json().catch(() => ({}));
    body.author = sessionName || userId;

    const res = await fetch(`${BACKEND}/api/submit_comment`, {
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
