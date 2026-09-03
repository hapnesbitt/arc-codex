# Reboot readiness — resolute

What comes back after a reboot, in what order, and what's historically
failed to. Written from a live audit on 2026-09-02, the day after an
actual reboot (2026-09-01 12:56 MDT) gave real evidence to check against —
most of what's below is confirmed against that boot, not just against
`enabled` status. See `RUNBOOK.md` for the incident narrative this draws
from; this file is the standalone reference, kept current.

**Scope**: arc_stack, huntaegis_stack, newsradio_stack, the School of Chat
Character Directory (`primer_academy_directory`), and the monitoring
stack. Nothing here was fixed as part of writing it beyond
`systemctl --user enable` on units that were already installed and
already running — see "Safe fixes applied" below. Anything else stayed
exactly as found.

## Dependency chain

```
network-online.target, docker.service, cron.service   (base OS services — always enabled)
        │
        ├── arc-stack.service ──requires──> redis-server.service
        │        │              ──wants───> network-online.target, solr.service, docker.service
        │        └─ ExecStart=arc.sh start: gunicorn, frontend (docker), and
        │           the rest of the 14 [services] entries
        │
        ├── huntaegis-stack.service ──identical Requires=/Wants=, 13 services
        │
        ├── arc-watchdog.service / huntaegis-watchdog.service
        │        (independent of the *-stack units; polls PID files under
        │        logs/*.pid and restarts anything dead — see watchdog.sh)
        │
        ├── school-of-chat-directory.service (LDAP)
        │        └── school-of-chat-web.service depends on LDAP being
        │            queryable, but has no systemd After=/Requires= on it —
        │            see "Known gaps" below
        │
        ├── audio-backfill.service ──Restart=always, RestartSteps=5
        │
        ├── docker.service
        │        └── arc-loki, arc-prometheus, arc-grafana, node-exporter,
        │            arc-alertmanager — all RestartPolicy=unless-stopped,
        │            so they come back with the docker daemon with no
        │            wrapping unit needed
        │
        ├── caddy.service (reverse proxy for every *.arc-codex.com site —
        │        if this is down, nothing below is externally reachable
        │        even if it's internally healthy)
        │
        └── cron.service
                 └── newsradio_stack's build_wiki_show.py (*/17 * * * *) —
                     no unit, no @reboot entry; first run happens at the
                     next 17-minute mark after boot. If arc-codex.com/wiki
                     isn't answering yet at that mark (arc-stack.service
                     still mid-startup), that one cycle finds nothing new
                     and the next cycle 17 minutes later picks it up
                     fine — the high-water-mark design makes a missed
                     cycle a no-op, not a failure. Not a gap; noted so a
                     cold "0 tracks" reading in the first ~20 minutes
                     after boot isn't mistaken for one.
```

`arc-watchdog.service`/`huntaegis-watchdog.service` are **not** children
of `arc-stack.service`/`huntaegis-stack.service` in systemd's dependency
graph — they're separately enabled units that happen to supervise the
same processes `arc.sh start` launches. Both must be enabled
independently; one being enabled says nothing about the other.

## Status as of 2026-09-02 (day after the 2026-09-01 12:56 reboot)

| Component | Unit exists | Enabled | Verified across the 09-01 reboot |
|---|---|---|---|
| arc-stack.service (wraps all 14 `[services]` entries) | Yes | Yes | Yes — active since boot |
| — individual `[services]` processes (gunicorn, scribe, analyzer, character_builder, bluesky/mastodon/facebook_poster, manual_publisher, mailer, stream_consumer, quiz_generator, corpus_exporter, caddy_exporter) | No individual units — arc.sh manages each by PID file, not systemd | N/A | All 14 confirmed running today (`./arc.sh status`); several show restart times *after* the boot (see "Reading PID freshness" below) — expected, not a gap |
| arc-watchdog.service | Yes | Yes | Yes — active, genuinely cgroup-tracked |
| huntaegis-stack.service (wraps 13 `[services]` entries) | Yes | Yes | Yes — active since boot |
| — individual huntaegis `[services]` processes | Same as arc — no individual units | N/A | All 12 running (`./huntaegis.sh status`; 13 minus "watchdog" itself) |
| huntaegis-watchdog.service | Yes | Yes | Yes — active, cgroup-tracked |
| audio-backfill.service | Yes (now tracked in git, was untracked as of this audit's start) | Yes | **Yes** — this closes the gap `RUNBOOK.md`'s 2026-08-27 entry flagged as installed-but-reboot-unverified ("needs... an actual reboot to confirm survival, not just `systemctl restart`. Both pending Ross.") The 09-01 reboot is that confirmation. |
| school-of-chat-directory.service (LDAP) | Yes | **Was `linked`, not `enabled`, at the 09-01 reboot — did not come up automatically.** Fixed 2026-09-02 (`systemctl --user enable`). | **No** — confirmed absent right after that boot (this is the incident that started this whole audit). Fix is unverified against an actual reboot; next reboot is the test. |
| school-of-chat-web.service (faculty API, port 8765) | Yes | Yes (was already enabled before 09-01) | Yes — active since boot |
| docker.service | base OS | Yes | Yes |
| arc-loki / arc-prometheus / arc-grafana / node-exporter / arc-alertmanager | Docker containers, `RestartPolicy=unless-stopped` — no wrapping unit by design | rides on docker.service | Yes — all "up" since the boot |
| **alloy.service** (log shipper → Loki) | Yes, in `monitoring/alloy/alloy.service` | **No — never installed.** Not in `/etc/systemd/system/`, not in any user unit dir. `systemctl is-enabled` returns `not-found`, not `disabled`. | **No — not running at all**, boot or otherwise. Loki has nothing shipping logs to it right now. |
| caddy.service | vendor package unit | Yes | Yes |
| cron.service | base OS | Yes | Yes (confirmed — huntaegis's 04:00 backup-triggered gunicorn restart today only happens if cron fired correctly) |
| newsradio cron entry | N/A — cron, not systemd | n/a (depends only on cron.service) | Structurally can't fail to "come back" — it's re-evaluated by cron every 17 minutes regardless of boot history |

### Reading PID freshness — a note so today's snapshot isn't over-read later

Several arc/huntaegis service PIDs today are *newer* than the 09-01
12:56 boot (e.g. arc's gunicorn restarted ~05:59 today, scribe restarted
separately after today's `startup_kill_zombies` crash-and-patch,
huntaegis's gunicorn restarted 04:00 today matching its `0 4 * * *`
backup cron, which stops/starts services around the backup window by
design). None of this is "drift" in the concerning sense — it's normal
mid-uptime activity. It does mean that checking `systemctl status
arc-stack.service` and seeing `active (exited)` is **not** by itself
evidence the currently-running processes trace back to that unit's own
`ExecStart` — `Type=oneshot` + `RemainAfterExit=yes` never keeps spawned
daemons in the unit's own cgroup, even on a start the unit itself
triggered (confirmed independently against `RUNBOOK.md`'s own
2026-07-1x entry documenting the identical observation — this is a known
characteristic of these two units, not a new finding). The **actual**
reboot-survival evidence is the "since boot" timestamp captured above,
independent of which cgroup a process happens to sit in right now.

## Known gaps (report only — none of these were touched)

1. **Alloy was never installed.** The unit file exists in the repo but
   was never copied to `/etc/systemd/system/`, never `daemon-reload`'d,
   never enabled. This needs root (`sudo systemctl --user` doesn't apply
   to a system unit) and starting it begins active log shipping, which
   wasn't evaluated here — leaving this for Ross's call rather than
   installing it as a "safe fix."
2. **`school-of-chat-web.service` has no systemd-level dependency on
   `school-of-chat-directory.service`.** It's possible for the web unit
   to start and report healthy before LDAP is queryable, since nothing
   orders them. Today's incident (LDAP not enabled at all) would have
   shown up as `/api/faculty/*` 503s regardless of ordering, but a
   *slow* LDAP start on some future boot could produce the same 503s
   transiently even with both units correctly enabled. Not fixed here —
   would mean adding `After=`/`Wants=` to
   `primer_academy_directory/ops/systemd/school-of-chat-web.service`,
   which is a unit-file edit, not an enable.
3. **`school-of-chat-directory.service`'s fix is unverified against an
   actual reboot.** It's enabled now; the box hasn't rebooted since. The
   next reboot is the real test — watch this one specifically.

## Safe fixes applied during this audit

- `systemctl --user enable school-of-chat-directory.service` — this had
  already been done in an earlier session (2026-09-02, same day); this
  audit re-confirmed it's still enabled and found nothing else in the
  `--user`-enable class needing the same treatment. No new fixes were
  required this round.

## What to verify after the next reboot

In order — each depends on the one above it having actually worked, not
just on the unit being enabled:

```bash
# 1. Base services
systemctl is-active docker.service cron.service caddy.service

# 2. The two stacks
systemctl is-active arc-stack.service arc-watchdog.service
systemctl is-active huntaegis-stack.service huntaegis-watchdog.service
cd /home/www/arc_stack && ./arc.sh status        # all 14 green
cd /home/www/huntaegis_stack && ./huntaegis.sh status   # all 12 green

# 3. audio-backfill — confirm it's the thing this audit exists because of
systemctl is-active audio-backfill.service

# 4. Character Directory — THE thing to watch, per the known-unverified gap above
systemctl --user is-active school-of-chat-directory.service school-of-chat-web.service
cd /home/www/primer_academy_directory && ./scripts/doctor.sh   # must be fully green, not just LDAP up
curl -s http://127.0.0.1:8765/api/faculty/af.heart | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['uid'], d['identity']['displayName'])"

# 5. Monitoring containers (docker restart policy, should need nothing manual)
docker ps --format "{{.Names}}\t{{.Status}}" | grep -E "loki|prometheus|grafana|node-exporter|alertmanager"

# 6. newsradio — give it one 17-minute cron cycle before checking, per the dependency-chain note above
curl -s https://newsradio.arc-codex.com/manifest.json | python3 -c "import json,sys; print(len(json.load(sys.stdin)['tracks']), 'tracks')"
# 0 tracks in the first cycle after a reboot is expected (see the
# dependency-chain note on newsradio above), not itself a failure signal

# 7. Public endpoints, end to end
curl -s -o /dev/null -w "%{http_code}\n" https://arc-codex.com/reporters/af_heart
curl -s -o /dev/null -w "%{http_code}\n" https://newsradio.arc-codex.com/
```

If step 4 is anything but active+active+all-green, that's the specific
regression this whole audit was written to catch — don't assume it'll
self-heal; `school-of-chat-web.service` will report itself healthy while
serving `/api/faculty/*` 503s the whole time LDAP is down (see gap #2
above).
