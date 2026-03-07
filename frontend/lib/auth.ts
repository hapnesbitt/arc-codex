/**
 * Arc Codex — Auth.js v5 Configuration
 * frontend/lib/auth.ts
 *
 * Google + GitHub SSO. JWT sessions (cookie-based, no Redis adapter needed).
 * On sign-in, upserts user preference record in Flask backend.
 *
 * Exports: { handlers, auth, signIn, signOut }
 */

import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import GitHub from "next-auth/providers/github";

export const { handlers, auth, signIn, signOut } = NextAuth({
    trustHost: true,

    providers: [
        Google({
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
            authorization: {
                params: {
                    scope: "openid email profile",
                },
            },
        }),
        GitHub({
            clientId: process.env.GITHUB_CLIENT_ID!,
            clientSecret: process.env.GITHUB_CLIENT_SECRET!,
        }),
    ],

    session: {
        strategy: "jwt",
        maxAge: 30 * 24 * 60 * 60, // 30 days
    },

    callbacks: {
        /**
         * Embed the provider subject ID into the JWT token.
         * `account.providerAccountId` is the stable sub for both Google and GitHub.
         */
        async jwt({ token, account }) {
            if (account?.providerAccountId) {
                token.sub = account.providerAccountId;
            }
            return token;
        },

        /**
         * Expose sub on the session object so client components can use it.
         */
        async session({ session, token }) {
            if (token.sub) {
                session.user.id = token.sub;
            }
            return session;
        },

        /**
         * On every sign-in: upsert user preference record in Flask.
         * Non-fatal — sign-in proceeds even if Flask is temporarily down.
         */
        async signIn({ user, account }) {
            if (!account?.providerAccountId || !user?.email) return true;

            try {
                const backendUrl =
                    process.env.BACKEND_INTERNAL_URL ?? "http://localhost:5005";

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

// ---------------------------------------------------------------------------
// Type augmentation — add `id` to Session.user
// ---------------------------------------------------------------------------
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
