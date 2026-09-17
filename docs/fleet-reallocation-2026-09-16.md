# Fleet reallocation — 2026-09-16 (in-flight)

Target shape: **resolute serves, spectre runs Arc's analysis, warden runs Hunt's analysis plus Arc's broadcast scripts, the M1 runs Kokoro.**

This is a restart-resumable note, not a summary. Each section says what's done, what's committed, what's still deferred, and where the next session picks up.

---

## Root cause of the two -np 2 → `-c 65536` OOMs

Hunt's `_apply_spec_following_options` defaulted `num_ctx=32768`. Arc dropped to 16384 in 2026-09-13 commit `46f7a17`; **Hunt was never mirrored** — Arc-forward drift per parity audit section C. Both stacks' analyzers reach spectre; ollama sizes llama-server from whichever client arrives first after a restart. On both `-np 2` attempts (2026-09-13 and 2026-09-16), Hunt's request landed first at 32768, so llama-server spawned with `-c 65536 -np 2`, which overflows spectre's 14 GiB.

**Fix landed 2026-09-16, commit `d4edab2` on Hunt branch `fix/translate-failure-visibility`.** Hunt's default now matches Arc at 16384. Analyzer, scribe, manual_publisher, and gunicorn all restarted on Hunt to pick up new code + new .env (below). 87 tests green.

---

## Numbered plan status

### 1. Hunt num_ctx cap ✅ DONE
- Committed: Hunt `d4edab2`.
- Restarts applied on Hunt: analyzer (884079), scribe (884192), manual_publisher (884133), gunicorn (884253).
- Post-restart verification: `python -c "from ollama_utils import OLLAMA_URL; print(OLLAMA_URL)"` inside Hunt's venv returns `http://192.168.1.190:11434`; `is_local_available(OLLAMA_URL)` returns True.
- Flagged not touched: `huntaegis.cfg [pipeline].analysis_max_chars = 100000` still assumes 32k n_ctx. With 16k, ~1.4% of articles silently truncate (Arc paired-halved to 50000 in `44a99a4`). One-line follow-up when Ross wants it.

### 2. Hunt inference to warden ✅ DONE (.env, gitignored — not committed)
- Warden IP verified: **192.168.1.190** (curl 200 on /api/tags; ping 0.7ms).
- Ollama on warden confirmed running, bound `0.0.0.0:11434`, `OLLAMA_KEEP_ALIVE=30m`.
- Model inventory on warden today: **gemma4:e2b (6 GB) already pulled**, qwen2.5:1.5b (~1 GB) present but rejected per Ross's Sept format-test failure note, gemma4:26b **pulling but not yet in `/api/tags`**.
- Hunt `backend/.env` (gitignored, uncommitted — documented in `d4edab2` commit body):
  ```
  OLLAMA_URL=http://192.168.1.190:11434         # was 192.168.1.189 (spectre)
  TRANSLATION_HOST=http://192.168.1.190:11434   # was 192.168.1.189 (spectre)
  ```
- Stale comment block around lines 25-31 of Hunt's `.env` (about "moving Ollama off both 8GB boxes") rewritten to reflect the split.
- Hunt's next analyzer queue pop will hit warden. Queue depth at handoff: 0.

### 3. Arc broadcast script to warden ✅ DONE (.env, gitignored — not committed)
- Arc `backend/.env` added block:
  ```
  BROADCAST_OLLAMA_HOST=http://192.168.1.190:11434
  BROADCAST_OLLAMA_MODEL=gemma4:e2b
  ```
- Model choice: `gemma4:e2b` per Ross's explicit rejection of `qwen2.5:1.5b` after September format-test failure.
- Restart applied on Arc: scribe (884374). Post-restart:
  ```
  BROADCAST_OLLAMA_HOST: http://192.168.1.190:11434
  BROADCAST_OLLAMA_MODEL: gemma4:e2b
  Arc OLLAMA_URL (unchanged): http://192.168.1.189:11434
  ```
- No Arc code commit — env changes only. `.env` diff is on disk but gitignored; commit history for this piece lives in `d4edab2`'s commit body cross-reference.

### 4. Kokoro back to M1 ⏸ REPORT-ONLY, NOT EXECUTED

Research gathered before the plan expanded and paused this:

- Current `AUDIO_KOKORO_PYTHON` (from `backend/scribe.py:1037`): `os.environ.get(...)` reads the env; when unset, default is likely `/home/ross/.venvs/kokoro/bin/python3` on resolute (verify at execution time; the default string wasn't fully captured before context switch).
- Systemd unit at `/etc/systemd/system/audio-backfill.service` currently **inactive since 2026-09-03 06:51:06** (`journalctl -u audio-backfill`). No audio narrated in 13 days.
- The daemon's own header comment: "Resolute has no FileVault-equivalent boot gate blocking that (unlike the M1), so this actually works here." — that was the whole point of the resolute placement.
- FileVault two-tier gate (memory `m1-filevault-two-tier-gate`): sshd starts from the system volume (TCP:22 opens), but `~/.ssh` and `~/.ollama/models` stay encrypted until a user logs in. If Kokoro's venv, model weights, or output directory live under `~/`, they're unreachable between reboot and login.
- **Ross accepts the login-after-reboot constraint per today's message.** That resolves the FileVault objection — after login, the data volume mounts and everything under `~/` works normally. Between reboot and login is the gap.
- **Question still open (for report):** does the narration daemon run on M1 (systemd unit on Linux only; M1 needs launchd), or does the daemon stay on warden and shell out to M1 for synthesis (mirrors the old M1 architecture before 2026-08-20)? The old shape had the daemon on resolute and Kokoro on M1 via ssh — that's the pattern to consider first.
- **Next-session first step for item 4:** finish the AUDIO_KOKORO_PYTHON default read from scribe.py, confirm resolute's current kokoro venv path, decide daemon-on-M1 (launchd) vs daemon-on-warden-shelling-to-M1 (ssh), and report before touching anything.

### 5. Warden hardware confirmed + benchmark ⏸ NOT STARTED

- 24 GB RAM confirmed today (was 7 GiB per stale comments). 20 GB free, 4 GB swap unused, 457 GB disk at 23%.
- Ollama installed, running, bound `0.0.0.0:11434`.
- Models needed for benchmark: **gemma4:26b** (~16 GB, currently pulling per Ross), **gemma4:e4b** (~9.6 GB, needs to be pulled).
- Benchmark protocol Ross specified:
  - Real article body + its Red/Blue/Purple analysis (not a toy prompt)
  - Report: load time, prompt-eval rate, generation rate, whether swap is touched
- Existing benchmark harness: `backend/arc_benchmark.py`. Adapt its prompt input to a real analyzed article; likely one hgetall from Redis + tokenize.
- Once benchmark lands, decision on gemma4:26b vs gemma4:e4b as the model for the essay-length escalation pass (item 6 below).

---

## Future capability, SCOPED NOT BUILT

### 6. Essay-length escalation pass
- Shape: same as `scribe.run_broadcast_script` but essay-length on a bigger model.
- Input: one story + its full Red/Blue/Purple analysis.
- Output: **Arc's own original article** addressing what the source left unanswered — **better than the original, not a summary**.
- Editorial guardrail (non-negotiable): must be Arc's own prose about the story, never a rewrite of the source. **Confirm the existing broadcast prompt's guardrail holds at essay length** — the current prompt is bounded by BROADCAST_NUM_PREDICT=300 tokens (~1100 chars); at essay length the guardrail might drift. That's a prompt-engineering verification before any deploy.
- Deployment scope decided by the item 5 benchmark: everything, or selected stories.
- Not yet designed: trigger point (which stories, at what score, on what cadence), storage (a new field alongside red/blue/purple, or a new `article:*:essay` key), rendering (a fourth tab on IntelligenceCard, or a distinct URL).

---

## Also open, deliberately deferred

### 7. site_config adoption sweep (parity audit E.5)
- ~15 modules per stack still re-derive `os.getenv("REDIS_URL")` / HOST / PORT / DB / PASSWORD directly instead of reading from `SITE`.
- Port default (`5005`/`5006`) still in ~12 files per stack.
- Estimated ~1 day of engineering. Sufficient version of the brand extraction pass; deliberately held so the base extraction verifies in production first.

---

## Fleet state at handoff

| Host | Role today | RAM | Ollama models loaded | Notes |
|---|---|---|---|---|
| resolute (localhost) | Serves both frontends, both analyzer processes, both mailers, character_builder (council) | 32 GB | gemma4:e2b, gpt-oss:latest, qwen2.5:1.5b | audio-backfill.service inactive since 2026-09-03 |
| spectre (192.168.1.189) | Arc's analyzer, sentinel/CA, translation | 14 GB | gemma4:e2b, cloud relay | -np 1 (drop-in rolled back); llama-server currently -c 16384 -np 1 |
| warden (192.168.1.190) | **NEW** Hunt's analyzer + translation + Arc's broadcast script (all just landed 2026-09-16) | 24 GB (upgraded from 7) | gemma4:e2b loaded (6 GB); gemma4:26b pulling; gemma4:e4b to pull | 20 GB free, 4 GB swap unused, 457 GB disk at 23% |
| M1 (192.168.1.185) | **PLANNED** Kokoro (item 4, not executed) | 8 GB | Ollama models deleted 2026-09-11 | FileVault two-tier gate; Ross accepts login-after-reboot |

## Commits this pass

Hunt (`fix/translate-failure-visibility`):
- `d4edab2` — Hunt: cap num_ctx at 16384 in _apply_spec_following_options

Arc (`main`): no code commits for the split — env-only, .env is gitignored. This doc IS the commit. Prior arc commits earlier today: `f9b38bd` (parity audit), `0316059` (sales rewrite), `86592ff` (local-only mode), `b606d12` (brand extraction backend), `f0de99f` (session handoff), `8a4b8fb` (brand extraction frontend), `90ed004` (aged-out metric).

## Restarts applied

- Hunt: analyzer, scribe, manual_publisher, gunicorn (all to pick up ollama_utils num_ctx AND .env pointing at warden).
- Arc: scribe (to pick up BROADCAST_OLLAMA_HOST / BROADCAST_OLLAMA_MODEL).
- Not restarted: Arc analyzer (its .env unchanged; still on spectre); Hunt stream_consumer (doesn't call Ollama); either mailer.

## Next-session immediate checklist

1. Verify Hunt's next few analyses actually landed on warden — grep Hunt `logs/analyzer.log` for `192.168.1.190` occurrences after ~19:20 UTC.
2. Verify Arc's next broadcast script actually landed on warden — grep Arc `logs/scribe.log` for `Trying local model: gemma4:e2b @ http://192.168.1.190:11434`.
3. Item 4: report Kokoro→M1 execution shape (daemon-on-M1 vs. daemon-on-warden-ssh-to-M1) before touching anything.
4. Item 5: pull gemma4:e4b on warden; wait for gemma4:26b pull to finish; adapt `backend/arc_benchmark.py` to a real analyzed article; report benchmark.
5. Optional pair with item 1: bump Hunt `analysis_max_chars` 100000 → 50000 to match the 16k n_ctx (~1.4% truncation trade-off Arc already accepted).
