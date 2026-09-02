# CODEX.md

Startup guidance for Codex in this repository.

## Required orientation

Before changing anything:

1. Read [CLAUDE.md](CLAUDE.md) fully. It is the canonical architecture,
   product, data-layout, and convention guide.
2. For operations, deployment, recovery, host coordinates, or service
   troubleshooting, read the relevant parts of
   [ops/RUNBOOK.md](ops/RUNBOOK.md).
3. Check 'git status --short' and preserve unrelated user changes.
4. Check whether the same fix belongs in the sibling repository at
   '/home/www/huntaegis_stack'.

If documentation and runtime disagree, verify code, configuration, processes,
Redis, Solr, Docker, and systemd. Evidence wins over narrative accounts.

## Production control plane

- Manage application workers with './arc.sh start|stop|restart [service]'.
  Never launch production workers manually.
- The watchdog is supervised separately by 'arc-watchdog.service' with
  'Restart=always'; it is not owned by arc.sh.
- The boot unit is 'arc-stack.service'. Its ExecStartPre runs
  'backend/validate_sites.py'; site isolation must remain fail-closed.
- Watchdog recovery validates PID, cwd, and command identity; adopts an
  unregistered stack process; reconciles duplicates; honors
  'pids/<service>.disabled'; and applies bounded restart backoff. Preserve
  these guards together.
- Port cleanup may terminate only matching listeners from this stack. A
  foreign listener is a collision to report, never a process to kill.
- Use the stack manager for targeted restarts so PID registration and
  'watchdog.hold' coordination remain correct.
- Changes under 'ops/systemd/' are inactive until installed under
  '/etc/systemd/system/' and followed by 'systemctl daemon-reload'. Verify
  installed files byte-for-byte and inspect loaded properties afterward.

## Isolation and configuration

- Arc: Redis DB 0, Flask 5005, frontend 3000, Solr core 'feeds', cold backups
  under '/mnt/arcdata/backups'.
- Hunt: Redis DB 1, Flask 5006, frontend 3002, Solr core 'feeds_huntaegis',
  cold backups under '/mnt/arcdata/backups/huntaegis'.
- Never weaken 'backend/validate_sites.py' to accommodate a collision.
- 'site_config' and 'arc.cfg' are current. Do not reintroduce legacy
  'arc_config.yaml' fallbacks.
- The '[ingestion]' timing fields in arc.cfg are operator-owned. Follow the
  exact policy in CLAUDE.md and do not normalize or revert them.

## Work and verification

- Diagnose read-only first. During incidents, restore service, report
  restoration, then address systemic causes.
- Use apply_patch for edits and keep commits narrowly scoped.
- For service changes, verify PID, '/proc/<pid>/cwd', command line, watchdog,
  Redis heartbeat, and queue state as applicable.
- For systemd changes, run 'systemd-analyze verify', install and reload, then
  inspect loaded properties with 'systemctl show'.
- Finish with 'git diff --check' and 'git status --short'.

## Traffic observability

- The custom Caddy traffic exporter is 'backend/caddy_exporter.py', managed
  only through './arc.sh start|stop|restart caddy_exporter'. Its Prometheus
  target is 'arc_traffic' on port 9102.
- Exporter positions under '/var/lib/arc-traffic-exporter' are production
  continuity state. Never reset, delete, or backfill them without explicit
  operator approval. Recovery must remain fail-closed when a retained
  rotation boundary is missing, ambiguous, unsafe, or outside configured
  bounds.
- After an exporter restart, 'up{job="arc_traffic"} == 1' proves only that
  Prometheus can scrape the process. Also require per-site
  'arc_traffic_exporter_ready == 1', lag zero, and zero checkpoint, parse,
  recovery, and known-duplicate errors before declaring it caught up.
- Grafana production dashboard UID 'arc-traffic-v2' and correctness-pilot UID
  'arc-traffic-correctness-pilot' are separate approval domains. Never promote
  or overwrite production merely because the pilot validates.
- Validate selected-range traffic with identical explicit Caddy-event and
  Prometheus boundaries. A restart can shift replayed events into scrape time,
  and newly appearing labeled counter series can hide their first value from
  'increase()'; distinguish these metric-semantics effects from source-log
  loss.
- Keep Prometheus labels bounded. Traffic paths use the fixed 'path_group'
  vocabulary; never add full URI, query string, exact client IP, full user
  agent, referer, article ID, or attacker-controlled strings as labels.

## Non-negotiable product rule

Scores annotate; they never gate or rank the chronological article feed.
Follow the complete rule and sanctioned exceptions in CLAUDE.md.
