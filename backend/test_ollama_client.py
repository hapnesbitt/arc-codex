#!/usr/bin/env python3
# Filename: test_ollama_client.py
# Phase 4 test plan for ollama_client.py host-failover wrapper.
# Run: cd backend && source venv/bin/activate && python3 test_ollama_client.py
#
# Real completions go to the M1 (192.168.1.185) via gemma4:e2b (small/fast).
# No cloud model is invoked (avoids burning cloud credits) — cloud pinning is
# verified by routing assertion instead.

import time
import logging

import requests
import ollama_client

M1        = "http://192.168.1.185:11434"
DEAD_PORT = "http://127.0.0.1:9"        # connection refused — instant
BLACKHOLE = "http://192.0.2.1:11434"    # RFC5737 TEST-NET — connect times out (~3s)
# gemma4:e2b is a thinking model: a small num_predict is spent entirely on hidden
# reasoning and returns empty text, so real-completion calls run uncapped.
SMALL = {"model": "gemma4:e2b", "stream": False}                 # real completions
TINY  = {"model": "gemma4:e2b", "stream": False,
         "options": {"num_predict": 1}}                          # timing/routing only (never completes)

# ── Capture failover log lines ───────────────────────────────────────────────
_captured = []

class _Capture(logging.Handler):
    def emit(self, record):
        _captured.append(record.getMessage())

ollama_client.logger.setLevel(logging.WARNING)
ollama_client.logger.addHandler(_Capture())

def failover_lines():
    return [m for m in _captured if m.startswith("ollama_failover")]

def reset():
    _captured.clear()
    ollama_client.reset_breaker()

results = []
def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ── Test 1: real completion succeeds via fallback; exactly one failover line ──
def test1_failover_completion():
    print("\nTEST 1 — failover to fallback, real completion, one log line")
    reset()
    ollama_client.configure(primary=DEAD_PORT, fallback=M1)
    resp = ollama_client.post("/api/generate",
                              json={**SMALL, "prompt": "Reply with one word."},
                              read_timeout=120)
    text = resp.json().get("response", "").strip()
    check("real completion via fallback (M1)", resp.status_code == 200 and bool(text),
          f"status={resp.status_code} text={text!r}")
    lines = failover_lines()
    check("exactly one failover log line", len(lines) == 1, f"{len(lines)} line(s)")
    if lines:
        print(f"        > {lines[0]}")


# ── Test 2: circuit breaker — calls 2 & 3 skip the 3s connect timeout ─────────
def test2_circuit_breaker():
    print("\nTEST 2 — breaker skips the 3s primary timeout on calls 2 & 3")
    reset()
    # blackhole primary => 3s connect timeout; dead-port fallback => instant fail.
    # This isolates timing from inference: every call raises, we measure only wait.
    ollama_client.configure(primary=BLACKHOLE, fallback=DEAD_PORT)
    lat = []
    for i in range(3):
        t = time.perf_counter()
        try:
            ollama_client.post("/api/generate",
                               json={**TINY, "prompt": "x"}, read_timeout=5)
        except requests.exceptions.RequestException:
            pass  # both hosts unreachable by design — we only care about latency
        lat.append(time.perf_counter() - t)
    print(f"        latencies: call1={lat[0]:.2f}s call2={lat[1]:.2f}s call3={lat[2]:.2f}s")
    check("call 1 pays the ~3s primary connect timeout", lat[0] >= 2.5, f"{lat[0]:.2f}s")
    check("call 2 skips it (breaker open)", lat[1] < 1.0, f"{lat[1]:.2f}s")
    check("call 3 skips it (breaker open)", lat[2] < 1.0, f"{lat[2]:.2f}s")
    # Only call 1 actually failed over (2 & 3 went straight to fallback).
    check("one failover line across the 3 calls", len(failover_lines()) == 1,
          f"{len(failover_lines())} line(s)")


# ── Test 3: recovery — after the 60s window, traffic returns to primary ───────
def test3_recovery():
    print("\nTEST 3 — recovery: primary used again after breaker window expires")
    reset()
    # primary = M1 (healthy), fallback = dead. Success can ONLY come from primary.
    ollama_client.configure(primary=M1, fallback=DEAD_PORT)
    ollama_client._trip_breaker()  # simulate a prior outage; breaker now open ~60s

    # While open: primary is skipped -> fallback(dead) -> fails. Proves skip.
    skipped = False
    try:
        ollama_client.post("/api/generate", json={**TINY, "prompt": "x"}, read_timeout=5)
    except requests.exceptions.RequestException:
        skipped = True
    check("while breaker open, primary is skipped (hits dead fallback)", skipped)

    wait = ollama_client.BREAKER_WINDOW + 1
    print(f"        waiting {wait:.0f}s for breaker window to expire...")
    time.sleep(wait)

    resp = ollama_client.post("/api/generate",
                              json={**SMALL, "prompt": "Reply with one word."},
                              read_timeout=120)
    text = resp.json().get("response", "").strip()
    check("after window, completion succeeds via primary (M1)",
          resp.status_code == 200 and bool(text), f"status={resp.status_code} text={text!r}")


# ── Test 4: inert mode — primary == fallback == M1, zero behaviour change ─────
def test4_inert_and_cloud_pinning():
    print("\nTEST 4 — inert mode (primary == fallback == M1): no failover, plus cloud pinning")
    reset()
    ollama_client.configure(primary=M1, fallback=M1, cloud=M1)

    # Exercise the REAL integrated scribe/dlb path (ollama_utils -> ollama_client).
    import ollama_utils
    ollama_utils.OLLAMA_LOCAL_FALLBACK = "gemma4:e2b"   # use the small model first
    text, dur, model = ollama_utils.call_ollama_local_only("Reply with one word.", timeout=180)
    # Which local model answers depends on M1 load (the model-fallback loop is
    # orthogonal to transport); we only assert a real completion came back.
    check("call_ollama_local_only (scribe path) returns a completion",
          bool(text), f"model={model} {dur:.0f}ms text={text!r}")
    check("zero failover log lines in inert mode", len(failover_lines()) == 0,
          f"{len(failover_lines())} line(s)")

    # Cloud pinning (constraint 2): -cloud models route to CLOUD_HOST, never primary.
    # Verified without a real cloud call (no credits burned) by capturing the URL.
    reset()
    ollama_client.configure(primary=BLACKHOLE, fallback=DEAD_PORT, cloud=M1)
    captured_url = {}
    real_post = requests.post
    def spy(url, *a, **k):
        captured_url["url"] = url
        return real_post(url, *a, **k)
    requests.post = spy
    try:
        ollama_client.post("/api/generate",
                           json={"model": "devstral-2:123b-cloud", "prompt": "x",
                                 "stream": False, "options": {"num_predict": 1}},
                           read_timeout=2, connect_timeout=1)
    except requests.exceptions.RequestException:
        pass  # M1 may reject/slow the cloud call; we only assert the host chosen
    finally:
        requests.post = real_post
    check("cloud model pinned to CLOUD_HOST (M1), not primary/blackhole",
          captured_url.get("url", "").startswith(M1), captured_url.get("url"))
    check("no host failover attempted for cloud model", len(failover_lines()) == 0,
          f"{len(failover_lines())} line(s)")


if __name__ == "__main__":
    print("=" * 70)
    print("ollama_client.py — Phase 4 test plan")
    print("=" * 70)
    test1_failover_completion()
    test2_circuit_breaker()
    test3_recovery()
    test4_inert_and_cloud_pinning()
    print("\n" + "=" * 70)
    print(f"RESULT: {sum(results)}/{len(results)} checks passed")
    print("=" * 70)
    raise SystemExit(0 if all(results) else 1)
