#!/usr/bin/env python3
"""
Essay-pass verification: five articles, e4b on warden, (red, blue, purple)
signature only — original_text NEVER enters the prompt. Structural
constraint enforced by the function shape, not by prompt language.

Prompt combines the broadcast prompt's FIDELITY + SOURCE DISCIPLINE
sections with the four essay-length additions from the scope report.
"""

import json, os, sys, time, urllib.request

sys.path.insert(0, "/home/www/arc_stack/backend")
import redis  # noqa: E402
import yaml  # noqa: E402

HOST = "http://192.168.1.190:11434"
MODEL = "gemma4:e4b"
NUM_CTX = 16384
NUM_PREDICT = 3000  # essay-length budget; well above bench 715 t observed
TIMEOUT = 1800

SCRATCH = os.path.dirname(os.path.abspath(__file__))
PROMPTS_PATH = "/home/www/arc_stack/backend/prompts.yaml"

ARTICLES = [
    "9c37f564c0d84eabc4236e77c80499ed",  # MIRI: If Anyone Builds It, Everyone Dies
    "9ec8a7f98fbd4f9c1211a33b5af6e7ad",  # True-Crime producer posed as heiress
    "7a468ae7d42c176e1860ef4ef48d443c",  # ALMA / Betelgeuse hotspots
    "f5a81066bba4a33c5be7da91d4bda6a2",  # AI in Agriculture
    "cfd9839af7b44ff4ac2e87c763288eed",  # Aliencell / CHITUBOX 3D printer
]


def build_essay_prompt(red: str, blue: str, purple: str) -> str:
    """Combine mission + broadcast fidelity/source-discipline blocks with
    the four essay-length additions from the scope report. NO original_text
    parameter — the source article is not available in this signature.
    """
    with open(PROMPTS_PATH) as f:
        p = yaml.safe_load(f)
    mission = p.get("mission", "")
    broadcast = (p.get("teams", {}).get("broadcast", {}).get("instruction", "")).strip()
    constraints = p.get("constraints", [])
    ctxt = "\n".join(f"- {c}" for c in constraints) if isinstance(constraints, list) else str(constraints)

    essay_additions = """
ESSAY-LENGTH ADDITIONS (on top of the FIDELITY and SOURCE DISCIPLINE
sections above, which still apply):

1. ANTI-SUMMARY: You do not have access to the source article. Do not
   narrate what the source said — the reader has already read it, and
   the R/B/P findings above are Arc's derived understanding, not the
   article's own prose. Do not restate what those findings already
   state; use them as the ground you reason from.

2. WHAT THIS IS: Identify the unanswered questions the R/B/P findings
   raise — the parts the analysis surfaced that the article did not
   resolve. Address one or two in depth. This is Arc's own reasoning
   about what was left open, not a paraphrase of any team's finding
   and not a rewrite of the Purple analysis at greater length.

3. FACTUAL GROUNDING: Every concrete factual claim — numbers, actors,
   events, quotes — must be traceable to a Red Team fact above. If R,
   B, and P do not establish it, do not include it, even if you
   believe it is true. Speculation about implications is fine and is
   part of the point; invention of facts is not.

4. LENGTH: Write until the argument is complete. If the R/B/P
   findings do not give you enough to sustain an essay, produce a
   shorter one — a two-paragraph honest essay beats a five-paragraph
   padded one. Aim for roughly 500–1500 words; do not pad to hit a
   target.
"""

    return f"""{mission}

BROADCAST-SHAPED SOURCE DISCIPLINE (unchanged from broadcast prompt):
{broadcast}

{essay_additions}

CONSTRAINTS:
{ctxt}

--- RED TEAM FINDINGS (facts) ---
{red}

--- BLUE TEAM FINDINGS (summary) ---
{blue}

--- PURPLE TEAM FINDINGS (analysis) ---
{purple}"""


def call_e4b(prompt: str):
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"num_predict": NUM_PREDICT, "num_ctx": NUM_CTX},
    }).encode()
    req = urllib.request.Request(
        f"{HOST}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        resp = json.loads(r.read())
    wall = time.perf_counter() - t0
    return resp, wall


def main():
    pw = None
    with open("/home/www/arc_stack/backend/.env") as f:
        for line in f:
            if line.startswith("REDIS_PASSWORD="):
                pw = line.split("=", 1)[1].strip()
                break
    if not pw:
        sys.exit("no REDIS_PASSWORD")

    r = redis.Redis(decode_responses=True, password=pw, db=0)

    results = []
    for i, aid in enumerate(ARTICLES, 1):
        key = f"article:{aid}"
        title = r.hget(key, "title") or "(no title)"
        red = r.hget(key, "red_team_analysis") or ""
        blue = r.hget(key, "blue_team_analysis") or ""
        purple = r.hget(key, "purple_team_analysis") or ""
        if not (red and blue and purple):
            print(f"[{i}/5] {aid} SKIP — missing R/B/P")
            continue
        prompt = build_essay_prompt(red, blue, purple)
        print(f"[{i}/5] {aid} — {title[:80]}")
        print(f"       R={len(red)} B={len(blue)} P={len(purple)} prompt={len(prompt)} chars")
        try:
            resp, wall = call_e4b(prompt)
        except Exception as e:
            print(f"       FAIL: {e}")
            continue
        essay = resp.get("response", "")
        out_path = f"{SCRATCH}/essay_{i}_{aid[:12]}.txt"
        with open(out_path, "w") as f:
            f.write(f"# {title}\n# id={aid}\n\n")
            f.write("## ESSAY OUTPUT\n\n")
            f.write(essay)
            f.write("\n\n## R/B/P GROUND TRUTH FED TO MODEL\n\n")
            f.write("### RED\n" + red + "\n\n### BLUE\n" + blue + "\n\n### PURPLE\n" + purple + "\n")
        results.append({
            "n": i, "id": aid, "title": title,
            "wall_s": round(wall, 1),
            "gen_tokens": resp.get("eval_count", 0),
            "essay_chars": len(essay),
            "essay_words": len(essay.split()),
            "done_reason": resp.get("done_reason"),
            "out": out_path,
        })
        print(f"       wall={wall:.1f}s gen_tokens={resp.get('eval_count')} chars={len(essay)} → {out_path}")

    print("\n=== SUMMARY ===")
    for row in results:
        print(row)


if __name__ == "__main__":
    main()
