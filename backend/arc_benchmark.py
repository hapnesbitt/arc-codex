#!/usr/bin/env python3
"""
arc_benchmark.py - A.R.C. News Analysis Model Benchmark v3.0

Tests Ollama models (local or cloud) for Arc Codex production readiness.
v3.0 adds labeled runs + persistent comparison file for side-by-side model eval.

Architecture mirrors The Construct:
  - 3 models do full independent A.R.C. analysis (Trinity / Architect / Oracle)
  - 1 model synthesizes into final think-tank conclusion (Case)

Tests:
  1. FACT EXTRACTION      - Clean who/what/when/where
  2. NARRATIVE SYNTHESIS  - Coherent executive summary
  3. CRITICAL ANALYSIS    - Manipulation patterns + bridge questions
  4. SYNTHESIS            - Combine 3 analyses into unified conclusion
  5. TRANSLATION          - Accuracy, completeness, register fidelity (optional)

v3.0 changes:
  - --label flag: tag each run by model name for comparison (e.g. "devstral-2", "qwen3.5")
  - --cloud-model flag: override CLOUD_MODEL without editing the file
  - Results APPEND to arc_benchmark_compare.json (not overwrite) — full history preserved
  - --compare flag: print side-by-side table from existing compare file, exit
  - --cloud runs skip ensemble selection (single model — no ensemble needed)
  - Credit burn estimate printed for cloud runs (based on task count × avg time)
  - Model under test shown in all output headers

v2.1 changes (preserved):
  - Auto-detects competing Ollama inference, stops scribe, waits for idle
  - Restarts scribe on exit via finally (even on crash or Ctrl+C)
  - Translation-only models auto-excluded from analysis
  - CJK length ratio scoring fixed (character-based, not word-based)
  - --skip-models flag to exclude known single-purpose models

Usage:
    # Compare three cloud models — run each in sequence:
    python3 arc_benchmark.py --cloud --cloud-model devstral-2:123b-cloud   --label devstral-2   --quick
    python3 arc_benchmark.py --cloud --cloud-model qwen3.5:122b-cloud      --label qwen3.5-122b --quick
    python3 arc_benchmark.py --cloud --cloud-model nemotron-3-super:120b-cloud --label nemotron-super --quick

    # Print comparison table from all labeled runs:
    python3 arc_benchmark.py --compare

    # Full run (all 3 articles):
    python3 arc_benchmark.py --cloud --cloud-model qwen3.5:122b-cloud --label qwen3.5-full

    # Local models:
    python3 arc_benchmark.py --local
    python3 arc_benchmark.py --models gemma3:4b llama3.2:latest

    # Translation:
    python3 arc_benchmark.py --translate --translate-langs Hindi French Telugu
"""

import json
import time
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

try:
    import requests
except ImportError:
    print("❌ pip install requests --break-system-packages")
    sys.exit(1)

# =============================================================================
# CONFIGURATION
# =============================================================================

M1_HOST      = "http://192.168.1.185:11434"
CLOUD_MODEL  = "devstral-2:123b-cloud"   # default — override with --cloud-model
ARC_SH       = "/home/www/arc_stack/arc.sh"

COMPARE_FILE = "arc_benchmark_compare.json"   # persistent cross-run comparison store

# Models known to be translation-only — excluded from analysis benchmark
TRANSLATION_ONLY_MODELS = ["translategemma", "translate-gemma"]

# Default translation languages
DEFAULT_TRANSLATE_LANGS = ["Hindi", "French", "Telugu", "Arabic", "Japanese"]

# CJK scripts — use character count for length ratio
CJK_LANGUAGES = {"Japanese", "Chinese", "Chinese (Simplified)", "Chinese (Traditional)",
                 "Korean", "Thai", "Burmese", "Khmer", "Lao"}

# =============================================================================
# TEST ARTICLES
# =============================================================================

TEST_ARTICLES = [
    {
        "id": "geopolitical_sanctions",
        "title": "EU Announces New Sanctions Package Targeting Tech Exports",
        "text": """The European Union announced its 15th sanctions package on Monday,
targeting semiconductor equipment exports to Russia and adding 47 entities to its
restricted list. The package, which took 3 months to negotiate among 27 member states,
includes restrictions on dual-use technology transfers and new financial reporting
requirements for European companies operating in third countries that may serve as
transshipment hubs.

EU foreign policy chief Kaja Kallas stated the measures are "designed to close
loopholes that have allowed circumvention through Central Asian intermediaries."
Industry groups including DigitalEurope and the European Semiconductor Industry
Association warned the restrictions could affect legitimate trade worth €2.3 billion
annually.

Russia's Foreign Ministry spokesperson Maria Zakharova called the sanctions
"another act of economic warfare that will backfire on European consumers" and
threatened retaliatory measures on agricultural imports. Meanwhile, Kazakhstan's
trade ministry issued a statement expressing concern about being "caught in the
crossfire" of sanctions enforcement.

Independent analysis by the Brussels-based Centre for European Policy Studies
suggests previous sanctions packages achieved approximately 30-40% reduction in
targeted trade flows, with significant variance by sector.""",
        "category": "threat_intelligence",
        "expected_facts": ["EU", "15th sanctions package", "semiconductor", "Russia",
                          "47 entities", "Kaja Kallas", "€2.3 billion", "Kazakhstan",
                          "30-40% reduction"],
        "manipulation_patterns": ["binary framing", "appeal to fear", "economic threat"],
    },
    {
        "id": "ai_regulation",
        "title": "Major AI Companies Announce Self-Regulation Framework",
        "text": """Six leading artificial intelligence companies including OpenAI,
Google DeepMind, and Anthropic jointly published a voluntary safety framework on
Tuesday, pledging to conduct independent safety testing before deploying models
above certain capability thresholds. The announcement came three days before a
Congressional hearing on AI oversight scheduled for Friday.

The framework, called the "Frontier Model Safety Protocol," commits signatories
to red-team testing, transparency reports, and a shared incident database. However,
the protocol contains no enforcement mechanism and relies entirely on voluntary
compliance. Companies retain full discretion over what constitutes a "dangerous
capability threshold."

Senator Maria Cantwell, chair of the Commerce Committee, described the initiative
as "a step in the right direction but no substitute for legislation." Consumer
advocacy group Public Citizen called it "a PR exercise designed to forestall
meaningful regulation."

Dr. Yoshua Bengio, a leading AI safety researcher, noted that "voluntary frameworks
have historically proven insufficient in other industries — from financial services
to social media — without regulatory backstops." The companies collectively spent
$47 million on lobbying in the previous quarter.""",
        "category": "tech_surveillance",
        "expected_facts": ["six companies", "OpenAI", "Google DeepMind", "Anthropic",
                          "Friday", "Frontier Model Safety Protocol", "Cantwell",
                          "$47 million lobbying"],
        "manipulation_patterns": ["self-regulation narrative", "timing manipulation",
                                  "voluntary compliance", "regulatory capture"],
    },
    {
        "id": "health_study",
        "title": "New Study Links Ultra-Processed Foods to Cognitive Decline",
        "text": """A longitudinal study published in The Lancet Neurology tracking
14,000 participants over 12 years found that individuals consuming more than 40%
of their daily calories from ultra-processed foods showed a 28% faster rate of
cognitive decline compared to those consuming less than 20%. The research was
conducted across 8 countries by a team led by Dr. Maria Fernandez at the
University of São Paulo.

The food industry's International Life Sciences Institute, which is funded by
Nestlé, PepsiCo, and other major food manufacturers, released a statement
questioning the methodology, arguing the study failed to adequately control for
socioeconomic factors and physical activity levels. They commissioned a rapid
counter-analysis by researchers at institutions that have received industry funding.

Dr. Fernandez responded that the study controlled for 23 confounding variables
including income, education, BMI, smoking, alcohol consumption, and physical
activity. She noted the results were consistent across all 8 countries studied.

The WHO has cited the study in its updated dietary guidelines draft, recommending
nations implement front-of-package warning labels on ultra-processed products.
Brazil and Chile already have such labels in place.""",
        "category": "science_health",
        "expected_facts": ["14,000 participants", "12 years", "28%", "Lancet Neurology",
                          "8 countries", "São Paulo", "WHO", "23 confounding variables"],
        "manipulation_patterns": ["industry-funded counter-research", "manufactured doubt",
                                  "appeal to methodology concerns"],
    },
]

TRANSLATION_SOURCE = """The European Union announced new sanctions targeting semiconductor exports.
EU foreign policy chief Kaja Kallas stated the measures are designed to close loopholes.
Industry groups warned the restrictions could affect legitimate trade worth €2.3 billion annually.
Russia's Foreign Ministry called the sanctions an act of economic warfare."""

# =============================================================================
# PROMPTS (unchanged from v2.1)
# =============================================================================

FACT_EXTRACTION_PROMPT = """You are a News Wire Editor. Extract and present ONLY verifiable core facts from this article.

INCLUDE: Who, What, When, Where — specific actors, actions, dates, locations.
EXCLUDE: Why, How, opinions, motivations, analysis.

OUTPUT: 8-12 bullet points of pure facts. Neutral, precise language only.

ARTICLE:
{article_text}

Respond with ONLY the factual bullet points. No headings, no commentary."""

NARRATIVE_SYNTHESIS_PROMPT = """You are an Editor-in-Chief. Provide a balanced, comprehensive summary for educated readers who need the full picture quickly.

APPROACH:
- Synthesize facts into coherent narrative
- Present multiple perspectives where they exist
- Acknowledge uncertainty explicitly
- Maintain strict journalistic neutrality

OUTPUT: 150-200 words in 2-3 well-constructed paragraphs.

ARTICLE:
{article_text}

Respond with ONLY the summary text. No headings, no meta-commentary."""

CRITICAL_ANALYSIS_PROMPT = """You are an A.R.C. Watchline Operator analyzing external news. Help readers develop cognitive resilience by recognizing patterns.

ANALYTICAL FRAMEWORK:
1. STEELMAN the narrative — what is the strongest version of this story?
2. SCAN for manipulation patterns — framing, omissions, emotional triggers
3. ROOT CAUSE — what paradigm or assumption drives this narrative?
4. IMPLICATIONS — what does this mean for human agency and power?
5. BRIDGE-BUILDING QUESTIONS — ask 2-3 questions that invite independent inquiry

VOICE: Combine intellectual rigor with humanist clarity. Principled skepticism, not cynicism.
Attack ideas, never people. Model thinking, not conclusions.

Red Team (Facts): The article contains factual claims about specific actors, numbers, and events.
Blue Team (Summary): The story presents a complex situation with multiple stakeholders and competing interests.

ARTICLE:
{article_text}

Respond with ONLY your analysis (200-300 words). No headings, labels, or meta-commentary. Do NOT list ARC codes explicitly."""

SYNTHESIS_PROMPT = """You are a Think Tank Director synthesizing three independent analyst perspectives into a single, authoritative conclusion.

Three analysts have independently analyzed the same article. Your task:

1. Identify where they AGREE — what is the consensus?
2. Identify where they DIVERGE — what does each see that others miss?
3. Synthesize into a UNIFIED conclusion that is stronger than any individual analysis
4. End with 2-3 questions for the reader that emerge from the combined analysis

ANALYST 1:
{analysis_1}

ANALYST 2:
{analysis_2}

ANALYST 3:
{analysis_3}

Write a 200-300 word synthesis. Be authoritative but intellectually honest.
No headings or labels. Just the synthesis."""

TRANSLATION_PROMPT = """Translate the following news excerpt into {language}.

Requirements:
- Accurate and complete translation
- Preserve proper nouns, numbers, and named entities exactly
- Maintain journalistic register (formal, neutral tone)
- Do not add explanation or commentary

TEXT TO TRANSLATE:
{text}

Respond with ONLY the translation. Nothing else."""

TRANSLATION_BACK_PROMPT = """Translate the following text back into English. Preserve all proper nouns, numbers, and named entities exactly.

TEXT:
{text}

Respond with ONLY the English translation. Nothing else."""

# =============================================================================
# OLLAMA CLIENT
# =============================================================================

def call_ollama(model: str, prompt: str, host: str, timeout: int = 120) -> Tuple[Optional[str], float, str]:
    """Call Ollama and return (response, elapsed_seconds, status)"""
    start = time.time()
    try:
        resp = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 4096}
            },
            timeout=timeout
        )
        elapsed = time.time() - start

        if resp.status_code != 200:
            return None, elapsed, f"http_{resp.status_code}"

        text = resp.json().get('message', {}).get('content', '').strip()
        return text, elapsed, "ok"

    except requests.exceptions.Timeout:
        return None, time.time() - start, "timeout"
    except Exception as e:
        return None, time.time() - start, f"error:{str(e)[:50]}"


def discover_local_models(host: str) -> List[str]:
    """Discover local (non-cloud) models via Ollama API"""
    try:
        resp = requests.get(f"{host}/api/tags", timeout=10)
        if resp.status_code != 200:
            return []
        models = [m['name'] for m in resp.json().get('models', [])
                  if m.get('size', 0) > 0
                  and 'cloud' not in m['name'].lower()]
        return sorted(set(models))
    except Exception as e:
        print(f"  ❌ Could not reach {host}: {e}")
        return []


def is_translation_only(model_name: str) -> bool:
    lower = model_name.lower()
    return any(tag in lower for tag in TRANSLATION_ONLY_MODELS)


def check_ollama_idle(host: str) -> bool:
    try:
        resp = requests.get(f"{host}/api/ps", timeout=5)
        return len(resp.json().get('models', [])) == 0
    except Exception:
        return True


def pause_scribe(host: str) -> bool:
    if check_ollama_idle(host):
        return False
    try:
        resp = requests.get(f"{host}/api/ps", timeout=5)
        running = [m['name'] for m in resp.json().get('models', [])]
        print(f"  ⚠️  Ollama busy: {running}")
    except Exception:
        pass
    print(f"  🛑 Stopping scribe to free inference capacity...")
    subprocess.run([ARC_SH, 'stop', 'scribe'], capture_output=True)
    print("  ⏳ Waiting for Ollama to go idle...", end=" ", flush=True)
    for _ in range(30):
        time.sleep(2)
        if check_ollama_idle(host):
            print("clear.")
            return True
    print("timeout — proceeding anyway.")
    return True


def resume_scribe():
    print("\n  🚀 Restarting scribe...")
    subprocess.run([ARC_SH, 'start', 'scribe'], capture_output=True)
    print("  ✅ scribe restarted")


# =============================================================================
# SCORING ENGINE (unchanged from v2.1)
# =============================================================================

def score_fact_extraction(response: str, article: Dict) -> Tuple[float, Dict]:
    if not response:
        return 0.0, {"reason": "no_response"}
    response_lower = response.lower()
    details = {}
    expected = article.get('expected_facts', [])
    found = sum(1 for fact in expected if fact.lower() in response_lower)
    coverage = found / max(len(expected), 1)
    details['fact_coverage'] = f"{found}/{len(expected)}"
    lines = [l.strip() for l in response.split('\n') if l.strip()]
    bullet_lines = sum(1 for l in lines if l.startswith(('-', '•', '*', '–')) or
                       (len(l) > 2 and l[0].isdigit() and l[1] in '.):'))
    structure_score = min(1.0, bullet_lines / 8)
    details['bullet_points'] = bullet_lines
    opinion_markers = ['suggests', 'implies', 'arguably', 'likely', 'appears to',
                       'in my view', 'it seems', 'probably', 'might indicate',
                       'this shows', 'clearly', 'obviously']
    opinion_count = sum(1 for m in opinion_markers if m in response_lower)
    neutrality = max(0.3, 1.0 - (opinion_count * 0.15))
    details['opinion_markers'] = opinion_count
    length_penalty = min(1.0, 1200 / max(len(response), 1)) if len(response) > 1200 else 1.0
    details['length'] = len(response)
    score = coverage * 0.45 + structure_score * 0.20 + neutrality * 0.20 + length_penalty * 0.15
    return round(score, 3), details


def score_narrative_synthesis(response: str, article: Dict) -> Tuple[float, Dict]:
    if not response:
        return 0.0, {"reason": "no_response"}
    response_lower = response.lower()
    details = {}
    expected = article.get('expected_facts', [])
    found = sum(1 for fact in expected if fact.lower() in response_lower)
    fact_score = min(1.0, found / max(len(expected) * 0.5, 1))
    details['key_facts'] = f"{found}/{len(expected)}"
    paragraphs = [p.strip() for p in response.split('\n\n') if p.strip() and len(p.strip()) > 50]
    structure_score = min(1.0, len(paragraphs) / 2)
    details['paragraphs'] = len(paragraphs)
    perspective_markers = ['however', 'meanwhile', 'in contrast', 'on the other hand',
                          'critics', 'opponents', 'supporters', 'while', 'although',
                          'some argue', 'others', 'alternatively', 'conversely']
    perspective_count = sum(1 for m in perspective_markers if m in response_lower)
    balance_score = min(1.0, perspective_count / 2)
    details['perspective_markers'] = perspective_count
    word_count = len(response.split())
    length_score = 1.0 if 130 <= word_count <= 250 else 0.7 if 100 <= word_count <= 350 else 0.4
    details['word_count'] = word_count
    score = fact_score * 0.30 + structure_score * 0.20 + balance_score * 0.25 + length_score * 0.25
    return round(score, 3), details


def score_critical_analysis(response: str, article: Dict) -> Tuple[float, Dict]:
    if not response:
        return 0.0, {"reason": "no_response"}
    response_lower = response.lower()
    details = {}
    steelman_markers = ['legitimate', 'valid', 'reasonable', 'understandable',
                       'credit', 'genuine concern', 'fair point', 'strongest',
                       'to be fair', 'rightly', 'important']
    steelman_count = sum(1 for m in steelman_markers if m in response_lower)
    steelman_score = min(1.0, steelman_count / 2)
    details['steelmanning'] = steelman_count
    pattern_markers = ['framing', 'narrative', 'pattern', 'assumption', 'omit',
                      'conspicuous', 'timing', 'whose interests', 'who benefits',
                      'unstated', 'presuppose', 'binary', 'false choice',
                      'manufactured', 'deflect', 'distract', 'lobby']
    pattern_count = sum(1 for m in pattern_markers if m in response_lower)
    pattern_score = min(1.0, pattern_count / 3)
    details['pattern_recognition'] = pattern_count
    question_count = response.count('?')
    question_score = min(1.0, question_count / 2)
    details['questions_asked'] = question_count
    cynical_markers = ['obviously corrupt', 'all lies', 'never trust', 'wake up',
                      'sheeple', 'propaganda machine']
    cynical_count = sum(1 for m in cynical_markers if m in response_lower)
    tone_score = max(0.3, 1.0 - (cynical_count * 0.3))
    details['cynicism_flags'] = cynical_count
    word_count = len(response.split())
    length_score = 1.0 if 180 <= word_count <= 350 else 0.7 if 120 <= word_count <= 450 else 0.4
    details['word_count'] = word_count
    score = (steelman_score * 0.20 + pattern_score * 0.30 +
             question_score * 0.20 + tone_score * 0.15 + length_score * 0.15)
    return round(score, 3), details


def score_synthesis(response: str) -> Tuple[float, Dict]:
    if not response:
        return 0.0, {"reason": "no_response"}
    response_lower = response.lower()
    details = {}
    agree_markers = ['agree', 'consensus', 'shared', 'common ground', 'converge',
                    'all three', 'each analyst', 'collectively', 'unified']
    agree_count = sum(1 for m in agree_markers if m in response_lower)
    details['agreement'] = agree_count
    diverge_markers = ['however', 'differs', 'contrast', 'whereas', 'unique',
                      'one analyst', 'distinct', 'diverge', 'disagree', 'tension',
                      'misses', 'overlooks', 'adds']
    diverge_count = sum(1 for m in diverge_markers if m in response_lower)
    details['divergence'] = diverge_count
    synthesis_markers = ['together', 'combined', 'synthesis', 'emerges', 'broader',
                        'deeper', 'underlying', 'reveals', 'when we consider',
                        'taken together', 'the fuller picture', 'collectively']
    synthesis_count = sum(1 for m in synthesis_markers if m in response_lower)
    details['synthesis_depth'] = synthesis_count
    question_count = response.count('?')
    details['questions'] = question_count
    word_count = len(response.split())
    length_score = 1.0 if 180 <= word_count <= 350 else 0.7 if 120 <= word_count <= 450 else 0.4
    details['word_count'] = word_count
    score = (min(1.0, agree_count / 2) * 0.20 +
             min(1.0, diverge_count / 2) * 0.20 +
             min(1.0, synthesis_count / 2) * 0.25 +
             min(1.0, question_count / 2) * 0.15 +
             length_score * 0.20)
    return round(score, 3), details


def score_translation(forward: str, back: str, language: str) -> Tuple[float, Dict]:
    details = {}
    if not forward:
        return 0.0, {"reason": "no_forward_translation"}
    source_words = set(TRANSLATION_SOURCE.lower().split())
    forward_words = set(forward.lower().split())
    overlap = len(source_words & forward_words) / max(len(source_words), 1)
    different_enough = overlap < 0.7
    details['source_overlap'] = round(overlap, 2)
    if language in CJK_LANGUAGES:
        source_len = len(TRANSLATION_SOURCE.replace(' ', ''))
        forward_len = len(forward.replace(' ', ''))
        length_ok = 0.25 <= (forward_len / max(source_len, 1)) <= 1.5
        details['length_metric'] = 'chars'
    else:
        source_len = len(TRANSLATION_SOURCE.split())
        forward_len = len(forward.split())
        length_ok = 0.4 <= (forward_len / max(source_len, 1)) <= 2.5
        details['length_metric'] = 'words'
    length_ratio = forward_len / max(source_len, 1)
    details['length_ratio'] = round(length_ratio, 2)
    details['forward_words'] = forward_len
    key_entities = ["EU", "Kallas", "Russia", "Kazakhstan", "2.3 billion",
                    "semiconductor", "Zakharova"]
    if not back:
        rt_score = 0.0
        details['round_trip'] = "no_back_translation"
    else:
        back_lower = back.lower()
        found = sum(1 for e in key_entities if e.lower() in back_lower)
        rt_score = found / len(key_entities)
        details['round_trip'] = f"{found}/{len(key_entities)} entities"
    refusal_markers = ["i cannot", "i'm unable", "i don't", "sorry", "i apologize",
                       "cannot translate", "unable to translate"]
    refused = any(m in forward.lower() for m in refusal_markers)
    if refused:
        details['refused'] = True
        return 0.0, details
    score = (
        (0.5 if different_enough else 0.1) * 0.25 +
        (1.0 if length_ok else 0.3) * 0.25 +
        rt_score * 0.50
    )
    return round(score, 3), details


# =============================================================================
# MOCK ANALYSES (for synthesis benchmark)
# =============================================================================

MOCK_ANALYSES = {
    "geopolitical_sanctions": [
        "The EU's 15th sanctions package reveals the inherent tension between economic warfare and diplomatic compromise. While targeting semiconductor exports addresses a genuine strategic vulnerability, the 3-month negotiation period suggests deep divisions among member states. The €2.3 billion trade impact warning from industry groups is significant but must be weighed against the 30-40% effectiveness rate of previous packages. Kazakhstan's 'crossfire' complaint points to unintended consequences on neutral parties.",
        "This sanctions escalation follows a predictable pattern of action-reaction cycles. The timing and scope suggest more political signaling than economic strategy. Russia's retaliatory threats on agricultural imports target EU constituencies directly, creating domestic political pressure against future sanctions. The real story may be the transshipment networks through Central Asia that have been undermining sanctions effectiveness all along.",
        "What stands out is the information gap: we know the EU claims these sanctions will close loopholes, but we have no independent verification mechanism. The 30-40% effectiveness figure from CEPS deserves scrutiny — does this represent success or failure? And who bears the costs: European companies, Russian citizens, or Central Asian intermediaries?",
    ],
    "ai_regulation": [
        "The voluntary safety framework represents the tech industry's preferred alternative to binding regulation. The timing — three days before Congressional hearings — is strategically significant. The $47 million lobbying spend provides essential context for interpreting this initiative. The absence of enforcement mechanisms is the critical weakness that Senator Cantwell correctly identifies.",
        "Self-regulation in technology has a poor track record. The 'Frontier Model Safety Protocol' name itself is revealing — it frames the companies as responsible stewards while preserving their autonomy. The real question is whether voluntary commitments create just enough political cover to prevent meaningful legislation.",
        "There's a democratic accountability gap here. Six private companies are effectively proposing to self-certify the safety of technologies that affect billions of people. The framework's reliance on company discretion for 'dangerous capability thresholds' means the entities with the strongest financial incentive to deploy are also the ones defining what's dangerous.",
    ],
    "health_study": [
        "The Lancet study's scale — 14,000 participants, 12 years, 8 countries — gives it significant statistical power. The 28% faster cognitive decline finding is substantial. The industry response through ILSI follows the established playbook of manufactured doubt, as seen with tobacco, sugar, and climate research.",
        "The methodological critique from industry-funded researchers is predictable but not automatically wrong. Dr. Fernandez's response about controlling for 23 variables is reassuring. The WHO's rapid adoption into dietary guidelines suggests the scientific consensus is moving decisively.",
        "The power dynamics are clear: a public health finding threatens industry profits, and the response follows established patterns of doubt manufacturing. The study's multi-country consistency makes it harder to dismiss, but the food industry has deep resources for sustained counter-messaging.",
    ],
}


# =============================================================================
# BENCHMARK RUNNERS
# =============================================================================

def benchmark_model(model: str, articles: List[Dict], host: str, quick: bool = False) -> Dict:
    """Run A.R.C. analysis benchmark on a single model"""
    print(f"\n{'='*65}")
    print(f"  🔬 Benchmarking: {model}")
    print(f"{'='*65}")

    results = {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "tests": defaultdict(list),
        "scores": {},
        "total_time": 0.0,
        "status": "unknown",
    }

    test_articles = articles[:1] if quick else articles
    total_tests = len(test_articles) * 3
    test_num = 0

    for article in test_articles:
        aid = article['id']
        print(f"\n  📰 {article['title'][:58]}...")

        # Fact extraction
        test_num += 1
        print(f"    [{test_num}/{total_tests}] Fact Extraction...", end=" ", flush=True)
        response, elapsed, status = call_ollama(
            model, FACT_EXTRACTION_PROMPT.format(article_text=article['text']), host)
        results['total_time'] += elapsed
        if response:
            score, details = score_fact_extraction(response, article)
            print(f"{'✅' if score > 0.6 else '⚠️' if score > 0.35 else '❌'} "
                  f"{score:.2f} ({elapsed:.1f}s) facts={details.get('fact_coverage')}")
        else:
            score, details = 0.0, {"reason": status}
            print(f"❌ FAILED ({status})")
        results['tests']['fact_extraction'].append({
            "article": aid, "score": score, "time": round(elapsed, 2), "details": details,
            "response_preview": (response or "")[:200]
        })

        # Narrative synthesis
        test_num += 1
        print(f"    [{test_num}/{total_tests}] Narrative Synthesis...", end=" ", flush=True)
        response, elapsed, status = call_ollama(
            model, NARRATIVE_SYNTHESIS_PROMPT.format(article_text=article['text']), host)
        results['total_time'] += elapsed
        if response:
            score, details = score_narrative_synthesis(response, article)
            print(f"{'✅' if score > 0.6 else '⚠️' if score > 0.35 else '❌'} "
                  f"{score:.2f} ({elapsed:.1f}s) words={details.get('word_count')}")
        else:
            score, details = 0.0, {"reason": status}
            print(f"❌ FAILED ({status})")
        results['tests']['narrative_synthesis'].append({
            "article": aid, "score": score, "time": round(elapsed, 2), "details": details,
            "response_preview": (response or "")[:200]
        })

        # Critical analysis
        test_num += 1
        print(f"    [{test_num}/{total_tests}] Critical Analysis...", end=" ", flush=True)
        response, elapsed, status = call_ollama(
            model, CRITICAL_ANALYSIS_PROMPT.format(article_text=article['text']), host)
        results['total_time'] += elapsed
        if response:
            score, details = score_critical_analysis(response, article)
            print(f"{'✅' if score > 0.6 else '⚠️' if score > 0.35 else '❌'} "
                  f"{score:.2f} ({elapsed:.1f}s) patterns={details.get('pattern_recognition')}")
        else:
            score, details = 0.0, {"reason": status}
            print(f"❌ FAILED ({status})")
        results['tests']['critical_analysis'].append({
            "article": aid, "score": score, "time": round(elapsed, 2), "details": details,
            "response_preview": (response or "")[:200]
        })

    for dim in ['fact_extraction', 'narrative_synthesis', 'critical_analysis']:
        scores = [t['score'] for t in results['tests'][dim]]
        times  = [t['time']  for t in results['tests'][dim]]
        results['scores'][dim] = {
            "avg_score": round(sum(scores) / max(len(scores), 1), 3),
            "avg_time":  round(sum(times)  / max(len(times),  1), 2),
        }

    fact_avg = results['scores']['fact_extraction']['avg_score']
    narr_avg = results['scores']['narrative_synthesis']['avg_score']
    crit_avg = results['scores']['critical_analysis']['avg_score']

    results['scores']['analysis_composite'] = round(
        fact_avg * 0.25 + narr_avg * 0.35 + crit_avg * 0.40, 3)
    results['scores']['avg_time_per_task'] = round(
        results['total_time'] / max(test_num, 1), 2)
    results['scores']['efficiency'] = round(
        results['scores']['analysis_composite'] / max(results['scores']['avg_time_per_task'], 0.1), 4)

    composite = results['scores']['analysis_composite']
    results['status'] = ('excellent' if composite > 0.65 else
                         'good'      if composite > 0.45 else
                         'fair'      if composite > 0.30 else 'poor')

    print(f"\n  {'─'*60}")
    print(f"  📊 {model} — {results['status'].upper()}")
    print(f"     Fact Extraction:     {fact_avg:.2f}")
    print(f"     Narrative Synthesis: {narr_avg:.2f}")
    print(f"     Critical Analysis:   {crit_avg:.2f}")
    print(f"     ─────────────────────────")
    print(f"     COMPOSITE:           {composite:.2f}")
    print(f"     Avg Time/Task:       {results['scores']['avg_time_per_task']:.1f}s")
    print(f"     Efficiency:          {results['scores']['efficiency']:.4f}")

    return results


def run_synthesis_benchmark(models: List[str], articles: List[Dict], host: str) -> Dict:
    """Test each model's synthesis capability"""
    print(f"\n{'='*65}")
    print(f"  🧬 SYNTHESIS BENCHMARK")
    print(f"{'='*65}")

    article = articles[0]
    aid = article['id']
    analyses = MOCK_ANALYSES[aid]

    synthesis_results = {}
    for model in models:
        print(f"\n  🔬 Testing synthesis: {model}")
        prompt = SYNTHESIS_PROMPT.format(
            analysis_1=analyses[0], analysis_2=analyses[1], analysis_3=analyses[2])
        response, elapsed, status = call_ollama(model, prompt, host, timeout=180)

        if response:
            score, details = score_synthesis(response)
            print(f"     {'✅' if score > 0.6 else '⚠️' if score > 0.35 else '❌'} "
                  f"Score: {score:.2f} ({elapsed:.1f}s) | "
                  f"agree={details.get('agreement',0)} diverge={details.get('divergence',0)} "
                  f"synth={details.get('synthesis_depth',0)} Q={details.get('questions',0)}")
            synthesis_results[model] = {
                "score": score, "time": round(elapsed, 2),
                "details": details, "response_preview": response[:300]
            }
        else:
            print(f"     ❌ FAILED ({status})")
            synthesis_results[model] = {"score": 0.0, "time": round(elapsed, 2),
                                        "details": {"reason": status}}
    return synthesis_results


def run_translation_benchmark(models: List[str], languages: List[str], host: str) -> Dict:
    print(f"\n{'='*65}")
    print(f"  🌐 TRANSLATION BENCHMARK")
    print(f"  Languages: {', '.join(languages)}")
    print(f"{'='*65}")

    translation_results = {}

    for model in models:
        print(f"\n  🔬 Testing translation: {model}")
        translation_results[model] = {}

        for lang in languages:
            print(f"    → {lang}...", end=" ", flush=True)
            fwd_prompt = TRANSLATION_PROMPT.format(language=lang, text=TRANSLATION_SOURCE)
            forward, fwd_elapsed, fwd_status = call_ollama(model, fwd_prompt, host, timeout=120)

            if not forward:
                print(f"❌ forward failed ({fwd_status})")
                translation_results[model][lang] = {
                    "score": 0.0, "status": fwd_status,
                    "forward_time": round(fwd_elapsed, 2)
                }
                continue

            back_prompt = TRANSLATION_BACK_PROMPT.format(text=forward)
            back, back_elapsed, back_status = call_ollama(model, back_prompt, host, timeout=120)

            score, details = score_translation(forward, back or "", lang)
            total_time = round(fwd_elapsed + back_elapsed, 2)

            emoji = "✅" if score > 0.65 else "⚠️" if score > 0.40 else "❌"
            print(f"{emoji} {score:.2f} ({total_time:.1f}s) "
                  f"rt={details.get('round_trip','?')} ratio={details.get('length_ratio','?')}")

            translation_results[model][lang] = {
                "score": score,
                "forward_time": round(fwd_elapsed, 2),
                "back_time": round(back_elapsed, 2),
                "total_time": total_time,
                "details": details,
                "forward_preview": forward[:200],
                "back_preview": (back or "")[:200],
            }

        lang_scores = [v['score'] for v in translation_results[model].values()
                       if isinstance(v, dict) and 'score' in v]
        avg = sum(lang_scores) / max(len(lang_scores), 1)
        print(f"\n    Translation avg: {avg:.2f} across {len(lang_scores)} languages")
        translation_results[model]['_avg'] = round(avg, 3)

    return translation_results


# =============================================================================
# COMPARISON FILE — persistent cross-run storage
# =============================================================================

def load_compare_file(path: str) -> Dict:
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"runs": []}


def save_compare_file(data: Dict, path: str) -> None:
    Path(path).write_text(json.dumps(data, indent=2, default=str))


def append_run(label: str, model: str, result: Dict,
               synthesis_score: float, articles_count: int,
               quick: bool, compare_path: str) -> None:
    """Append a labeled run summary to the comparison file."""
    data = load_compare_file(compare_path)
    scores = result.get('scores', {})
    entry = {
        "label":       label,
        "model":       model,
        "run_at":      datetime.now().isoformat(),
        "quick_mode":  quick,
        "articles":    articles_count,
        "composite":   scores.get('analysis_composite', 0),
        "fact":        scores.get('fact_extraction', {}).get('avg_score', 0),
        "narrative":   scores.get('narrative_synthesis', {}).get('avg_score', 0),
        "critical":    scores.get('critical_analysis', {}).get('avg_score', 0),
        "synthesis":   synthesis_score,
        "avg_time_s":  scores.get('avg_time_per_task', 0),
        "efficiency":  scores.get('efficiency', 0),
        "status":      result.get('status', ''),
    }
    # Replace existing entry with same label, or append
    runs = data.get('runs', [])
    replaced = False
    for i, r in enumerate(runs):
        if r.get('label') == label:
            runs[i] = entry
            replaced = True
            break
    if not replaced:
        runs.append(entry)
    data['runs'] = runs
    save_compare_file(data, compare_path)
    action = "Updated" if replaced else "Appended"
    print(f"\n  💾 {action} '{label}' in {compare_path}")


def print_comparison_table(compare_path: str) -> None:
    """Print side-by-side comparison of all labeled runs."""
    data = load_compare_file(compare_path)
    runs = data.get('runs', [])
    if not runs:
        print(f"  No runs found in {compare_path}")
        return

    print(f"\n{'='*80}")
    print(f"  📊 A.R.C. CLOUD MODEL COMPARISON — {len(runs)} run(s)")
    print(f"{'='*80}")

    # Header
    print(f"\n  {'Label':<22} {'Model':<28} {'Comp':>6} {'Fact':>6} {'Narr':>6} "
          f"{'Crit':>6} {'Synth':>6} {'Time':>6} {'Eff':>7}  {'Q':<5} {'Art'}")
    print(f"  {'─'*22} {'─'*28} {'─'*6} {'─'*6} {'─'*6} "
          f"{'─'*6} {'─'*6} {'─'*6} {'─'*7}  {'─'*5} {'─'*3}")

    # Sort by composite descending
    for r in sorted(runs, key=lambda x: x.get('composite', 0), reverse=True):
        label    = r.get('label', '')[:22]
        model    = r.get('model', '')[:28]
        comp     = r.get('composite', 0)
        fact     = r.get('fact', 0)
        narr     = r.get('narrative', 0)
        crit     = r.get('critical', 0)
        synth    = r.get('synthesis', 0)
        avg_time = r.get('avg_time_s', 0)
        eff      = r.get('efficiency', 0)
        quick    = "⚡" if r.get('quick_mode') else "  "
        arts     = r.get('articles', '?')
        medal    = "🥇" if comp == max(x.get('composite',0) for x in runs) else "  "
        print(f"  {medal}{label:<21} {model:<28} {comp:>6.3f} {fact:>6.2f} {narr:>6.2f} "
              f"{crit:>6.2f} {synth:>6.2f} {avg_time:>5.1f}s {eff:>7.4f}  {quick}    {arts}")

    print(f"\n  ⚡ = quick mode (1 article)  |  Efficiency = composite / avg_time")

    # Winner call
    best = max(runs, key=lambda x: x.get('composite', 0))
    print(f"\n  🏆 Best composite: {best['label']} ({best['model']}) — {best['composite']:.3f}")

    fastest = min(runs, key=lambda x: x.get('avg_time_s', 999))
    print(f"  ⚡ Fastest:        {fastest['label']} ({fastest['model']}) — {fastest['avg_time_s']:.1f}s/task")

    best_eff = max(runs, key=lambda x: x.get('efficiency', 0))
    print(f"  💡 Best efficiency:{best_eff['label']} ({best_eff['model']}) — {best_eff['efficiency']:.4f}")
    print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="A.R.C. News Analysis Model Benchmark v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Compare cloud models (run each, then compare):
  python3 arc_benchmark.py --cloud --cloud-model devstral-2:123b-cloud    --label devstral-2    --quick
  python3 arc_benchmark.py --cloud --cloud-model qwen3.5:122b-cloud       --label qwen3.5-122b  --quick
  python3 arc_benchmark.py --cloud --cloud-model nemotron-3-super:120b-cloud --label nemotron-super --quick
  python3 arc_benchmark.py --compare

  # Full run after picking a winner:
  python3 arc_benchmark.py --cloud --cloud-model qwen3.5:122b-cloud --label qwen3.5-full

  # Local models:
  python3 arc_benchmark.py --local
  python3 arc_benchmark.py --models gemma3:4b llama3.2:latest

  # Translation:
  python3 arc_benchmark.py --translate --translate-langs Hindi French Telugu
"""
    )
    parser.add_argument('--local',        action='store_true', help='Test all local models (default)')
    parser.add_argument('--cloud',        action='store_true', help='Test cloud model only')
    parser.add_argument('--cloud-model',  default=None,
                        help=f'Cloud model to test (default: {CLOUD_MODEL})')
    parser.add_argument('--models',       nargs='+',           help='Test specific model(s) by name')
    parser.add_argument('--label',        default=None,
                        help='Label for this run in comparison file (e.g. "devstral-2", "qwen3.5")')
    parser.add_argument('--quick',        action='store_true', help='Quick mode (1 article only)')
    parser.add_argument('--compare',      action='store_true',
                        help='Print comparison table from saved runs and exit')
    parser.add_argument('--translate',       action='store_true', help='Run translation benchmark')
    parser.add_argument('--translate-langs', nargs='+',  metavar='LANG',
                        default=DEFAULT_TRANSLATE_LANGS,
                        help=f'Languages to test (default: {" ".join(DEFAULT_TRANSLATE_LANGS)})')
    parser.add_argument('--translate-only',  action='store_true',
                        help='Skip analysis benchmark, run translation only')
    parser.add_argument('--host',         default=M1_HOST,
                        help=f'Ollama host (default: {M1_HOST})')
    parser.add_argument('--skip-models',  nargs='+', metavar='MODEL', default=[],
                        help='Model name fragments to exclude (e.g. translategemma)')
    parser.add_argument('--no-scribe-mgmt', action='store_true',
                        help='Skip automatic scribe stop/start')
    parser.add_argument('--compare-file', default=COMPARE_FILE,
                        help=f'Comparison file path (default: {COMPARE_FILE})')
    parser.add_argument('--output',       default=None,
                        help='Per-run output JSON (default: arc_benchmark_<label>.json or arc_benchmark_results.json)')
    args = parser.parse_args()

    # --compare: just print table and exit
    if args.compare:
        print_comparison_table(args.compare_file)
        return

    # Resolve cloud model
    cloud_model = args.cloud_model or CLOUD_MODEL

    # Auto-label from cloud model name if not provided
    label = args.label
    if label is None and args.cloud:
        label = cloud_model.replace(":123b-cloud", "").replace(":122b-cloud", "").replace("-cloud", "").replace(":", "-")
    elif label is None:
        label = None  # won't be saved to compare file unless labeled

    host = args.host

    print("=" * 65)
    print("  🎯 A.R.C. News Analysis Model Benchmark v3.0")
    print(f"  Host: {host}")
    if label:
        print(f"  Label: {label}")
    print("=" * 65)
    print()

    # Resolve model list
    if args.models:
        models = args.models
        print(f"  📋 Testing specified: {', '.join(models)}")
    elif args.cloud:
        models = [cloud_model]
        print(f"  ☁️  Cloud model: {cloud_model}")
    else:
        print(f"  📡 Discovering local models at {host}...")
        models = discover_local_models(host)
        if not models:
            print(f"  ❌ No local models found at {host}")
            print(f"     Run: curl {host}/api/tags")
            sys.exit(1)
        print(f"  Found {len(models)}: {', '.join(models)}")

    # Apply skip list
    skip_fragments = [s.lower() for s in args.skip_models] + TRANSLATION_ONLY_MODELS
    if skip_fragments and not args.translate_only:
        before = len(models)
        analysis_models = [m for m in models
                           if not any(f in m.lower() for f in skip_fragments)]
        skipped = [m for m in models if m not in analysis_models]
        if skipped:
            print(f"  ⏭️  Skipping (translation-only): {', '.join(skipped)}")
        models = analysis_models

    if not models:
        print("  ❌ No models remain after filtering!")
        sys.exit(1)

    if args.quick:
        print("  ⚡ QUICK MODE — 1 article per model")
    print()

    # Scribe management
    scribe_was_stopped = False
    if not args.no_scribe_mgmt and not args.cloud:
        scribe_was_stopped = pause_scribe(host)

    output_file = args.output or (
        f"arc_benchmark_{label}.json" if label else "arc_benchmark_results.json")

    output = {
        "generated_at": datetime.now().isoformat(),
        "version": "3.0 - A.R.C. News Analysis Benchmark",
        "label": label,
        "host": host,
        "models_tested": len(models),
        "quick_mode": args.quick,
    }

    # Analysis benchmark
    if not args.translate_only:
        print("  Tests: Fact Extraction → Narrative Synthesis → Critical Analysis → Synthesis")
        print()

        all_results = []
        for i, model in enumerate(models, 1):
            print(f"\n  [{i}/{len(models)}]", end="")
            try:
                result = benchmark_model(model, TEST_ARTICLES, host, quick=args.quick)
                all_results.append(result)
            except KeyboardInterrupt:
                print("\n\n  ⚠️  Interrupted — processing results so far...")
                break
            except Exception as e:
                print(f"\n  ❌ {model} failed: {e}")
                continue

        if not all_results:
            print("  ❌ No successful analysis tests!")
            sys.exit(1)

        # Synthesis benchmark (skip for single cloud model runs to save credits)
        synthesis_results = {}
        if len(all_results) > 1 or not args.cloud:
            synthesis_results = run_synthesis_benchmark(
                [r['model'] for r in all_results], TEST_ARTICLES, host)
        else:
            # Single cloud model: run synthesis once
            model = all_results[0]['model']
            print(f"\n  🧬 Single-model synthesis test: {model}")
            article = TEST_ARTICLES[0]
            analyses = MOCK_ANALYSES[article['id']]
            prompt = SYNTHESIS_PROMPT.format(
                analysis_1=analyses[0], analysis_2=analyses[1], analysis_3=analyses[2])
            response, elapsed, status = call_ollama(model, prompt, host, timeout=180)
            if response:
                score, details = score_synthesis(response)
                print(f"     {'✅' if score > 0.6 else '⚠️'} Score: {score:.2f} ({elapsed:.1f}s)")
                synthesis_results[model] = {"score": score, "time": round(elapsed, 2), "details": details}
            else:
                print(f"     ❌ FAILED ({status})")
                synthesis_results[model] = {"score": 0.0, "time": 0}

        # Print rankings
        print(f"\n{'='*65}")
        print(f"  ✅ ANALYSIS COMPLETE{' — ' + label if label else ''}")
        print(f"{'='*65}")
        print(f"\n  📊 Rankings:")
        print(f"  {'Model':<30} {'Comp':>6} {'Facts':>6} {'Narr':>6} {'Crit':>6} {'Synth':>6} {'Time':>6} {'Eff':>8}")
        print(f"  {'─'*30} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*8}")

        ranked = sorted(all_results, key=lambda x: x['scores']['analysis_composite'], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        full_rankings = []
        for i, r in enumerate(ranked):
            m = medals[i] if i < 3 else "  "
            synth_score = synthesis_results.get(r['model'], {}).get('score', 0)
            eff = r['scores']['efficiency']
            print(f"  {m}{r['model']:<28} {r['scores']['analysis_composite']:>6.3f} "
                  f"{r['scores']['fact_extraction']['avg_score']:>6.2f} "
                  f"{r['scores']['narrative_synthesis']['avg_score']:>6.2f} "
                  f"{r['scores']['critical_analysis']['avg_score']:>6.2f} "
                  f"{synth_score:>6.2f} {r['scores']['avg_time_per_task']:>5.1f}s {eff:>8.4f}")
            full_rankings.append({
                "model":          r['model'],
                "composite":      r['scores']['analysis_composite'],
                "fact_extraction": r['scores']['fact_extraction']['avg_score'],
                "narrative":      r['scores']['narrative_synthesis']['avg_score'],
                "critical":       r['scores']['critical_analysis']['avg_score'],
                "synthesis":      synth_score,
                "avg_time":       r['scores']['avg_time_per_task'],
                "efficiency":     eff,
                "status":         r['status'],
            })

        # Credit burn estimate for cloud runs
        if args.cloud:
            total_tasks = len(TEST_ARTICLES if not args.quick else TEST_ARTICLES[:1]) * 3 + 1
            total_time_s = sum(r['scores']['avg_time_per_task'] * (
                len(TEST_ARTICLES) if not args.quick else 1) * 3
                for r in all_results)
            print(f"\n  ⏱️  Total inference time: {total_time_s:.0f}s "
                  f"({total_tasks} tasks @ ~{total_time_s/max(total_tasks,1):.0f}s avg)")
            print(f"  💡 Full run (3 articles) would take ~{total_time_s * (3 if args.quick else 1):.0f}s")

        output.update({
            "articles_used":   1 if args.quick else len(TEST_ARTICLES),
            "full_rankings":   full_rankings,
            "detailed_results": all_results,
            "synthesis_results": {
                m: {"score": d.get('score', 0), "time": d.get('time', 0)}
                for m, d in synthesis_results.items()
            },
        })

        # Save to compare file if labeled
        if label and len(all_results) == 1:
            synth_score = synthesis_results.get(all_results[0]['model'], {}).get('score', 0)
            append_run(
                label=label,
                model=all_results[0]['model'],
                result=all_results[0],
                synthesis_score=synth_score,
                articles_count=1 if args.quick else len(TEST_ARTICLES),
                quick=args.quick,
                compare_path=args.compare_file,
            )
            print_comparison_table(args.compare_file)

    # Translation benchmark
    if args.translate or args.translate_only:
        trans_models = args.models if args.models else (
            [cloud_model] if args.cloud else discover_local_models(host))
        explicit_skip = [s.lower() for s in args.skip_models]
        if explicit_skip:
            trans_models = [m for m in trans_models
                            if not any(f in m.lower() for f in explicit_skip)]
        translation_results = run_translation_benchmark(
            trans_models, args.translate_langs, host)
        output['translation_results'] = translation_results

    # Save per-run output
    output_path = Path(output_file)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  💾 Run results saved to: {output_path}")


def _run():
    """Entry point with guaranteed scribe restart via finally."""
    scribe_needs_restart = [False]

    original_pause = pause_scribe
    def tracked_pause(host):
        result = original_pause(host)
        scribe_needs_restart[0] = result
        return result

    globals()['pause_scribe'] = tracked_pause

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  ⚠️  Interrupted by user")
    finally:
        if scribe_needs_restart[0]:
            resume_scribe()


if __name__ == '__main__':
    _run()
