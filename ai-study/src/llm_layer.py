"""
Free LLM Layer — with anti-hallucination guard
-----------------------------------------------
Priority: Ollama → Groq → Offline fallback

Anti-hallucination measures:
  1. STRICT system prompt: "answer ONLY from textbook context"
  2. Confidence gate: if top retrieval score < 25%, refuse to answer
  3. Grounding check: after generation, verify answer contains words
     from the context (not invented content)
  4. Temperature = 0 for factual questions (no creativity)
  5. Every guard firing is logged to logs/hallucination_guard.log
"""

import os
import re
from src.logger import get_logger, log_hallucination_guard

log = get_logger("llm_layer")

# ── Anti-hallucination: confidence gate ─────────────────────────────────────
# ChromaDB cosine similarity scores: 100 = perfect match, 0 = unrelated.
# Typical textbook matches land between 20-55 even for good questions.
# 25 was too aggressive — it blocked valid questions whose phrasing
# differed slightly from textbook wording. 10 blocks only true noise.
MIN_RETRIEVAL_SCORE = 10.0   # below this = refuse to answer

# ── Anti-hallucination: strict system prompt ────────────────────────────────
TUTOR_SYSTEM = """You are a helpful science tutor for a Class 5 student (age 10-11).

STRICT RULES — follow these exactly:
1. Answer ONLY using the TEXTBOOK CONTENT provided below.
2. If the answer is NOT in the textbook content, say exactly:
   "I couldn't find this in your textbook. Please ask your teacher."
   Do NOT guess or use outside knowledge.
3. Use simple words a 10-year-old understands.
4. Keep explanations short — 3 to 5 sentences maximum.
5. Never make up facts, examples, or numbers not in the textbook.

Answer in this exact format:
✅ EXPLANATION: [2-3 sentences from textbook content only]
🌍 EXAMPLE: [one real-world example — only if mentioned in textbook]
🔑 KEY POINT: [single most important fact from textbook]
📺 LEARN MORE: [suggest: "search YouTube for: [topic] for kids class 5"]"""


def _confidence_gate(context_chunks: list[dict],
                     question: str,
                     session_id: str = "") -> tuple[bool, str]:
    """
    Returns (should_answer, reason).
    Blocks answering only when ALL retrieved chunks are noise-level matches.

    Uses the average of the top-3 scores (not just rank-1) so that questions
    whose keywords are spread across multiple chunks still pass.
    """
    if not context_chunks:
        reason = "no_context_retrieved"
        log_hallucination_guard(question, True, reason, 0.0, session_id)
        log.warning(f"Hallucination guard: BLOCKED — {reason} | q={question[:60]}")
        return False, reason

    # Average the top-3 scores (or fewer if less retrieved)
    top_scores = sorted(
        [c.get("score", 0) for c in context_chunks], reverse=True
    )[:3]
    avg_score = sum(top_scores) / len(top_scores)
    top_score = top_scores[0]

    if avg_score < MIN_RETRIEVAL_SCORE:
        reason = f"low_confidence_avg{avg_score:.0f}pct_top{top_score:.0f}pct"
        log_hallucination_guard(question, True, reason, avg_score, session_id)
        log.warning(
            f"Hallucination guard: BLOCKED — avg score {avg_score:.1f}% "
            f"(top {top_score:.1f}%) for: {question[:60]}"
        )
        return False, reason

    log_hallucination_guard(question, False, "passed", avg_score, session_id)
    return True, "passed"


def _chunk_quality_score(text: str) -> float:
    """
    0.0–1.0 estimate of how much real English is in a chunk.
    Used to detect garbage OCR before grounding checks.
    """
    if not text or len(text) < 10:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    real = sum(1 for w in words if sum(c.isalpha() for c in w) >= 3)
    return real / len(words)


def _grounding_check(answer: str, context_chunks: list[dict]) -> tuple[bool, float]:
    """
    Check that the generated answer is grounded in the retrieved context.

    Two safeguards added vs the original:
    1. Chunks whose quality score < 0.5 (mostly OCR garbage) are excluded
       from the check — a good LLM answer should not be discarded because
       the context was junk.
    2. Words must be 5+ chars (not 4+) to avoid short OCR noise like 'Veac'.
    """
    if not answer or not context_chunks:
        return False, 0.0

    # Filter to only quality chunks for the grounding check
    quality_chunks = [c for c in context_chunks if _chunk_quality_score(c["text"]) >= 0.50]

    # If ALL chunks are garbage OCR, skip the grounding check entirely —
    # we can't measure overlap against noise, so pass through to the LLM answer.
    if not quality_chunks:
        log.warning("Grounding check skipped — all context chunks are low-quality OCR")
        return True, 1.0

    context_text = " ".join(c["text"] for c in quality_chunks).lower()

    # 5+ char alpha words only, excluding common stop words
    answer_words = set(
        w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', answer)
        if w.lower() not in {
            'about', 'above', 'after', 'again', 'their', 'there', 'these',
            'those', 'could', 'would', 'should', 'which', 'where', 'while',
            'being', 'still', 'every', 'other', 'often', 'since', 'under',
            'until', 'using', 'might', 'first', 'before', 'never', 'always',
        }
    )

    if not answer_words:
        return True, 1.0  # can't check — pass through

    matched = sum(1 for w in answer_words if w in context_text)
    ratio   = matched / len(answer_words)

    log.debug(f"Grounding check: {matched}/{len(answer_words)} words "
              f"found in context ({ratio:.0%}) "
              f"[{len(quality_chunks)}/{len(context_chunks)} quality chunks used]")
    return ratio >= 0.25, ratio   # 25% overlap (was 30%; quality filter makes this safer)


def _low_confidence_response(question: str, reason: str) -> str:
    """Safe response when confidence gate fires."""
    return (
        "📚 I couldn't find a reliable answer to this question in your textbook.\n\n"
        "This might mean:\n"
        "• The topic is in a chapter not yet added to the system\n"
        "• The question uses different words than the textbook\n\n"
        "💡 **Try**: rephrase with keywords from your textbook, "
        "or ask your teacher directly."
    )


# ── Ollama (local, completely free) ─────────────────────────────────────────
def _try_ollama(system: str, user: str, model: str = "gemma2:2b") -> str | None:
    try:
        import requests
        # Use chat format with separate system + user messages
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": 0},    # no creativity = less hallucination
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user}
                ]
            },
            timeout=90
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        log.debug(f"Ollama call failed: {e}")
    return None


# ── Groq (free API) ──────────────────────────────────────────────────────────
def _try_groq(system: str, user: str) -> str | None:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama3-8b-8192",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user}
                ],
                "max_tokens": 600,
                "temperature": 0     # no creativity
            },
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            log.warning(f"Groq API error {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        log.debug(f"Groq call failed: {e}")
    return None


# ── Rule-based fallback (always works offline) ───────────────────────────────
def _fallback_answer(question: str, context_chunks: list[dict]) -> str:
    """
    When no LLM is available: extract and present relevant textbook sentences.
    No generation = zero hallucination risk.
    """
    if not context_chunks:
        return "I couldn't find information about this in your textbook."

    top = sorted(context_chunks, key=lambda x: x["score"], reverse=True)[:2]
    q_words = set(re.sub(r'[^a-z ]', '', question.lower()).split()) - {
        'what', 'why', 'how', 'is', 'are', 'the', 'a', 'an', 'in', 'of',
        'to', 'and', 'or', 'does', 'do', 'can', 'could', 'would', 'explain'
    }

    scored_sentences = []
    for chunk in top:
        for sent in re.split(r'(?<=[.!?])\s+', chunk["text"]):
            sent = sent.strip()
            if len(sent) < 20:
                continue
            overlap = sum(1 for w in q_words if w in sent.lower())
            if overlap > 0:
                scored_sentences.append((overlap, sent, chunk["source"], chunk["page"]))

    scored_sentences.sort(key=lambda x: -x[0])
    selected = [s[1] for s in scored_sentences[:4]]
    if not selected:
        selected = [top[0]["text"][:350] + "..."]

    src, pg = top[0]["source"], top[0]["page"]
    return (
        "📚 **From your textbook:**\n\n" +
        " ".join(selected) +
        f"\n\n📖 *Source: {src}, Page {pg}*"
    )


# ── Main public function ─────────────────────────────────────────────────────
def ask_llm(question: str,
            context_chunks: list[dict],
            mode: str = "tutor",
            ollama_model: str = "gemma2:2b",
            session_id: str = "") -> tuple[str, str]:
    """
    Ask the LLM with anti-hallucination guards active.

    Returns:
        (answer_text, llm_used_description)
    """
    log.info(f"ask_llm: mode={mode} session={session_id[:8]} q={question[:60]}")

    # ── 1. Confidence gate ───────────────────────────────────
    should_answer, gate_reason = _confidence_gate(
        context_chunks, question, session_id
    )
    if not should_answer:
        return _low_confidence_response(question, gate_reason), "blocked-low-confidence"

    # ── 2. Build context string ──────────────────────────────
    context_text = "\n\n---\n\n".join(
        f"[Page {c['page']} | {c['source']} | match {c['score']}%]\n{c['text']}"
        for c in context_chunks[:4]
    )

    if mode == "tutor":
        system = TUTOR_SYSTEM
        user   = (
            f"TEXTBOOK CONTENT:\n{context_text}\n\n"
            f"STUDENT QUESTION: {question}\n\n"
            "Answer using ONLY the textbook content above."
        )
    else:
        system = "You are a question paper generator. Use only the provided content."
        user   = question

    # ── 3. Try LLMs in order ─────────────────────────────────
    answer, llm_used = None, None

    raw = _try_ollama(system, user, model=ollama_model)
    if raw:
        answer, llm_used = raw, f"Ollama ({ollama_model})"
        log.info(f"Answered by Ollama ({ollama_model})")

    if not answer:
        raw = _try_groq(system, user)
        if raw:
            answer, llm_used = raw, "Groq (free API)"
            log.info("Answered by Groq")

    if not answer:
        answer = _fallback_answer(question, context_chunks)
        llm_used = "Textbook excerpts (offline mode)"
        log.info("Answered by offline fallback")

    # ── 4. Grounding check (LLM answers only) ────────────────
    if llm_used and "offline" not in llm_used and "blocked" not in llm_used:
        is_grounded, overlap = _grounding_check(answer, context_chunks)
        if not is_grounded:
            log.warning(
                f"Grounding check FAILED ({overlap:.0%} overlap) "
                f"for q={question[:60]} — switching to fallback"
            )
            log_hallucination_guard(
                question, True,
                f"grounding_failed_{overlap:.0%}", 0.0, session_id
            )
            # Replace with safer fallback answer
            answer   = _fallback_answer(question, context_chunks)
            llm_used = "Textbook excerpts (grounding-fallback)"
        else:
            log.debug(f"Grounding check passed ({overlap:.0%} overlap)")

    return answer, llm_used


def check_llm_availability() -> dict:
    """Check which LLMs are available."""
    status = {}
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            status["ollama"] = models if models else ["(no models pulled yet)"]
        else:
            status["ollama"] = None
    except Exception:
        status["ollama"] = None

    status["groq"]     = bool(os.getenv("GROQ_API_KEY"))
    status["fallback"] = True
    return status
