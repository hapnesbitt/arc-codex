/**
 * Arc Codex — Auth.js v5 Configuration
 * frontend/lib/auth.ts
 */

import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import GitHub from "next-auth/providers/github";

const { handlers, auth, signIn, signOut } = NextAuth({
    trustHost: true,
    providers: [
        Google({
            clientId: process.env.GOOGLE_CLIENT_ID ?? "dummy-client-id",
            clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "dummy-client-secret",
            authorization: {
                params: {
                    scope: "openid email profile",
                },
            },
        }),
        GitHub({
            clientId: process.env.GITHUB_CLIENT_ID ?? "dummy-client-id",
            clientSecret: process.env.GITHUB_CLIENT_SECRET ?? "dummy-client-secret",
        }),
    ],
    session: {
        strategy: "jwt",
        maxAge: 30 * 24 * 60 * 60,
    },
    callbacks: {
        async jwt({ token, account }: { token: any; account?: any }) {
            if (account?.providerAccountId) {
                token.sub = account.providerAccountId;
            }
            return token;
        },
        async session({ session, token }: { session: any; token: any }) {
            if (token.sub && session?.user) {
                session.user.id = token.sub;
            }
            return session;
        },
        async signIn({ user, account }: { user: any; account?: any }) {
            if (!account?.providerAccountId || !user?.email) return true;
            try {
                const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";
                await fetch(`${backendUrl}/api/user/prefs`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-User-Id": account.providerAccountId,
                    },
                    body: JSON.stringify({
                        email: user.email,
                        name: user.name ?? "",
                        picture: user.image ?? "",
                    }),
                });
            } catch (err) {
                console.error("[auth] Failed to upsert user prefs:", err);
            }
            return true;
        },
    },
});

export { handlers, auth, signIn, signOut };

declare module "next-auth" {
    interface Session {
        user: {
            id: string;
            name?: string | null;
            email?: string | null;
            image?: string | null;
        };
    }
}
