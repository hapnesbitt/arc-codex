#!/usr/bin/env python3
# backend/quiz_generator.py
#
# Pop Quiz — weekly news quiz generator service.
#
# Selection: walk the feed ZSET newest-first; take the first 7 public
# articles whose Red Team analysis is substantive (>= MIN_RED_CHARS).
# That's the whole rule. One question per article. Red is the canonical
# grounding source for generation and for the validators.
#
# Asks Ollama to produce 7 strict-JSON multiple-choice questions, then
# validates structure (4 distinct options, correct ∈ 0..3), option/
# explanation integrity (the correct option text must appear in the
# explanation, and any score/$/%/year asserted in the explanation must
# appear in some option), grounding (correct option word-overlaps source),
# banned-phrase voice filter. Stored at arc:quiz:YYYY-Www, current-pointer
# at arc:quiz:current.
#
# Long-loop service in the scribe style — watchdog-restartable, fires every
# CYCLE_MINUTES (5 h). Each cycle compares the top-7 candidate IDs against
# the live quiz's source IDs; if identical, the pool has not turned over
# and the cycle is a no-op. The moment one article rotates in or out, the
# next cycle regenerates. Lock prevents racing instances.
#
# Manual run (no loop): python3 quiz_generator.py --once
# Force regen of current week: python3 quiz_generator.py --once --force

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import redis
from dotenv import load_dotenv

from ollama_utils import call_ollama_with_fallback

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [quiz_generator] %(message)s",
)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CYCLE_MINUTES = 300              # 5 h — roughly the rate at which 7 fresh substantive-Red stories accumulate
QUESTION_TARGET = 7
MIN_RED_CHARS = 200              # substantive Red required — placeholders/one-liners excluded

QUIZ_KEY_FMT = "arc:quiz:{slug}"
STAGING_KEY_FMT = "arc:quiz:staging:{slug}"
CURRENT_KEY = "arc:quiz:current"
COUNTER_KEY = "arc:quiz:counter"   # lifetime quiz # — INCR'd ONLY at successful promote
LOCK_KEY = "arc:quiz:generating"
LOCK_TTL = 600

# Single local model for quiz generation. Cloud is intentionally NOT
# included — the quiz must not depend on weekly cloud quota. No local-to-local
# fallback (fleet policy 2026-07-01; qwen2.5-coder:7b was removed from the M1
# in the same cleanup). If we later want cloud as a quality boost during
# healthy quota, prepend ("devstral-2:123b-cloud", "cloud").
QUIZ_MODELS = [
    ("gemma4:e2b", "local"),
]

# JSON Schema for a SINGLE question. We generate the quiz one article at a
# time (each Ollama call returns one question for one article), which makes
# dup-source structurally impossible — the model only sees the article we
# want it to use, and we attach `source_article_id` post-hoc. The orchestrator
# loops over the 7 candidates and assembles the array.
QUIZ_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "minLength": 10},
        "options": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {"type": "string", "minLength": 1},
        },
        "correct": {"type": "integer", "minimum": 0, "maximum": 3},
        "explanation": {"type": "string", "minLength": 5, "maxLength": 240},
    },
    "required": ["question", "options", "correct", "explanation"],
}

BANNED_PHRASES = [
    "recent article", "did you know", "according to",
    "fascinating", "unprecedented", "incredible",
    "in this article", "the article says",
]

# Dangling-reference phrases the model writes because IT can see the article;
# the reader can't. Each requires an antecedent the reader lacks ("the author"
# of WHICH paper?). Word-boundary matched so a legit literal entity like
# "The Coca-Cola Company" or "the United States Department of..." doesn't get
# caught. Heuristic — kills the common offenders; the broader self-contained
# requirement lives in the prompt.
_DANGLING_REFERENCE_RE = re.compile(
    r"\b(?:"
    r"the authors?|the report|(?:the|this) study|(?:the|this) article|"
    r"the company|the firm|the researchers?|the paper|the document|"
    r"the piece|the writer"
    r")\b",
    re.IGNORECASE,
)

STOPWORDS = set("""
a an and are as at be by for from has have he her his i in is it its of on or our she
that the their them they this to was we were what when where which who will with you
your about into over under between among
""".split())

# Canonical-form normalization for the option/explanation integrity check.
# Equates "$84.17m" with "$84.17 million", "US$8 trillion" with "$8 trillion",
# "$10B" with "$10 billion", "5K" with "5 thousand". Tight by design — only
# magnitude abbreviations after a number and the US$ currency prefix; nothing
# else. Adding more equivalents risks reopening the "answer not in any option"
# hole that the substring check is meant to close.
_CURRENCY_PREFIX_RE = re.compile(r"\bus\$", re.IGNORECASE)
_MAGNITUDE_MAP = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion"}
_MAGNITUDE_RE = re.compile(r"(\d(?:[\d,.]*\d)?)\s*([kmbt])\b", re.IGNORECASE)


def canonical_value_form(s: str) -> str:
    """Normalize currency prefix + compact magnitude letters to verbose form,
    case-folded, with collapsed whitespace. See _MAGNITUDE_MAP for what counts.
    Also folds "No." → "No" (ordinal abbreviation) so option "No. 2" matches
    explanation "No 2" — a narrow punctuation gap we saw in real failures."""
    s = s.lower().strip()
    s = _CURRENCY_PREFIX_RE.sub("$", s)
    s = _MAGNITUDE_RE.sub(lambda m: f"{m.group(1)} {_MAGNITUDE_MAP[m.group(2).lower()]}", s)
    s = re.sub(r"\bno\.\s*", "no ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Redis
# ──────────────────────────────────────────────────────────────────────────────
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ Redis connected")
except Exception as e:
    logger.critical(f"🔥 Redis connection failed: {e}")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Week math
# ──────────────────────────────────────────────────────────────────────────────
def iso_week_slug(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_label(dt: datetime) -> str:
    iso = dt.isocalendar()
    # Monday of this ISO week
    monday = datetime.fromisocalendar(iso.year, iso.week, 1).replace(tzinfo=timezone.utc)
    return f"Week of {monday.strftime('%B %-d, %Y')}"


# ──────────────────────────────────────────────────────────────────────────────
# Candidate curation
# ──────────────────────────────────────────────────────────────────────────────
def fetch_candidates(n: int = QUESTION_TARGET) -> list[dict]:
    """Walk the feed ZSET newest-first; return the first `n` public articles
    whose Red Team analysis is substantive (>= MIN_RED_CHARS). One question
    will be generated per candidate — that's the whole selection rule."""
    fields = [
        "id", "title", "directive", "category", "source_name",
        "sourceUrl", "timestamp", "visibility",
        "red_team_analysis",
    ]
    BATCH = 100
    picked: list[dict] = []
    offset = 0
    while len(picked) < n:
        ids = r.zrevrange("feed", offset, offset + BATCH - 1)
        if not ids:
            break
        pipe = r.pipeline()
        for aid in ids:
            pipe.hmget(f"article:{aid}", *fields)
        rows = pipe.execute()
        for aid, row in zip(ids, rows):
            d = dict(zip(fields, row))
            d["id"] = aid
            if (d.get("visibility") or "") == "private":
                continue
            red = (d.get("red_team_analysis") or "").strip()
            if len(red) < MIN_RED_CHARS:
                continue
            d["_facts"] = red
            picked.append(d)
            if len(picked) >= n:
                break
        offset += BATCH
    logger.info(f"🎯 Curated {len(picked)} candidates (newest public stories with substantive Red)")
    return picked


# ──────────────────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────────────────
VOICE_CONTRACT = """You are writing the Arc Codex Pop Quiz — a 7-question multiple-choice recap of the past week.

YOUR AUDIENCE: smart, time-poor, news-aware, early-career. They read Morning Brew, Quartz Daily Brief, and Axios. They are NOT boomers. They are NOT children.

VOICE RULES (non-negotiable):
- Be witty, never try-hard. Concision is respect.
- Do NOT condescend. Do NOT over-explain.
- Do NOT use the phrases: "in a recent article", "according to", "did you know", "in this article", "the article says".
- Do NOT use the words: "fascinating", "incredible", "unprecedented".
- Do NOT use exclamation marks.
- Questions should sound like a sharp friend at brunch, not a textbook.
"""

CONTENT_CONTRACT = """Produce ONE multiple-choice question grounded in the ARTICLE below.

GROUNDING RULE (most important — overrides everything else):
- Ask about a specific fact, figure, date, name, place, quantity, or event that is EXPLICITLY STATED in the article's FACTS block. The correct answer must be a string of text that appears in (or is directly paraphrased from) that FACTS block.
- Do NOT ask definitional questions ("what is X", "how is X defined").
- Do NOT ask conceptual or "main idea" questions ("what is the primary purpose / logic / meaning / reason / theme of X").
- Do NOT introduce any fact, definition, date, figure, or claim that is not present in the FACTS block. Do not use general/world knowledge from outside the article — even if you are confident it is true.

SELF-CONTAINED RULE:
- Each QUESTION must be fully SELF-CONTAINED — answerable by a reader who has NOT read the source article. The reader sees ONLY the question and the 4 options, never the article.
- NAME every person, company, organization, place, and thing in the QUESTION. Do NOT use bare references like "the author", "the company", "the report", "the study", "the researcher", "this article", "the CEO", "the firm" — the reader has no article to resolve them against. A validator rejects these.
- BAD: "When will the author join the company?" → reader has no idea WHICH author or which company; the question is unanswerable as presented.
- GOOD: name the specific person and company from the article, even if it makes the question slightly longer.
- If the FACTS block abstracts the writer to "the author", check the SOURCE line above the FACTS for the byline (e.g. SOURCE "Hyperdimensional (Dean Ball)" → use "Dean Ball" as the author's name). If neither FACTS nor SOURCE provides a specific name to anchor the question, ask about a DIFFERENT, nameable fact from the article instead.

EXAMPLES:

GOOD (specific stated fact — a number from the text):
  Q: "How much of India's wealth did the East India Company transfer to Britain between 1765 and 1938?"
  A: "$45 trillion"
  (works because the article's FACTS block states this figure verbatim)

GOOD (specific stated fact — a date from the text):
  Q: "By what year had European control of African minerals risen to 90%?"
  A: "1900"

GOOD (specific stated fact — a named entity from the text):
  Q: "Which city's silver mine bankrolled Spain's 16th-century empire?"
  A: "Potosí"
  Explanation: "Potosí, Bolivia, produced an estimated 60% of global silver during the empire's peak."
  (works because the explanation contains the exact answer text "Potosí" verbatim — the validator requires this. Do NOT write 'the Bolivian city produced...' without naming Potosí; the option's exact text must appear in the explanation.)

BAD (self-answering — forbidden):
  Q: "Which Bolivian city, Potosí, produced 60% of global silver?"
  A: "Potosí"
  → the stem already names "Potosí"; the user isn't being asked to identify anything. Ask "Which city…" without naming the answer in the stem.

BAD (definitional — forbidden):
  Q: "What is capitalism?"  → asks for a definition, not a stated fact

BAD (conceptual / general knowledge — forbidden):
  Q: "What was the primary economic logic behind capitalism?"  → "primary logic" is conceptual; the answer comes from training data, not from a specific sentence in the FACTS block

BAD (invented specific — forbidden):
  Q: "How many merchants traded in 12th-century Cairo?"  → if the FACTS block names the city but does NOT state a count, do not invent one; pick a fact the article actually states

FORMAT:
- The QUESTION is one sentence. Specific. No "according to a recent article".
- Four OPTIONS — one correct, three plausible-but-wrong distractors a half-skimmer would fall for (right story, wrong number; right company, wrong actor; etc.). Distractors must NOT be obviously absurd. Distractors must be the same TYPE as the correct answer (if the answer is a year, distractors are years; if a dollar figure, distractors are dollar figures).
- The EXPLANATION is ONE sentence, sharp-friend tone, ≤220 chars, and must itself only state facts present in the FACTS block. State the fact DIRECTLY; do not write "the correct answer is X" or "as stated in the article" — those are filler. Just state X.
- The EXPLANATION must contain the CORRECT option's text — a validator checks this (case-insensitive, and treats compact and verbose magnitudes as equivalent, e.g. "$84.17m" ↔ "$84.17 million", "US$8 trillion" ↔ "$8 trillion", "$10B" ↔ "$10 billion", "No. 2" ↔ "No 2").
- USE CONSISTENT FORMATTING for any dollar/magnitude value across the OPTION and the EXPLANATION. Pick one form and stick to it within the question: either "$84.17 million" in BOTH the option and the explanation, OR "$84.17m" in BOTH.
- The QUESTION STEM must NOT contain the correct answer's text. Ask ABOUT the fact; do not state it in the question. If the answer is "Eric Clapton", the stem should be "Which guitarist was an early influence on X?" — NOT "Which of X's influences included Eric Clapton?" The validator rejects any question whose stem contains its own correct option text.
"""

JSON_CONTRACT = """Output is a single JSON object matching this schema:
  {
    "question": string (one sentence, ≥10 chars),
    "options": array of EXACTLY 4 distinct strings,
    "correct": integer (0, 1, 2, or 3 — the 0-based index of the correct option in `options`),
    "explanation": string (one sentence, ≤220 chars, must contain the correct option's text)
  }

Do NOT wrap in an array. Do NOT add extra fields. Output JUST the one object, no commentary."""


def build_single_prompt(article: dict, extra_reminder: str = "") -> str:
    """Prompt for ONE question grounded in ONE article. The dup-source bug
    that plagued the multi-article prompt can't happen here — the model
    literally only sees this one article. `source_article_id` is attached
    by the orchestrator afterward.

    The SOURCE byline ships alongside title + facts so the model has the
    author's name to substitute when the Red layer abstracts to 'the
    author' (a real failure we saw — the Red analyzer's prompt strips
    bylines, so without this the model can't satisfy the self-contained
    rule on first-person essays)."""
    reminder = f"\n\nIMPORTANT: {extra_reminder}\n" if extra_reminder else ""
    return (
        f"{VOICE_CONTRACT}\n\n"
        f"{CONTENT_CONTRACT}\n\n"
        f"{JSON_CONTRACT}"
        f"{reminder}\n\n"
        f"ARTICLE:\n"
        f"TITLE: {article.get('title', '')}\n"
        f"SOURCE: {article.get('source_name', '')}\n"
        f"FACTS:\n{article['_facts'][:1800]}\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Parsing + validation
# ──────────────────────────────────────────────────────────────────────────────
def parse_strict_json(raw: str) -> dict | None:
    """Tolerate code fences and a stray preamble; locate the outer {...} block."""
    if not raw:
        return None
    text = raw.strip()
    # Strip ```json ... ``` fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back: extract first balanced {...} chunk
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[A-Za-z0-9]{3,}", s.lower()) if w not in STOPWORDS}


def balance_correct_positions(questions: list[dict]) -> None:
    """In-place: rearrange each question's options so the correct answers spread
    across positions [0,1,2,3] as evenly as possible. For n=7 that's {2,2,2,1};
    which slot gets the "1" is chosen uniformly at random. Distractors are also
    shuffled. Correct-index always rebuilt with options — they cannot desync."""
    n = len(questions)
    base, extra = divmod(n, 4)
    # `extra` slots get an extra correct (count = base+1); the rest get `base`.
    high_slots = random.sample(range(4), k=extra) if extra else []
    counts = [base + (1 if i in high_slots else 0) for i in range(4)]
    targets: list[int] = []
    for pos, cnt in enumerate(counts):
        targets.extend([pos] * cnt)
    random.shuffle(targets)

    for q, target in zip(questions, targets):
        correct_idx = int(q["correct"])
        correct_text = q["options"][correct_idx]
        distractors = [o for i, o in enumerate(q["options"]) if i != correct_idx]
        random.shuffle(distractors)
        new_options = list(distractors)
        new_options.insert(target, correct_text)
        q["options"] = new_options
        q["correct"] = target


def post_balance_assertions(questions: list[dict]) -> tuple[bool, str]:
    """Run AFTER balance_correct_positions. Returns (ok, reason)."""
    # Balanced positions — exactly one position has count (n%4) when n>0 and the
    # rest have count (n//4) or (n//4 + 1). For n=7: multiset is {2,2,2,1}.
    n = len(questions)
    expected_high = n // 4 + (1 if n % 4 else 0)
    expected_low = n // 4
    expected_high_count = n % 4 if n % 4 else 4
    expected_low_count = 4 - expected_high_count
    actual = Counter(int(q["correct"]) for q in questions)
    highs = sum(1 for v in actual.values() if v == expected_high)
    lows = sum(1 for v in actual.values() if v == expected_low)
    if highs != expected_high_count or lows != expected_low_count:
        return False, f"correct positions not balanced: {dict(actual)}"
    return True, "ok"


# Grounding-fail tolerance across the 7 questions of a quiz. Word-overlap
# grounding is a coarse heuristic — local 7B models occasionally write a
# tangentially related question (article mentions "Grand Slam" → asks about
# breakfast). One or two slips per quiz are fine; more than that is a sign
# the model genuinely lost the plot and we should retry.
GROUNDING_TOLERANCE = 2


def validate_single_question(q: dict, article: dict) -> tuple[bool, str, bool]:
    """Per-article question validator. Returns (ok, reason, was_ungrounded).
    `was_ungrounded` is True for soft word-overlap misses — the orchestrator
    counts these across the whole quiz against GROUNDING_TOLERANCE rather
    than hard-rejecting per question.

    Notes:
    - source_article_id is NOT checked here — the orchestrator attaches it
      after generation, so it cannot be wrong.
    - Uniqueness of source articles is structurally guaranteed (one call per
      article); no `seen_sids` check needed.
    - The 2-2 / option-not-in-explanation class is caught by the canonical
      substring check below."""
    if not isinstance(q, dict):
        return False, "not a dict", False
    question_text = q.get("question", "").strip()
    if len(question_text) < 10:
        return False, "question too short", False
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return False, "must have 4 options", False
    if len({o.strip().lower() for o in options if isinstance(o, str)}) != 4:
        return False, "options not distinct", False
    correct = q.get("correct")
    if not isinstance(correct, int) or not 0 <= correct < 4:
        return False, "correct index invalid", False
    explanation = q.get("explanation", "").strip()
    if not explanation or len(explanation) > 240:
        return False, "explanation length", False

    # Voice heuristic — banned phrases in question or explanation
    combined = (question_text + " " + explanation).lower()
    for banned in BANNED_PHRASES:
        if banned in combined:
            return False, f"banned phrase: {banned!r}", False

    # Dangling references — bare "the author/company/study/etc." phrases
    # the reader can't resolve without the source. Stem only; the explanation
    # can reasonably reference back to the article in some framings.
    m = _DANGLING_REFERENCE_RE.search(question_text)
    if m:
        return False, f"question contains dangling reference {m.group(0)!r} — name the entity", False

    correct_text = options[correct].strip()

    # Option/explanation integrity (canonical-form substring). Catches the
    # shipped "2-2 bug" and the $84.17m/$84.17-million class. See
    # canonical_value_form for what counts as equivalent.
    if canonical_value_form(correct_text) not in canonical_value_form(explanation):
        return False, f"correct option {correct_text!r} not present in explanation (canonical check)", False

    # Self-answering check. If the stem literally contains the correct
    # option's text, the question is circular ("Which of X's influences
    # included Eric Clapton?" → "Eric Clapton"). Match the FULL canonical
    # answer phrase as a substring of the canonical stem; skip for very
    # short answers (<3 chars) so we don't false-positive on single common
    # tokens. The full-phrase requirement means "Eric Clapton" matching
    # "...included Eric Clapton..." rejects, but a stem mentioning "Eric"
    # alone (when answer is "Eric Clapton") would NOT reject.
    correct_canon = canonical_value_form(correct_text)
    if len(correct_canon) >= 3 and correct_canon in canonical_value_form(question_text):
        return False, f"question stem contains the answer {correct_text!r} (self-answering)", False

    # Reject if any option contains a hex id (model leaked something it
    # shouldn't). Tightened to require ≥12 hex chars so we don't catch
    # legitimate short hex like "0xFF".
    aid = article.get("id", "")
    for o in options:
        if (aid and aid in o) or re.search(r"\b[a-f0-9]{12,}\b", o, re.IGNORECASE):
            return False, "option leaks article id or hex hash", False

    # Soft grounding signal — at least one content word from the correct
    # option must appear in the article title or Red facts. Soft because
    # entity names are sometimes the answer to an inferred question (e.g.
    # answer "Singapore" when article is about Hong Kong's ranking).
    source_text = " ".join([
        article.get("title", ""), article.get("_facts", ""),
    ]).lower()
    c_words = content_words(correct_text)
    was_ungrounded = bool(c_words) and not (c_words & content_words(source_text))
    if was_ungrounded:
        logger.warning(f"⚠️  Correct answer {correct_text!r} not word-grounded in source — tallied")

    return True, "ok", was_ungrounded


# ──────────────────────────────────────────────────────────────────────────────
# Generation
# ──────────────────────────────────────────────────────────────────────────────
def generate_question_for(article: dict, max_attempts: int = 4) -> tuple[dict | None, str | None]:
    """Single article → single validated question. Returns (q_dict, model_name)
    or (None, None) after max_attempts failures. The question dict has
    `was_ungrounded` attached so the orchestrator can apply the across-quiz
    GROUNDING_TOLERANCE check (we keep the question but tally the slip)."""
    schedules = [(1, 0.0), (2, 0.3), (3, 0.5), (4, 0.7)][:max_attempts]
    last_reason = ""
    last_model = None
    for attempt, temp in schedules:
        reminder = "" if attempt == 1 else (
            f"Your previous attempt failed validation with this exact error: {last_reason}\n\n"
            "Re-read the rules and fix exactly that issue. The most common "
            "failures are: (a) the QUESTION stem contained the correct "
            "answer's text (self-answering / circular — the user can't be "
            "asked to identify something the question already names); (b) "
            "the EXPLANATION did not contain the CORRECT option's text "
            "verbatim — fix this by repeating the option text in the "
            "explanation; (c) the answer was a generalization or definition "
            "not stated in the FACTS block — fix this by picking a specific "
            "stated fact (a number, date, name, place, or event) instead; "
            "(d) the question used a bare reference like 'the author' or "
            "'the company' that the reader cannot resolve — the reader has "
            "NOT read the article and must be able to answer from the "
            "question text alone, so NAME the specific person/company/place "
            "instead of writing 'the author' / 'the company' / 'the study'."
        )
        prompt = build_single_prompt(article, extra_reminder=reminder)
        logger.info(
            f"🧠 Article {article['id'][:8]}… attempt {attempt} (temp={temp}) "
            f"— prompt {len(prompt)} chars"
        )

        try:
            raw, duration, model = call_ollama_with_fallback(
                prompt,
                timeout=300,
                format_schema=QUIZ_QUESTION_SCHEMA,
                temperature=temp,
                models=QUIZ_MODELS,
            )
        except Exception as e:
            logger.error(f"🔥 Ollama call failed: {e}")
            last_reason = "Ollama call failed"
            continue
        last_model = model
        logger.info(f"  ↳ {model} in {duration:.0f}ms ({len(raw)} chars)")

        q = parse_strict_json(raw)
        if not q:
            last_reason = "model output was not valid JSON"
            logger.warning(f"  ⚠️  JSON parse failed")
            continue

        ok, reason, was_ungrounded = validate_single_question(q, article)
        if not ok:
            last_reason = reason
            logger.warning(f"  ⚠️  Validation failed: {reason}")
            continue

        q["was_ungrounded"] = was_ungrounded
        logger.info(f"  ✅ Question valid")
        return q, last_model

    logger.error(f"❌ Article {article['id'][:8]}… failed all {max_attempts} attempts")
    return None, last_model


def generate_quiz(candidates: list[dict]) -> tuple[dict | None, str | None]:
    """Per-article generation: one Ollama call per article, 4 attempts each.
    Returns (payload, model_used) or (None, None). dup-source is structurally
    impossible because each call sees only one article."""
    if len(candidates) < QUESTION_TARGET:
        logger.warning(f"⚠️  Only {len(candidates)} candidates — below {QUESTION_TARGET}")
        return None, None

    questions: list[dict] = []
    ungrounded_total = 0
    model_used = None
    for article in candidates:
        q, model = generate_question_for(article)
        if not q:
            logger.error(f"❌ Quiz aborted — could not generate question for {article['id']}")
            return None, None
        if q.pop("was_ungrounded", False):
            ungrounded_total += 1
        q["source_article_id"] = article["id"]   # attach post-hoc (always correct)
        questions.append(q)
        model_used = model or model_used

    if ungrounded_total > GROUNDING_TOLERANCE:
        logger.error(
            f"❌ Quiz aborted — {ungrounded_total}/{len(questions)} questions "
            f"ungrounded (>{GROUNDING_TOLERANCE} tolerance)"
        )
        return None, None

    # Re-arrange options so correct answers spread A/B/C/D in a balanced pattern.
    balance_correct_positions(questions)

    ok, reason = post_balance_assertions(questions)
    if not ok:
        logger.warning(f"⚠️  Post-balance check failed: {reason}")
        return None, None

    positions = Counter(int(q["correct"]) for q in questions)
    slots = " ".join(f"{chr(65+i)}={positions.get(i, 0)}" for i in range(4))
    logger.info(f"📊 Correct positions: {slots} | ungrounded tally: {ungrounded_total}")
    logger.info(f"✅ Quiz validated ({QUESTION_TARGET} Qs, per-article)")
    return {"questions": questions}, model_used


def hydrate_questions(questions: list[dict], candidates: list[dict]) -> list[dict]:
    """Attach source_title / source_url / id to each question for the frontend."""
    by_id = {c["id"]: c for c in candidates}
    out = []
    for i, q in enumerate(questions, 1):
        sid = q["source_article_id"]
        src = by_id.get(sid, {})
        out.append({
            "id": i,
            "question": q["question"].strip(),
            "options": [o.strip() for o in q["options"]],
            "correct": int(q["correct"]),
            "explanation": q["explanation"].strip(),
            "source_article_id": sid,
            "source_title": src.get("title", "") or "",
            "source_url": f"/article/{sid}",
            "source_name": src.get("source_name", "") or "",
        })
    return out


def generate_to_key(week_slug: str, target_key: str, candidates: list[dict]) -> bool:
    """Generate the quiz for `week_slug` using the provided `candidates` and
    write the validated payload to `target_key`. Returns True on success.
    Used by `maybe_generate_current` with `target_key` = staging key, so the
    live key is never touched until after validation succeeds.

    Candidates are passed in (rather than fetched here) so the caller can
    run the content-diff trigger off the same fetch — no double Redis scan."""
    payload, model_used = generate_quiz(candidates)
    if not payload:
        logger.error("❌ Generation failed after retries")
        return False

    now = datetime.now(timezone.utc)
    record = {
        "week": week_slug,
        "week_label": week_label(now),
        "generated_at": now.isoformat(),
        "model_used": model_used,
        "candidate_count": len(candidates),
        "questions": hydrate_questions(payload["questions"], candidates),
    }

    r.set(target_key, json.dumps(record))
    logger.info(f"💾 Wrote {target_key} ({len(record['questions'])} questions, model={model_used})")
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Main loop / CLI
# ──────────────────────────────────────────────────────────────────────────────
def maybe_generate_current(force: bool = False) -> bool:
    """Generate this ISO-week's quiz using a staging-key promote pattern: the
    new payload is written to `arc:quiz:staging:<slug>`, validated end-to-end,
    then atomically RENAMEd to the live `arc:quiz:<slug>` key on success. On
    failure, the live key is left untouched.

    Content-trigger: if a live quiz already exists and its 7 source articles
    match the current top-7 candidates exactly, the pool has not turned over
    since the last run — skip (no new stories to quiz on). The moment one
    article rotates in or out, the next cycle regenerates. `--force` bypasses
    the content check; the staging-key promote is the destructive-write
    safety, so it never destroys a live quiz on generation failure."""
    now = datetime.now(timezone.utc)
    week_slug = iso_week_slug(now)
    final_key = QUIZ_KEY_FMT.format(slug=week_slug)
    staging_key = STAGING_KEY_FMT.format(slug=week_slug)

    locked = r.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
    if not locked:
        logger.info("🔒 Another generator instance holds the lock — skipping")
        return False

    try:
        candidates = fetch_candidates()
        if len(candidates) < QUESTION_TARGET:
            logger.error(f"❌ Not enough substantive-Red candidates ({len(candidates)}) — need {QUESTION_TARGET}")
            return False

        # Content-trigger: compare the top-7 candidate IDs against the live
        # quiz's source IDs. Identical → no new content; skip. Different →
        # the pool turned over, regenerate.
        if not force:
            existing = r.get(final_key)
            if existing:
                try:
                    payload = json.loads(existing)
                    prior_ids = {q["source_article_id"] for q in payload.get("questions", [])}
                    current_ids = {c["id"] for c in candidates}
                    if prior_ids == current_ids:
                        logger.info(f"⏭️  {final_key} sources unchanged ({len(prior_ids)} articles) — skipping")
                        return False
                    rotated_in = current_ids - prior_ids
                    rotated_out = prior_ids - current_ids
                    logger.info(
                        f"🆕 Candidate pool turned over — {len(rotated_in)} in, "
                        f"{len(rotated_out)} out vs live quiz; regenerating"
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"⚠️  Could not parse existing {final_key}: {e} — regenerating")

        # Clean any stale staging from a prior failed run before writing fresh.
        r.delete(staging_key)

        ok = generate_to_key(week_slug, staging_key, candidates)
        if ok:
            # Lifetime quiz number. INCR is atomic — peers cannot race a
            # duplicate value here. Only happens when we are about to ship,
            # so content-trigger skips and failed generations never bump it.
            quiz_number = r.incr(COUNTER_KEY)
            # Stamp the assigned number into the staged payload so the live
            # key has it. The reload-edit-rewrite is on the local staging key,
            # not the live one, so readers never see the un-numbered form.
            payload = json.loads(r.get(staging_key))
            payload["quiz_number"] = quiz_number
            r.set(staging_key, json.dumps(payload))
            # Atomic swap: staging payload becomes the live week's quiz.
            r.rename(staging_key, final_key)
            r.set(CURRENT_KEY, week_slug)
            logger.info(f"💾 Promoted {staging_key} → {final_key} as Pop Quiz #{quiz_number}")
            return True

        # Failed generation: tidy staging, leave live key as-is.
        r.delete(staging_key)
        if r.exists(final_key):
            logger.warning(f"❌ Generation failed — {final_key} preserved (no destructive write)")
        else:
            logger.warning(f"❌ Generation failed — {final_key} stays empty")
        return False
    finally:
        r.delete(LOCK_KEY)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Generate once and exit (no loop)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if the week's quiz exists")
    args = parser.parse_args()

    if args.once:
        ok = maybe_generate_current(force=args.force)
        sys.exit(0 if ok else 1)

    startup_delay = random.randint(30, 120)
    logger.info(f"⏱️  Startup delay: {startup_delay}s")
    time.sleep(startup_delay)

    logger.info(f"🔁 Entering loop — CYCLE_MINUTES={CYCLE_MINUTES}")
    while True:
        try:
            maybe_generate_current()
        except Exception as e:
            logger.error(f"🔥 Cycle error: {e}", exc_info=True)
        logger.info(f"💤 Sleeping {CYCLE_MINUTES} minutes")
        for _ in range(CYCLE_MINUTES * 60):
            time.sleep(1)


if __name__ == "__main__":
    main()
