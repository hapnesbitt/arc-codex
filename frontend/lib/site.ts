// site.ts — per-site identity primitives, read from build-time env.
//
// Frontend companion to backend/site_config.py. Reads NEXT_PUBLIC_SITE_*
// vars baked in at build time (see Dockerfile.frontend build-args block
// and docker-compose.yml build.args). NO hardcoded fallbacks: this is
// the white-label mechanism, and a Hunt build with a missing or
// misnamed var would otherwise silently ship Arc-branded (or vice
// versa). A failed build is loud and cheap; wrong branding on a
// customer instance is not — so any missing/empty required var throws
// here with a message naming which variable and where to set it. The
// throw fires at module load, which means it surfaces at Next.js
// build-time page collection (previously this manifested three files
// away as `new URL('')` → ERR_INVALID_URL in layout.tsx, hard to
// trace).
//
// Everything else in the frontend that would otherwise hardcode
// "Arc Codex" / "arc-codex.com" / a specific canonical URL should read
// from here. cardConfig.ts is a related but separate concern — it
// carries per-site FEATURE flags and per-site EXTERNAL service URLs
// (video subdomain, quiz deeplink template, dashboard link); this
// module is just brand identity.

function requireBrandEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(
      `[site.ts] Required brand env var ${name} is unset or empty. ` +
      `This is the white-label mechanism — no default is applied so a ` +
      `mislabeled build fails loudly instead of shipping the wrong brand. ` +
      `Set it via docker-compose.yml build.args (see the NEXT_PUBLIC_SITE_* ` +
      `block, sourced from the shell/.env at build time) or, for local ` +
      `npm run dev, in frontend/.env.local.`
    );
  }
  return v;
}

const SITE_NAME = requireBrandEnv('NEXT_PUBLIC_SITE_NAME');
const SITE_BASE_URL = requireBrandEnv('NEXT_PUBLIC_SITE_BASE_URL');
const SITE_DEFAULT_IMAGE = requireBrandEnv('NEXT_PUBLIC_SITE_DEFAULT_IMAGE');

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
