// Filename: /frontend/app/about/developer/page.tsx
// Arc Codex Developer Documentation — v6.2 (mobile overflow fix, linkedin_poster, updated services)
// Changes from v6.0:
//   - Collapse: button has aria-expanded, aria-controls, panel has role="region" + id
//   - Section: heading hierarchy h2 (was already h2, confirmed)
//   - Code/Block: code elements are already semantic
//   - Warn: role="note" for advisory content (not an error/alert)
//   - API method badges: aria-label on method span for screen readers
//   - Footer link: existing rel="noopener noreferrer" kept, focus-visible ring added
//   - All decorative icons: aria-hidden="true"
//   - Motion: respects prefers-reduced-motion
//   - Skip link added
//   - PageWrapper preserved

'use client';

import React, { useState, useId } from 'react';
import { motion } from 'framer-motion';
import {
  GitBranch, Terminal, Database, Cpu, Shield, Layers,
  Zap, CodeIcon, Server, Globe, Lock, AlertTriangle,
  ChevronDown, ChevronRight, BookOpen
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import { Badge } from '@/components/ui/badge';

// ── Reduced motion ────────────────────────────────────────────────────────────
const reducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false;

const fadeUp = reducedMotion
  ? {}
  : { initial: { opacity: 0, y: 20 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true }, transition: { duration: 0.5 } };

const heroAnim = reducedMotion
  ? {}
  : { initial: { opacity: 0, y: -20 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6 } };

// ── Section ───────────────────────────────────────────────────────────────────
interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  gradient: string;
  id?: string;
}

const Section: React.FC<SectionProps> = ({ title, icon, children, gradient, id }) => (
  <motion.section
    {...fadeUp}
    aria-labelledby={id ? `${id}-heading` : undefined}
    className={`p-8 rounded-2xl bg-slate-900/30 border ${gradient} backdrop-blur-2xl shadow-[0_0_20px_rgba(251,191,36,0.15)] transition-all duration-500 hover:scale-[1.005] hover:shadow-[0_0_35px_rgba(251,191,36,0.25)]`}
  >
    <div className="flex items-center gap-4 mb-6">
      <span aria-hidden="true">{icon}</span>
      <h2
        id={id ? `${id}-heading` : undefined}
        className="text-2xl font-bold text-slate-50 tracking-tight"
      >
        {title}
      </h2>
    </div>
    <div className="text-slate-300 leading-relaxed space-y-4">
      {children}
    </div>
  </motion.section>
);

// ── Collapse ──────────────────────────────────────────────────────────────────
interface CollapseProps {
  label: string;
  children: React.ReactNode;
}

const Collapse: React.FC<CollapseProps> = ({ label, children }) => {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonId = useId();

  return (
    <div className="border border-white/10 rounded-lg overflow-hidden">
      <button
        id={buttonId}
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/40 hover:bg-slate-800/70 transition-colors text-left outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 focus-visible:ring-inset"
      >
        <span className="text-slate-200 font-mono text-sm font-medium">{label}</span>
        {open
          ? <ChevronDown size={16} className="text-amber-400" aria-hidden="true" />
          : <ChevronRight size={16} className="text-slate-500" aria-hidden="true" />
        }
      </button>
      {open && (
        <div
          id={panelId}
          role="region"
          aria-labelledby={buttonId}
          className="px-4 py-4 bg-slate-900/50 border-t border-white/5"
        >
          {children}
        </div>
      )}
    </div>
  );
};

// ── Code / Block / Warn ───────────────────────────────────────────────────────
const Code: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <code className={`font-mono text-xs bg-slate-800/60 border border-white/10 rounded px-1.5 py-0.5 text-amber-300/90 ${className}`}>
    {children}
  </code>
);

const Block: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <pre className="bg-slate-900/70 border border-white/10 rounded-lg p-4 text-xs font-mono text-slate-300 overflow-x-auto leading-relaxed whitespace-pre-wrap">
    {children}
  </pre>
);

// role="note" — advisory/informational, not an error
const Warn: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div role="note" className="flex gap-3 bg-amber-900/15 border border-amber-500/30 rounded-lg p-4 text-amber-200 text-sm">
    <AlertTriangle size={16} className="text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
    <span>{children}</span>
  </div>
);

// ── Page ──────────────────────────────────────────────────────────────────────
const DeveloperPage: React.FC = () => {
  return (
    <PageWrapper>
      {/* Skip to content */}
      <a
        href="#dev-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[300] focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-black focus:font-bold focus:rounded-lg focus:text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
      >
        Skip to main content
      </a>

      <main id="dev-main" className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="space-y-12">

          {/* Hero */}
          <motion.header
            {...heroAnim}
            className="flex flex-col items-center text-center space-y-6 py-10"
          >
            <div
              className="p-4 rounded-2xl bg-gradient-to-br from-amber-500/30 via-orange-400/20 to-yellow-500/30 border border-amber-400/50 shadow-[0_0_40px_rgba(251,191,36,0.4)]"
              aria-hidden="true"
            >
              <Terminal className="h-12 w-12 text-amber-300" />
            </div>
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-slate-50">
              Developer Documentation
            </h1>
            <p className="text-xl text-amber-300/80 italic max-w-2xl mx-auto">
              Architecture, API contracts, data schemas, and the hard-won gotchas.
            </p>
            <div className="flex flex-wrap gap-3 justify-center" role="list" aria-label="Tech stack">
              {[
                { label: 'Flask + Next.js 16.1.6', className: 'bg-amber-600/20 text-amber-300 border-amber-500/30' },
                { label: 'Redis + Solr',       className: 'bg-blue-600/20 text-blue-300 border-blue-500/30' },
                { label: 'Ollama on M1',       className: 'bg-green-600/20 text-green-300 border-green-500/30' },
                { label: 'Auth.js v5 Beta',    className: 'bg-purple-600/20 text-purple-300 border-purple-500/30' },
              ].map(({ label, className }) => (
                <div key={label} role="listitem">
                  <Badge variant="outline" className={`${className} text-sm`}>{label}</Badge>
                </div>
              ))}
            </div>
            <div className="w-24 h-1 bg-gradient-to-r from-amber-400 to-orange-500 rounded-full animate-pulse" aria-hidden="true" />
          </motion.header>

          {/* Stack Overview */}
          <Section
            id="stack"
            title="Stack Overview"
            icon={<Layers className="w-8 h-8 text-amber-400" />}
            gradient="border-amber-400/40 hover:border-amber-300/60"
          >
            <dl className="grid md:grid-cols-2 gap-4">
              {[
                { label: 'Backend',     value: 'Python / Flask / gunicorn (port 5005)',      color: 'text-amber-300' },
                { label: 'Frontend',    value: 'Next.js 16.1.6 / React 19 / TypeScript',     color: 'text-blue-300' },
                { label: 'Database',    value: 'Redis (in-memory, port 6379)',                color: 'text-green-300' },
                { label: 'Search',      value: 'Apache Solr (full-text, port 8983)',          color: 'text-cyan-300' },
                { label: 'AI Inference',value: 'Ollama on MacBook Air M1 (192.168.1.185)',   color: 'text-purple-300' },
                { label: 'Auth',        value: 'Auth.js v5 beta — Google OAuth, JWT sessions',color: 'text-pink-300' },
                { label: 'Proxy',       value: "Caddy (automatic TLS via Let's Encrypt)",    color: 'text-orange-300' },
                { label: 'Process Mgr', value: 'arc.sh + systemd itc-stack.service',         color: 'text-slate-300' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-slate-800/30 border border-white/5 rounded-lg p-4">
                  <dt className="text-xs text-slate-500 uppercase tracking-widest mb-1">{label}</dt>
                  <dd className={`text-sm font-mono ${color} break-words`}>{value}</dd>
                </div>
              ))}
            </dl>
          </Section>

          {/* Services */}
          <Section
            id="services"
            title="Services & arc.sh"
            icon={<Server className="w-8 h-8 text-blue-400" />}
            gradient="border-blue-400/40 hover:border-blue-300/60"
          >
            <p>All services are managed by <Code>arc.sh</Code>. The stack auto-starts on boot via <Code>/etc/systemd/system/itc-stack.service</Code> (legacy name from itc era — paths are correct).</p>
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
./arc.sh restart linkedin_poster
./arc.sh restart frontend

# LinkedIn on/off (no restart needed):
redis-cli -a $REDIS_PASSWORD set linkedin:autopost 1
redis-cli -a $REDIS_PASSWORD set linkedin:autopost 0`}</Block>

            <dl className="grid md:grid-cols-2 gap-3 mt-2">
              {[
                { name: 'gunicorn',         note: 'Flask API — port 5005, must run before build' },
                { name: 'scribe',           note: 'v50.0 — RSS scraper + full A.R.C. pipeline' },
                { name: 'manual_publisher', note: 'v5.1 — URL/text/file submissions' },
                { name: 'stream_consumer',  note: 'Redis Streams consumer' },
                { name: 'analyzer',         note: 'On-demand analysis worker' },
                { name: 'mailer',           note: 'v1.0 ACTIVE — alerts + 7am digest' },
                { name: 'linkedin_poster',  note: 'v1.0 — auto-posts to LinkedIn, on/off via Redis' },
                { name: 'frontend',         note: 'Docker container arc-frontend — port 3000' },
                { name: 'watchdog',         note: '60s check loop, restarts crashed services' },
              ].map(({ name, note }) => (
                <div key={name} className="flex items-start gap-2 bg-slate-800/20 border border-white/5 rounded p-3 min-w-0">
                  <dt><Code>{name}</Code></dt>
                  <dd className="text-xs text-slate-400 min-w-0 break-words">{note}</dd>
                </div>
              ))}
            </dl>

            <Warn>
              <strong>Watchdog restart logic:</strong> Only restarts a service if its PID file exists.
              A missing PID file means intentionally stopped. A stale PID file means crashed.
            </Warn>
          </Section>

          {/* Caddy Routing */}
          <Section
            id="caddy"
            title="Reverse Proxy: Caddy Routing"
            icon={<Globe className="w-8 h-8 text-cyan-400" />}
            gradient="border-cyan-400/40 hover:border-cyan-300/60"
          >
            <Warn>
              <strong>/api/auth/* and /api/user/* MUST appear before the /api/* catch-all.</strong> These routes go to Next.js (3000), not Flask (5005). Getting the order wrong silently breaks all auth and user prefs.
            </Warn>
            <Block>{`arc-codex.com, www.arc-codex.com {
  handle /api/auth/* { reverse_proxy localhost:3000 }  # Auth.js
  handle /api/user/* { reverse_proxy localhost:3000 }  # Prefs proxy
  handle /api/*      { reverse_proxy localhost:5005 }  # Flask
  handle             { reverse_proxy localhost:3000 }  # Next.js
  tls rossnesbitt@gmail.com
}`}</Block>
          </Section>

          {/* API Endpoints */}
          <Section
            id="api"
            title="API Reference"
            icon={<CodeIcon className="w-8 h-8 text-green-400" />}
            gradient="border-green-400/40 hover:border-green-300/60"
          >
            <ul className="space-y-2" aria-label="API endpoints">
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
                <li key={path} className="flex flex-wrap items-start gap-2 bg-slate-800/20 border border-white/5 rounded p-3 min-w-0">
                  <span
                    aria-label={`HTTP ${method}`}
                    className={`text-xs font-bold font-mono px-2 py-0.5 rounded flex-shrink-0 ${
                      method === 'GET'    ? 'bg-green-900/40 text-green-300' :
                      method === 'POST'   ? 'bg-blue-900/40 text-blue-300' :
                      method === 'PATCH'  ? 'bg-amber-900/40 text-amber-300' :
                      'bg-red-900/40 text-red-300'
                    }`}
                  >
                    {method}
                  </span>
                  <Code className="break-all">{path}</Code>
                  <span className="text-xs text-slate-400 min-w-0">{desc}</span>
                </li>
              ))}
            </ul>
            <p className="text-sm mt-4">All blueprints registered in <Code>backend/main.py</Code> inside the Redis try block. Flask restart required after adding a new blueprint.</p>
          </Section>

          {/* Redis Schemas */}
          <Section
            id="redis"
            title="Redis Data Schemas"
            icon={<Database className="w-8 h-8 text-purple-400" />}
            gradient="border-purple-400/40 hover:border-purple-300/60"
          >
            <div className="space-y-3">
              <Collapse label="article:{id}  (hash)">
                <Block>{`id, title, url, source, original_text, timestamp, directive,
chimera_score, red_team_analysis, blue_team_analysis,
purple_team_analysis, sentinel_verdict, og_image, slug`}</Block>
              </Collapse>
              <Collapse label="comments:{article_id}  (list of JSON strings)">
                <Block>{`{ id, article_id, author, content, timestamp, is_ai }`}</Block>
                <p className="text-xs text-slate-400 mt-2">Counter-Analyst author must be exactly <Code>A.R.C. Counter-Analyst</Code> — frontend cyan styling depends on exact string match.</p>
              </Collapse>
              <Collapse label="reactions:{comment_id}  (hash)">
                <Block>{`like, dislike, heart, happy, sad, angry  (integer counts)`}</Block>
              </Collapse>
              <Collapse label="translation:{article_id}:{lang}  (string, 24h TTL)">
                <Block>{`{
  title, original_text, red_team_analysis,
  blue_team_analysis, purple_team_analysis,
  rtl: bool
}`}</Block>
              </Collapse>
              <Collapse label="user:{google_sub}  (hash)">
                <Block>{`email, name, picture, preferred_lang, created_at, last_seen

Note: google_sub is a long numeric string (e.g. 106447029965347101642)
LightBox uses user:{username} — no collision risk`}</Block>
              </Collapse>
              <Collapse label="analysis:pending  (Redis Stream)">
                <Block>{`Consumer group: analysis_workers
Used by: stream_consumer.py
Delivery: real-time, zero polling, no filesystem writes`}</Block>
              </Collapse>
            </div>
          </Section>

          {/* Auth Architecture */}
          <Section
            id="auth"
            title="Authentication Architecture"
            icon={<Lock className="w-8 h-8 text-pink-400" />}
            gradient="border-pink-400/40 hover:border-pink-300/60"
          >
            <p>Soft auth model — the site is fully public. Google login is optional and unlocks preferences only. No username/password fallback.</p>
            <Block>{`Browser
  → Next.js /api/auth/[...nextauth]  (Auth.js catch-all)
  → Google OAuth callback
  → JWT session cookie set (30 days)

Browser requests /api/user/prefs
  → Next.js app/api/user/prefs/route.ts  (server-side proxy)
  → Adds X-User-Id: {google_sub} header
  → Flask /api/user/prefs (loopback only — rejects if not 127.0.0.1)`}</Block>
            <div className="space-y-3 mt-2">
              <Warn><strong>trustHost: true is required in auth.ts.</strong> Without it, all auth routes return UntrustedHost error when behind a reverse proxy.</Warn>
              <Warn><strong>Use account.providerAccountId for the Google sub</strong>, not user.id. The JWT strategy populates these differently.</Warn>
            </div>
            <p className="text-sm mt-4">
              <Code>@auth/redis-adapter</Code> does not exist as a standalone package. The <Code>adapters.js</Code> in this beta is empty. JWT sessions are the correct approach — no adapter needed.
            </p>
          </Section>

          {/* AI Pipeline */}
          <Section
            id="ai"
            title="AI Pipeline"
            icon={<Cpu className="w-8 h-8 text-amber-400" />}
            gradient="border-amber-400/40 hover:border-amber-300/60"
          >
            <p>All AI inference routes through <Code>ollama_utils.py</Code>. Never duplicate <Code>call_ollama_with_fallback()</Code> in other files.</p>
            <Warn>
              <strong>call_ollama_with_fallback() returns a TUPLE.</strong> Always use <Code>result[0]</Code> for text. Never unpack as <Code>text, duration = result</Code> — it returns more than 2 values and raises ValueError.
            </Warn>
            <Block>{`# Correct:
result = call_ollama_with_fallback(prompt, model)
text = result[0]

# Wrong — raises ValueError:
text, duration = call_ollama_with_fallback(prompt, model)`}</Block>
            <p className="text-sm mt-4">Models: <Code>devstral</Code> (cloud, primary) → <Code>gemma3:4b</Code> (local M1, fallback). gemma3:4b handles simple tasks but struggles with large JSON translation payloads. Translation failures on 429 are graceful — "model unavailable" shown to user.</p>
            <Warn>
              <strong>DO NOT auto-translate on component mount in feed view.</strong> 33 article cards firing simultaneous Ollama requests blocks all gunicorn threads and takes down the site. <Code>preferred_lang</Code> is a click shortcut — it skips the language dropdown, it does not auto-fire.
            </Warn>
          </Section>

          {/* Frontend Gotchas */}
          <Section
            id="gotchas"
            title="Frontend Gotchas"
            icon={<AlertTriangle className="w-8 h-8 text-orange-400" />}
            gradient="border-orange-400/40 hover:border-orange-300/60"
          >
            <ul className="space-y-3" aria-label="Frontend gotchas">
              {[
                { title: 'FeedClient.tsx',       warn: true,  text: 'NEVER restructure. Surgical deletions only. Keep React.Fragment structure.' },
                { title: 'LayoutTheme.module.css',warn: true, text: 'ALWAYS check here first for color issues. It overrides everything else.' },
                { title: 'UserPrefsContext',      warn: false, text: 'Single source of truth for prefs. Import from @/components/UserPrefsContext — NOT @/hooks/useUserPrefs.' },
                { title: 'postcss.config.js',    warn: true,  text: 'CommonJS (.js) only. The .mjs version references @tailwindcss/postcss which is not installed — build will fail.' },
                { title: 'npm install',          warn: false, text: 'Always use --legacy-peer-deps (set permanently in .npmrc — automatic).' },
                { title: 'Next.js version',      warn: false, text: '16.1.6 — not 14. App Router. Turbopack enabled.' },
                { title: 'spaCy install',        warn: false, text: 'Use pip wheel URL. NOT python3 -m spacy download (typer conflict).' },
                { title: 'Ads',                  warn: true,  text: 'Fully removed. Do not re-add AdSense, GAM, or any ad network components.' },
                { title: 'CopyAllButton',        warn: false, text: "Client component — import separately, never inline 'use client' in server components." },
              ].map(({ title, warn, text }) => (
                <li key={title} className={`flex items-start gap-3 p-3 rounded-lg border text-sm ${warn ? 'bg-amber-900/10 border-amber-500/20' : 'bg-slate-800/20 border-white/5'}`}>
                  {warn && <AlertTriangle size={14} className="text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />}
                  <div>
                    <Code>{title}</Code>
                    <span className="text-slate-300 ml-2">{text}</span>
                  </div>
                </li>
              ))}
            </ul>
          </Section>

          {/* Solr */}
          <Section
            id="solr"
            title="Search: Solr"
            icon={<GitBranch className="w-8 h-8 text-cyan-400" />}
            gradient="border-cyan-400/40 hover:border-cyan-300/60"
          >
            <p>Full-text search via <Code>pysolr</Code>. Endpoint: <Code>http://localhost:8983/solr/articles</Code>.</p>
            <p><strong>Schema fields:</strong> id, title, content, source, url, timestamp, directive, chimera_score.</p>
            <p><strong>Lazy reconnect:</strong> Both <Code>main.py</Code> and <Code>scribe.py</Code> use a <Code>global solr</Code> lazy reconnect pattern. This fixes the boot-order race condition where Solr starts after application services.</p>
            <p>Admin tool: <Code>kasmir7.py</Code> functions 5–8 handle re-index, diagnostics, and orphan purging. 31,924 Solr orphans were purged during the v5.0 migration.</p>
          </Section>

          {/* Planned Features */}
          <Section
            id="roadmap"
            title="Planned Features"
            icon={<Zap className="w-8 h-8 text-green-400" />}
            gradient="border-green-400/40 hover:border-green-300/60"
          >
            <div className="space-y-4">
              {[
                {
                  tag: 'NEXT SESSION',
                  tagClass: 'bg-green-500/20 text-green-400',
                  titleClass: 'text-green-300',
                  wrapClass: 'bg-green-900/10 border-green-500/20',
                  title: 'arc.sh restore',
                  desc: 'List available backup tarballs, interactive selection, confirmation prompt, extract to stack root, auto-restart affected services. Fits existing arc.sh bash pattern.',
                },
                {
                  tag: 'NEXT SESSION',
                  tagClass: 'bg-green-500/20 text-green-400',
                  titleClass: 'text-green-300',
                  wrapClass: 'bg-green-900/10 border-green-500/20',
                  title: 'arc_admin.py — Curses TUI',
                  desc: <span>Python stdlib curses. Password-protected terminal menu. Sections: System, Backups, Articles, Users, Ollama. Auth via Redis <Code>is_admin</Code> flag. Launch via <Code>./arc.sh admin</Code>.</span>,
                },
              ].map(({ tag, tagClass, titleClass, wrapClass, title, desc }) => (
                <div key={title} className={`${wrapClass} border rounded-lg p-5`}>
                  <h3 className={`font-bold ${titleClass} mb-2 flex items-center gap-2`}>
                    <span className={`text-xs ${tagClass} px-2 py-0.5 rounded`}>{tag}</span>
                    {title}
                  </h3>
                  <p className="text-sm text-slate-300">{desc}</p>
                </div>
              ))}

              <div className="bg-slate-800/30 border border-white/10 rounded-lg p-5">
                <h3 className="font-bold text-slate-200 mb-3">Future Roadmap</h3>
                <ul className="space-y-2 text-sm text-slate-400">
                  {[
                    'Auto-translate on article detail page /article/[slug] only (safe — one article)',
                    'Email digest notifications (mailer.py stub ready)',
                    'Topic/category preferences per user',
                    'GitHub SSO (second OAuth provider)',
                    'Article deduplication (SimHash/MinHash)',
                    'Ollama model auto-switching on credit exhaustion',
                    'Netdata integration for custom pipeline metrics',
                    'TLS for IMAP (port 993) via Let\'s Encrypt',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-2">
                      <span aria-hidden="true">→</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Section>

          {/* Footer */}
          <footer className="text-center text-sm text-slate-500 pt-8 pb-4 border-t border-slate-700/50 space-y-2">
            <p>
              © {new Date().getFullYear()} Arc Codex. Project context v6.2.{' '}
              <a
                href="https://github.com/hapnesbitt/arc-codex"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-300/80 hover:text-amber-200 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 rounded"
              >
                github.com/hapnesbitt/arc-codex
              </a>
            </p>
            <p>
              <a
                href="/about/developer/config"
                className="text-cyan-400/60 hover:text-cyan-300 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 rounded text-xs font-mono"
              >
                current values →
              </a>
            </p>
          </footer>

        </div>
      </main>
    </PageWrapper>
  );
};

export default DeveloperPage;
