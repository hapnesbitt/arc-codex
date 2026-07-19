// Filename: /frontend/app/about/developer/page.tsx
// Infrastructure of Meaning — Developer Documentation.
// Librarian aesthetic. Reconstructed from page.tsx.Apr20 (full architecture
// content: stack, arc.sh services, Caddy routing, API reference, Redis schemas,
// auth, AI pipeline, frontend gotchas, Solr, roadmap). Server component.

import React from 'react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Developer Documentation — Arc Codex',
  description: 'Architecture, API contracts, data schemas, and the hard-won gotchas behind Arc Codex.',
};

// ── helpers ───────────────────────────────────────────────────────────────────
const SectionShell: React.FC<{ id?: string; eyebrow: string; heading: string; children: React.ReactNode }> = ({
  id, eyebrow, heading, children,
}) => (
  <section id={id} className="py-10 border-b border-slate-800/60 space-y-6">
    <div className="space-y-2">
      <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">{eyebrow}</div>
      <h2 className="font-sans text-xs uppercase tracking-[0.25em] font-semibold text-slate-300">{heading}</h2>
    </div>
    {children}
  </section>
);

const Code: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <code className="font-mono text-sm text-slate-300 bg-slate-900 border border-slate-800 rounded-sm px-1.5 py-0.5">
    {children}
  </code>
);

const Block: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <pre className="bg-slate-900 border border-slate-800 rounded-sm p-4 text-sm font-mono text-slate-300 overflow-x-auto leading-relaxed whitespace-pre-wrap">
    {children}
  </pre>
);

const Warn: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p role="note" className="font-serif text-sm text-slate-300 italic leading-relaxed flex items-start gap-2 not-prose">
    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" aria-hidden="true" />
    <span>{children}</span>
  </p>
);

const Panel: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <details className="group/p border-b border-slate-800/40">
    <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer flex items-center justify-between gap-4 py-3 px-2 -mx-2 rounded-sm hover:bg-slate-800/30 transition-colors ring-focus">
      <span className="font-mono text-sm text-slate-300">{label}</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 group-open/p:hidden">expand</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-500 hidden group-open/p:inline">collapse</span>
    </summary>
    <div className="pt-2 pb-4 px-2 space-y-3 text-slate-300 font-serif text-base leading-relaxed">
      {children}
    </div>
  </details>
);

// ── page ──────────────────────────────────────────────────────────────────────
export default function DeveloperPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">

        {/* Header */}
        <header className="text-center py-12 border-b border-slate-800/60 space-y-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            Infrastructure of Meaning
          </div>
          <h1 className="font-serif text-5xl sm:text-6xl font-semibold tracking-tight text-slate-50 leading-none">
            Developer Documentation
          </h1>
          <p className="font-serif text-lg text-slate-400 italic leading-relaxed max-w-2xl mx-auto">
            Architecture, API contracts, data schemas, and the hard-won gotchas.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-2 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
            <span>Flask + Next.js 16.1.6</span>
            <span aria-hidden="true">·</span>
            <span>Redis + Solr</span>
            <span aria-hidden="true">·</span>
            <span>Ollama on M1</span>
            <span aria-hidden="true">·</span>
            <span>Auth.js v5 Beta</span>
          </div>
        </header>

        {/* Stack Overview */}
        <SectionShell id="stack" eyebrow="I" heading="Stack Overview">
          <dl className="grid sm:grid-cols-2 gap-x-6">
            {[
              { label: 'Backend', value: 'Python / Flask / gunicorn (port 5005)' },
              { label: 'Frontend', value: 'Next.js 16.1.6 / React 19 / TypeScript' },
              { label: 'Database', value: 'Redis (in-memory, port 6379)' },
              { label: 'Library DB', value: 'SQLite (public-domain book corpus)' },
              { label: 'Search', value: 'Apache Solr (full-text, port 8983)' },
              { label: 'AI Inference', value: 'Ollama on MacBook Air M1 (192.168.1.185)' },
              { label: 'Auth', value: 'Auth.js v5 beta — Google OAuth, JWT sessions' },
              { label: 'Proxy', value: "Caddy (automatic TLS via Let's Encrypt)" },
              { label: 'Process Mgr', value: 'arc.sh + systemd itc-stack.service' },
            ].map(({ label, value }) => (
              <div key={label} className="py-3 border-b border-slate-800/40">
                <dt className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{label}</dt>
                <dd className="font-mono text-sm text-slate-200 break-words">{value}</dd>
              </div>
            ))}
          </dl>
        </SectionShell>

        {/* Services & arc.sh */}
        <SectionShell id="services" eyebrow="II" heading="Services & arc.sh">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            All services are managed by <Code>arc.sh</Code>. The stack auto-starts on boot via{' '}
            <Code>/etc/systemd/system/itc-stack.service</Code> (legacy name from the itc era — paths are correct).
          </p>
          <Block>{`./arc.sh start|stop|restart [service]
./arc.sh status          # service states + log/backup sizes
./arc.sh build           # Docker build + restart frontend
./arc.sh backup          # fast SSD backup, code only (stack stops briefly)
./arc.sh backup-cold     # full archive to /mnt/data (stack stays up)
./arc.sh checkup         # health check + error scan + CPU/RAM
./arc.sh logs [service]  # tail logs for a service
./arc.sh prune [dry]     # rotate old backups

# Named service control:
./arc.sh restart gunicorn
./arc.sh restart scribe
./arc.sh restart bluesky_poster
./arc.sh restart frontend

# Poster on/off (no restart needed):
redis-cli -a $REDIS_PASSWORD set bluesky:autopost 1
redis-cli -a $REDIS_PASSWORD set bluesky:autopost 0`}</Block>
          <dl className="border-t border-slate-800/40">
            {[
              { name: 'gunicorn', note: 'Flask API — port 5005, must run before build' },
              { name: 'scribe', note: 'v50.0 — RSS scraper + full A.R.C. pipeline' },
              { name: 'manual_publisher', note: 'v5.1 — URL/text/file submissions' },
              { name: 'stream_consumer', note: 'Redis Streams consumer' },
              { name: 'analyzer', note: 'On-demand analysis worker' },
              { name: 'mailer', note: 'v1.0 ACTIVE — alerts + 7am digest' },
              { name: 'bluesky_poster', note: 'v1.3 — auto-posts to Bluesky, on/off via Redis' },
              { name: 'mastodon_poster', note: 'v1.1 — auto-posts to Mastodon, on/off via Redis' },
              { name: 'facebook_poster', note: 'v1.0 — auto-posts to Facebook, on/off via Redis' },
              { name: 'frontend', note: 'Docker container arc-frontend — port 3000' },
              { name: 'watchdog', note: '60s check loop, restarts crashed services' },
            ].map(({ name, note }) => (
              <div key={name} className="py-3 border-b border-slate-800/40 flex items-baseline gap-4 flex-wrap">
                <dt className="min-w-[180px]"><Code>{name}</Code></dt>
                <dd className="font-serif text-sm text-slate-300 leading-relaxed">{note}</dd>
              </div>
            ))}
          </dl>
          <Warn>
            <span><strong className="not-italic">Watchdog restart logic:</strong> only restarts a service if its PID file exists. A missing PID file means intentionally stopped. A stale PID file means crashed.</span>
          </Warn>
        </SectionShell>

        {/* Caddy Routing */}
        <SectionShell id="caddy" eyebrow="III" heading="Reverse Proxy · Caddy Routing">
          <Warn>
            <span><strong className="not-italic">/api/auth/* and /api/user/* must appear before the /api/* catch-all.</strong> These routes go to Next.js (3000), not Flask (5005). Getting the order wrong silently breaks all auth and user prefs.</span>
          </Warn>
          <Block>{`arc-codex.com, www.arc-codex.com {
  handle /api/auth/* { reverse_proxy localhost:3000 }  # Auth.js
  handle /api/user/* { reverse_proxy localhost:3000 }  # Prefs proxy
  handle /api/*      { reverse_proxy localhost:5005 }  # Flask
  handle             { reverse_proxy localhost:3000 }  # Next.js
  tls rossnesbitt@gmail.com
}`}</Block>
        </SectionShell>

        {/* API Reference */}
        <SectionShell id="api" eyebrow="IV" heading="API Reference">
          <ul className="border-t border-slate-800/40">
            {[
              { method: 'GET',    path: '/api/articles',          desc: 'Paginated feed — ?limit=N&offset=N' },
              { method: 'GET',    path: '/api/articles/<id>',     desc: 'Single article with full analysis' },
              { method: 'POST',   path: '/api/submit',            desc: 'Submit URL/text/file for processing' },
              { method: 'GET',    path: '/api/search',            desc: 'Solr full-text — ?q=query&limit=N' },
              { method: 'GET',    path: '/api/translate/<id>',    desc: 'Translate article + analysis — ?lang=<language>' },
              { method: 'DELETE', path: '/api/translate/<id>/cache', desc: 'Admin cache bust' },
              { method: 'GET',    path: '/api/user/prefs',        desc: 'Fetch prefs (via Next.js proxy)' },
              { method: 'POST',   path: '/api/user/prefs',        desc: 'Upsert on login (loopback only)' },
              { method: 'PATCH',  path: '/api/user/prefs',        desc: 'Update preferred_lang (via proxy)' },
              { method: 'DELETE', path: '/api/user/prefs',        desc: 'GDPR self-service deletion' },
              { method: 'GET',    path: '/api/rss',               desc: 'RSS 2.0 — full analysis per item' },
            ].map(({ method, path, desc }) => (
              <li key={path} className="py-3 border-b border-slate-800/40 flex items-start gap-3 flex-wrap">
                <span
                  aria-label={`HTTP ${method}`}
                  className="font-sans text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-400 min-w-[60px]"
                >
                  {method}
                </span>
                <Code>{path}</Code>
                <span className="font-serif text-sm text-slate-300 leading-relaxed flex-1 min-w-[240px]">{desc}</span>
              </li>
            ))}
          </ul>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            All blueprints registered in <Code>backend/main.py</Code> inside the Redis try block. Flask restart required after adding a new blueprint.
          </p>
        </SectionShell>

        {/* Redis Schemas */}
        <SectionShell id="redis" eyebrow="V" heading="Redis Data Schemas">
          <div className="border-t border-slate-800/40">
            <Panel label="article:{id}  (hash)">
              <Block>{`id, title, url, source, original_text, timestamp, directive,
chimera_score, red_team_analysis, blue_team_analysis,
purple_team_analysis, sentinel_verdict, og_image, slug`}</Block>
            </Panel>
            <Panel label="comments:{article_id}  (list of JSON strings)">
              <Block>{`{ id, article_id, author, content, timestamp, is_ai }`}</Block>
              <p>
                Counter-Analyst author must be exactly <Code>A.R.C. Counter-Analyst</Code> — frontend cyan styling depends on exact string match.
              </p>
            </Panel>
            <Panel label="reactions:{comment_id}  (hash)">
              <Block>{`like, dislike, heart, happy, sad, angry  (integer counts)`}</Block>
            </Panel>
            <Panel label="translation:{article_id}:{lang}  (string, 24h TTL)">
              <Block>{`{
  title, original_text, red_team_analysis,
  blue_team_analysis, purple_team_analysis,
  rtl: bool
}`}</Block>
            </Panel>
            <Panel label="user:{google_sub}  (hash)">
              <Block>{`email, name, picture, preferred_lang, created_at, last_seen

Note: google_sub is a long numeric string (e.g. 106447029965347101642)
LightBox uses user:{username} — no collision risk`}</Block>
            </Panel>
            <Panel label="analysis:pending  (Redis Stream)">
              <Block>{`Consumer group: analysis_workers
Used by: stream_consumer.py
Delivery: real-time, zero polling, no filesystem writes`}</Block>
            </Panel>
          </div>
        </SectionShell>

        {/* Auth Architecture */}
        <SectionShell id="auth" eyebrow="VI" heading="Authentication Architecture">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Soft auth model — the site is fully public. Google login is optional and unlocks preferences only. No username/password fallback.
          </p>
          <Block>{`Browser
  → Next.js /api/auth/[...nextauth]  (Auth.js catch-all)
  → Google OAuth callback
  → JWT session cookie set (30 days)

Browser requests /api/user/prefs
  → Next.js app/api/user/prefs/route.ts  (server-side proxy)
  → Adds X-User-Id: {google_sub} header
  → Flask /api/user/prefs (loopback only — rejects if not 127.0.0.1)`}</Block>
          <Warn>
            <span><strong className="not-italic">trustHost: true is required in auth.ts.</strong> Without it, all auth routes return UntrustedHost error when behind a reverse proxy.</span>
          </Warn>
          <Warn>
            <span><strong className="not-italic">Use account.providerAccountId for the Google sub</strong>, not user.id. The JWT strategy populates these differently.</span>
          </Warn>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <Code>@auth/redis-adapter</Code> does not exist as a standalone package. The <Code>adapters.js</Code> in this beta is empty. JWT sessions are the correct approach — no adapter needed.
          </p>
        </SectionShell>

        {/* AI Pipeline */}
        <SectionShell id="ai" eyebrow="VII" heading="AI Pipeline">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            All AI inference routes through <Code>ollama_utils.py</Code>. Never duplicate <Code>call_ollama_with_fallback()</Code> in other files.
          </p>
          <Warn>
            <span><strong className="not-italic">call_ollama_with_fallback() returns a TUPLE.</strong> Always use <Code>result[0]</Code> for text. Never unpack as <Code>text, duration = result</Code> — it returns more than 2 values and raises ValueError.</span>
          </Warn>
          <Block>{`# Correct:
result = call_ollama_with_fallback(prompt, model)
text = result[0]

# Wrong — raises ValueError:
text, duration = call_ollama_with_fallback(prompt, model)`}</Block>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Inference is tiered and demand-gated: a compact local model handles the bulk of the work, and a larger cloud model is reached only on escalation, within a weekly budget. The Red / Blue / Purple analyses are computed lazily — on an article&rsquo;s first view rather than at ingest — so inference cost tracks readership, not ingest volume. Published articles are retained for roughly a month before they are pruned. Translation degrades gracefully when a model is unavailable: &ldquo;model unavailable&rdquo; is shown rather than a hard failure.
          </p>
          <Warn>
            <span><strong className="not-italic">Do not auto-translate on component mount in feed view.</strong> The feed lazy-loads on a tribonacci ramp, but a scrolled session holds dozens of mounted cards — that many simultaneous Ollama requests blocks all gunicorn threads and takes down the site. <Code>preferred_lang</Code> is a click shortcut — it skips the language dropdown, it does not auto-fire.</span>
          </Warn>
        </SectionShell>

        {/* Frontend Gotchas */}
        <SectionShell id="gotchas" eyebrow="VIII" heading="Frontend Gotchas">
          <ul className="border-t border-slate-800/40">
            {[
              { title: 'FeedClient.tsx',        warn: true,  text: 'NEVER restructure. Surgical deletions only. Keep React.Fragment structure.' },
              { title: 'LayoutTheme.module.css', warn: true,  text: 'ALWAYS check here first for color issues. It overrides everything else.' },
              { title: 'UserPrefsContext',       warn: false, text: 'Single source of truth for prefs. Import from @/components/UserPrefsContext — NOT @/hooks/useUserPrefs.' },
              { title: 'postcss.config.js',     warn: true,  text: 'CommonJS (.js) only. The .mjs version references @tailwindcss/postcss which is not installed — build will fail.' },
              { title: 'npm install',           warn: false, text: 'Always use --legacy-peer-deps (set permanently in .npmrc — automatic).' },
              { title: 'Next.js version',       warn: false, text: '16.1.6 — not 14. App Router. Turbopack enabled.' },
              { title: 'spaCy install',         warn: false, text: 'Use pip wheel URL. NOT python3 -m spacy download (typer conflict).' },
              { title: 'Ads',                   warn: true,  text: 'Fully removed. Do not re-add AdSense, GAM, or any ad network components.' },
              { title: 'CopyAllButton',         warn: false, text: "Client component — import separately, never inline 'use client' in server components." },
            ].map(({ title, warn, text }) => (
              <li key={title} className="py-3 border-b border-slate-800/40 flex items-start gap-3">
                {warn && (
                  <span className="mt-2 h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" aria-hidden="true" />
                )}
                {!warn && <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-700 shrink-0" aria-hidden="true" />}
                <div className="flex-1 min-w-0 space-y-1">
                  <Code>{title}</Code>
                  <p className="font-serif text-sm text-slate-300 leading-relaxed">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </SectionShell>

        {/* Solr */}
        <SectionShell id="solr" eyebrow="IX" heading="Search · Solr">
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Full-text search via <Code>pysolr</Code>. Endpoint: <Code>http://localhost:8983/solr/articles</Code>.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <strong>Schema fields:</strong> id, title, content, source, url, timestamp, directive, chimera_score (Chimera Difficulty Score, 0–100).
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            <strong>Lazy reconnect:</strong> both <Code>main.py</Code> and <Code>scribe.py</Code> use a <Code>global solr</Code> lazy reconnect pattern. This fixes the boot-order race condition where Solr starts after application services.
          </p>
          <p className="font-serif text-base text-slate-200 leading-relaxed">
            Admin tool: <Code>kasmir7.py</Code> functions 5–8 handle re-index, diagnostics, and orphan purging. 31,924 Solr orphans were purged during the v5.0 migration.
          </p>
        </SectionShell>

        {/* Planned Features */}
        <SectionShell id="roadmap" eyebrow="X" heading="Planned Features">
          <div className="space-y-6">
            {[
              {
                tag: 'Next session',
                title: 'arc.sh restore',
                desc: 'List available backup tarballs, interactive selection, confirmation prompt, extract to stack root, auto-restart affected services. Fits the existing arc.sh bash pattern.',
              },
              {
                tag: 'Next session',
                title: 'arc_admin.py — Curses TUI',
                desc: <>Python stdlib curses. Password-protected terminal menu. Sections: System, Backups, Articles, Users, Ollama. Auth via Redis <Code>is_admin</Code> flag. Launch via <Code>./arc.sh admin</Code>.</>,
              },
            ].map(({ tag, title, desc }) => (
              <div key={title} className="py-4 border-b border-slate-800/40 space-y-2">
                <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">{tag}</div>
                <h3 className="font-serif text-xl text-slate-100 leading-snug">{title}</h3>
                <p className="font-serif text-base text-slate-300 leading-relaxed">{desc}</p>
              </div>
            ))}

            <div className="py-4 space-y-3">
              <div className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">Future roadmap</div>
              <ul className="font-serif text-base text-slate-300 leading-relaxed space-y-2 list-disc ml-6">
                <li>Auto-translate on article detail page /article/[slug] only (safe — one article).</li>
                <li>Topic/category preferences per user.</li>
                <li>Article deduplication (SimHash/MinHash).</li>
                <li>Ollama model auto-switching on credit exhaustion.</li>
                <li>Netdata integration for custom pipeline metrics.</li>
                <li>TLS for IMAP (port 993) via Let&apos;s Encrypt.</li>
              </ul>
            </div>
          </div>
        </SectionShell>

        {/* Project context + repo */}
        <section className="py-10 border-b border-slate-800/60 text-center space-y-3 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
          <p>© {new Date().getFullYear()} Arc Codex · Project context v6.2</p>
          <p>
            <a
              href="https://github.com/hapnesbitt/arc-codex"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-300 underline decoration-slate-600 hover:decoration-slate-300 underline-offset-2 ring-focus rounded-sm"
            >
              github.com/hapnesbitt/arc-codex
            </a>
          </p>
        </section>

        {/* Footer — identifier block */}
        <footer className="text-center pt-12 pb-6 space-y-1 font-sans text-[10px] uppercase tracking-[0.25em] text-slate-600">
          <p>Harold Edwin Ross Nesbitt III</p>
          <p>Fort Collins, CO · 40.5853° N, 105.0844° W</p>
          <p>A.R.C. Framework v7.14 · Connection Secure</p>
        </footer>
      </main>
    </div>
  );
}
