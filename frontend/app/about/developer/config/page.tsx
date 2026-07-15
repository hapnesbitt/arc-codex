// Filename: /frontend/app/about/developer/config/page.tsx
// Arc Codex — Live Configuration View v1.0
// Read-only dashboard showing arc_config.yaml values + live Redis runtime state.
// No auth required — no secrets exposed (credentials live in backend/.env only).

'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Settings, Server, Cpu, Database, RefreshCw,
  CheckCircle, XCircle, AlertTriangle, Clock, Zap
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import Link from 'next/link';

// ── Types ─────────────────────────────────────────────────────────────────────
interface ConfigData {
  stack:       Record<string, string | number | boolean>;
  ollama:      Record<string, string>;
  scribe:      Record<string, number | string>;
  bluesky:     Record<string, number | boolean>;
  mailer:      Record<string, string | number>;
  translation: Record<string, string | number>;
  feed:        Record<string, number>;
  services:    Record<string, boolean>;
  runtime:     {
    bluesky_autopost:  boolean;
    article_count:     number;
    last_publish:      string | null;
  };
  loaded_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://arc-codex.com';

const reducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false;

const fadeUp = reducedMotion
  ? {}
  : { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true }, transition: { duration: 0.4 } };

// ── Sub-components ────────────────────────────────────────────────────────────
const Card: React.FC<{ title: string; icon: React.ReactNode; color: string; children: React.ReactNode }> =
  ({ title, icon, color, children }) => (
  <motion.div
    {...fadeUp}
    className={`p-6 rounded-2xl bg-slate-900/30 border ${color} backdrop-blur-xl shadow-[0_0_16px_rgba(251,191,36,0.08)]`}
  >
    <div className="flex items-center gap-3 mb-4">
      <span aria-hidden="true">{icon}</span>
      <h2 className="text-lg font-bold text-slate-50 tracking-tight">{title}</h2>
    </div>
    {children}
  </motion.div>
);

const KV: React.FC<{ label: string; value: React.ReactNode; mono?: boolean }> =
  ({ label, value, mono = true }) => (
  <div className="flex items-start justify-between gap-4 py-2 border-b border-white/5 last:border-0">
    <dt className="text-xs text-slate-500 uppercase tracking-widest flex-shrink-0 pt-0.5">{label}</dt>
    <dd className={`text-sm text-right ${mono ? 'font-mono text-amber-300/90' : 'text-slate-300'}`}>
      {value}
    </dd>
  </div>
);

const Toggle: React.FC<{ label: string; value: boolean; source?: string }> =
  ({ label, value, source }) => (
  <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
    <div>
      <dt className="text-xs text-slate-500 uppercase tracking-widest">{label}</dt>
      {source && <div className="text-xs text-slate-600 mt-0.5">{source}</div>}
    </div>
    <dd>
      {value
        ? <span className="flex items-center gap-1.5 text-green-400 text-xs font-mono"><CheckCircle size={13} aria-hidden="true" /> ON</span>
        : <span className="flex items-center gap-1.5 text-slate-500 text-xs font-mono"><XCircle size={13} aria-hidden="true" /> OFF</span>
      }
    </dd>
  </div>
);

// ── Page ──────────────────────────────────────────────────────────────────────
const ConfigPage: React.FC = () => {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [error,  setError]  = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/config`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setConfig(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load config');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <PageWrapper>
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">

        {/* Header */}
        <motion.header
          {...(reducedMotion ? {} : { initial: { opacity: 0, y: -16 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5 } })}
          className="flex flex-col items-center text-center space-y-4 py-10"
        >
          <div className="p-4 rounded-2xl bg-gradient-to-br from-cyan-500/20 via-blue-400/10 to-slate-500/20 border border-cyan-400/40 shadow-[0_0_30px_rgba(34,211,238,0.2)]" aria-hidden="true">
            <Settings className="h-10 w-10 text-cyan-300" />
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-50">Live Configuration</h1>
          <p className="text-lg text-cyan-300/70 italic max-w-xl">
            Runtime values from <code className="font-mono text-xs bg-slate-800/60 px-1.5 py-0.5 rounded text-amber-300/80">arc_config.yaml</code> and Redis.
            No secrets — credentials live in <code className="font-mono text-xs bg-slate-800/60 px-1.5 py-0.5 rounded text-amber-300/80">backend/.env</code> only.
          </p>
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <Link href="/about/developer" className="text-cyan-400/70 hover:text-cyan-300 transition-colors">
              ← Developer Docs
            </Link>
            <span>·</span>
            {config && <span>Loaded {new Date(config.loaded_at).toLocaleTimeString()}</span>}
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-1.5 text-amber-400/70 hover:text-amber-300 transition-colors disabled:opacity-40"
              aria-label="Refresh config"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
              Refresh
            </button>
          </div>
        </motion.header>

        {/* Error */}
        {error && (
          <div role="alert" className="flex gap-3 bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-red-200 text-sm mb-8">
            <AlertTriangle size={16} className="flex-shrink-0 mt-0.5 text-red-400" aria-hidden="true" />
            <span>Could not load config: {error}. Is gunicorn running?</span>
          </div>
        )}

        {loading && !config && (
          <div className="text-center text-slate-500 py-20 text-sm">Loading…</div>
        )}

        {config && (
          <div className="grid md:grid-cols-2 gap-6">

            {/* Stack Identity */}
            <Card title="Stack Identity" icon={<Server className="w-6 h-6 text-amber-400" />} color="border-amber-400/30 hover:border-amber-300/50">
              <dl>
                <KV label="Name"         value={String(config.stack.name)} />
                <KV label="Domain"       value={String(config.stack.domain)} />
                <KV label="Root"         value={String(config.stack.root)} />
                <KV label="Backend Port" value={String(config.stack.backend_port)} />
                <KV label="Frontend Port"value={String(config.stack.frontend_port)} />
                <KV label="Redis DB"     value={String(config.stack.redis_db)} />
                <KV label="Solr Core"    value={String(config.stack.solr_core)} />
              </dl>
            </Card>

            {/* Ollama */}
            <Card title="Ollama / AI" icon={<Cpu className="w-6 h-6 text-purple-400" />} color="border-purple-400/30 hover:border-purple-300/50">
              <dl>
                <KV label="Host"               value={config.ollama.host} />
                <KV label="Primary Model"      value={config.ollama.primary_model} />
                <KV label="Fallback Model"     value={config.ollama.fallback_model} />
                <KV label="Translation Model"  value={config.ollama.translation_model} />
                <KV label="Translation Fields" value={config.ollama.translation_fields} />
              </dl>
            </Card>

            {/* Runtime Toggles */}
            <Card title="Runtime Toggles" icon={<Zap className="w-6 h-6 text-green-400" />} color="border-green-400/30 hover:border-green-300/50">
              <dl>
                <Toggle label="Bluesky Autopost"  value={config.runtime.bluesky_autopost}  source="Redis: bluesky:autopost" />
                <KV label="Article Count"  value={config.runtime.article_count.toLocaleString()} />
                <KV label="Last Publish"   value={config.runtime.last_publish
                  ? new Date(config.runtime.last_publish).toLocaleString()
                  : '—'} mono={false} />
              </dl>
            </Card>

            {/* Scribe */}
            <Card title="Scribe" icon={<Clock className="w-6 h-6 text-blue-400" />} color="border-blue-400/30 hover:border-blue-300/50">
              <dl>
                <KV label="Cycle Sleep (s)"      value={String(config.scribe.cycle_sleep_seconds)} />
                <KV label="Sleep Interval (s)"   value={String(config.scribe.cycle_sleep_interval)} />
                <KV label="Max Analyzers"        value={String(config.scribe.max_concurrent_analyzers)} />
                <KV label="Priority Queue Key"   value={String(config.scribe.priority_queue_key)} />
              </dl>
            </Card>

            {/* Bluesky */}
            <Card title="Bluesky Poster" icon={<span className="text-sky-400 text-lg" aria-hidden="true">🦋</span>} color="border-sky-400/30 hover:border-sky-300/50">
              <dl>
                <KV label="Handle"          value={String(config.stack.handle)} />
                <KV label="Jitter Min (s)"  value={String(config.bluesky.jitter_min_seconds)} />
                <KV label="Jitter Max (s)"  value={String(config.bluesky.jitter_max_seconds)} />
                <KV label="CA Wait (s)"     value={String(config.bluesky.counter_analyst_wait_seconds)} />
                <KV label="Poll (s)"        value={String(config.bluesky.poll_interval_seconds)} />
              </dl>
            </Card>

            {/* Services */}
            <Card title="Services" icon={<Server className="w-6 h-6 text-cyan-400" />} color="border-cyan-400/30 hover:border-cyan-300/50 md:col-span-2">
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-8">
                {Object.entries(config.services).map(([name, enabled]) => (
                  <Toggle key={name} label={name} value={enabled} />
                ))}
              </dl>
            </Card>

            {/* Mailer + Translation + Feed */}
            <Card title="Mailer" icon={<span className="text-orange-400 text-lg" aria-hidden="true">✉</span>} color="border-orange-400/30 hover:border-orange-300/50">
              <dl>
                <KV label="Alert To"          value={String(config.mailer.alert_to)} />
                <KV label="Digest Hour"       value={`${config.mailer.digest_hour}:00`} />
                <KV label="Stall Threshold"   value={`${config.mailer.stall_threshold_hours}h`} />
                <KV label="Scan Interval (s)" value={String(config.mailer.log_scan_interval_seconds)} />
              </dl>
            </Card>

            <Card title="Translation & Feed" icon={<Database className="w-6 h-6 text-pink-400" />} color="border-pink-400/30 hover:border-pink-300/50">
              <dl>
                <KV label="Cache TTL"        value={`${config.translation.cache_ttl_hours}h`} />
                <KV label="Lock TTL (s)"     value={String(config.translation.lock_ttl_seconds)} />
                <KV label="Ollama Backoff (s)" value={String(config.translation.ollama_backoff_seconds)} />
                <KV label="Feed Page Size"   value={String(config.feed.default_page_size)} />
                <KV label="Feed Max Size"    value={String(config.feed.max_page_size)} />
              </dl>
            </Card>

          </div>
        )}

        {/* Footer */}
        <footer className="text-center text-xs text-slate-600 pt-12">
          Read-only · Values from <code className="font-mono">arc_config.yaml</code> + Redis ·{' '}
          <Link href="/about/developer" className="text-amber-300/60 hover:text-amber-200 transition-colors">
            Developer Docs
          </Link>
        </footer>

      </main>
    </PageWrapper>
  );
};

export default ConfigPage;
