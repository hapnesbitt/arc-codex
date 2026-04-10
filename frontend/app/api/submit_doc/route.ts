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

    if (!userId) {
        userId = await getLocalAuthUserId();
    }

    // Forward the multipart form data as-is
    const formData = await req.formData();

    const res = await fetch(`${BACKEND}/api/submit_doc`, {
        method: "POST",
        headers: {
            "X-User-Id": userId,
        },
        body: formData,
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
}
