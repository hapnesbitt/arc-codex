/**
 * Arc Codex — Auth.js Route Handler
 * frontend/app/api/auth/[...nextauth]/route.ts
 *
 * Catch-all handler for all Auth.js endpoints:
 *   GET  /api/auth/providers
 *   GET  /api/auth/session
 *   GET  /api/auth/csrf
 *   GET  /api/auth/signin
 *   GET  /api/auth/signout
 *   GET  /api/auth/callback/google
 *   POST /api/auth/signin/google
 *   POST /api/auth/signout
 */

import { handlers } from "@/lib/auth";

export const { GET, POST } = handlers;
