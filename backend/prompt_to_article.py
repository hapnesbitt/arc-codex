"""prompt_to_article.py — generate a publish-ready article from a user prompt.

Split out of scribe.py 2026-08-27 (scribe recon/cleanup — see
ops/RUNBOOK.md). Already pure — prompt text in, article text out — and its
one real dependency, call_ollama_local_only, was already a shared utility
(ollama_utils.py) rather than scribe.py's own, so this module needs nothing
from scribe.py at all.
"""

from __future__ import annotations

import logging

from ollama_utils import call_ollama_local_only

logger = logging.getLogger('scribe')


def generate_article_from_prompt(prompt_text: str) -> str | None:
    """
    Call Ollama to write a full article from a user-supplied prompt.
    Returns article text string, or None on failure.

    The system instruction keeps the output clean and publication-ready:
    no meta-commentary, no "here is your article", just the article itself.
    """
    system_instruction = (
        "You are a professional writer for Arc Codex, an intelligence and analysis platform. "
        "When given a writing prompt, produce a well-structured, publication-ready article. "
        "Write only the article itself — no preamble, no 'here is your article', no meta-commentary. "
        "Use clear prose, factual tone, and logical structure with an introduction, body, and conclusion."
    )

    full_prompt = f"{system_instruction}\n\nWriting prompt:\n{prompt_text}"

    try:
        logger.info(f"✍️  Generating article from prompt: '{prompt_text[:80]}...'")
        article_text, duration, model_used = call_ollama_local_only(full_prompt, timeout=900)
        logger.info(f"✍️  Article generated via {model_used} in {duration:.0f}ms ({len(article_text)} chars)")
        return article_text.strip()
    except Exception as e:
        logger.error(f"✍️  Prompt-to-article generation failed: {e}")
        return None
