// site.ts — per-site identity primitives, read from build-time env.
//
// Frontend companion to backend/site_config.py. Reads NEXT_PUBLIC_SITE_*
// vars baked in at build time (see Dockerfile.frontend build-args block)
// with hardcoded fallbacks matching Arc Codex — the fallbacks exist so
// this module is safe to import in local dev without env vars set, and
// so a rebrand that forgets to set the build args produces a working
// page (with the wrong branding, visibly) rather than an undefined
// crash.
//
// Everything else in the frontend that would otherwise hardcode
// "Arc Codex" / "arc-codex.com" / a specific canonical URL should read
// from here. cardConfig.ts is a related but separate concern — it
// carries per-site FEATURE flags and per-site EXTERNAL service URLs
// (video subdomain, quiz deeplink template, dashboard link); this
// module is just brand identity.

const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME ?? 'Arc Codex';
const SITE_BASE_URL = process.env.NEXT_PUBLIC_SITE_BASE_URL ?? 'https://arc-codex.com';
const SITE_DEFAULT_IMAGE = process.env.NEXT_PUBLIC_SITE_DEFAULT_IMAGE ?? '/uploads/arc-codex-default.jpg';

// Derived from base_url — no separate env var needed. Strips protocol
// so callers building host-only strings (canonical URLs already have
// the scheme via SITE_BASE_URL) get the shape they expect.
const SITE_DOMAIN = SITE_BASE_URL.replace(/^https?:\/\//, '').replace(/\/$/, '');

export const site = {
  name: SITE_NAME,
  baseUrl: SITE_BASE_URL,
  domain: SITE_DOMAIN,
  defaultImagePath: SITE_DEFAULT_IMAGE,

  /** Absolute URL to an article — replaces hardcoded
   *  `https://arc-codex.com/article/${id}` constructions across the frontend. */
  articleUrl(id: string): string {
    return `${SITE_BASE_URL}/article/${id}`;
  },

  /** Absolute URL to the default fallback image, for onError handlers
   *  and OG defaults. Handles both relative ("/uploads/foo.jpg") and
   *  absolute ("https://cdn.example/foo.jpg") values from the env. */
  defaultImageUrl(): string {
    if (SITE_DEFAULT_IMAGE.startsWith('http://') || SITE_DEFAULT_IMAGE.startsWith('https://')) {
      return SITE_DEFAULT_IMAGE;
    }
    const path = SITE_DEFAULT_IMAGE.startsWith('/') ? SITE_DEFAULT_IMAGE : `/${SITE_DEFAULT_IMAGE}`;
    return `${SITE_BASE_URL}${path}`;
  },
} as const;
