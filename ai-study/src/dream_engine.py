"""
dream_engine.py — Background Learning While Idle
=================================================

The DreamEngine runs in a background daemon thread. While the student is not
actively asking questions, it autonomously:

  Cycle 1 — Gap Discovery
    Probe the vector store with a bank of curriculum questions.
    Any question scoring below WEAK_SCORE_THRESHOLD (40%) is flagged
    as a coverage gap — the textbook content for that topic is either
    missing or poorly chunked.

  Cycle 2 — QA Enrichment
    For each gap topic, load the relevant Markdown pages from
    markdown_store/, generate 5-8 new Q&A pairs via LLM, and inject
    them as new chunks directly into the live ChromaDB collection.
    No full rebuild required.

  Cycle 3 — Topic Deepening
    Re-read every .md file in markdown_store/ and find sections that
    have fewer than MIN_QA_PER_SECTION QA pairs. Generate more pairs
    for those sections to improve exam question variety.

  Cycle 4 — Consolidation
    Remove near-duplicate chunks (cosine similarity > 0.97) to keep
    the vector store lean and prevent retrieval bias toward repeated content.

All activity is logged to logs/dream.log.
Status is exposed via get_status() for the Streamlit monitoring dashboard.

Usage
-----
# In app.py — start once after the vector store is loaded:
    from src.dream_engine import DreamEngine
    dream = DreamEngine(collection, markdown_store_path)
    dream.start()
    dream.notify_activity()   # call this every time a question is asked

# In tutor_agent.py / exam_agent.py — reset idle timer:
    if dream_engine:
        dream_engine.notify_activity()

# In app.py monitoring tab:
    status = dream.get_status()
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.logger import get_logger

log = get_logger("dream_engine")

# ── Tuning constants ──────────────────────────────────────────────────────────
IDLE_SECONDS          = 120    # wait this long after last activity before dreaming
CYCLE_INTERVAL        = 30     # seconds between dream sub-cycles
WEAK_SCORE_THRESHOLD  = 40.0   # retrieval score below this = coverage gap
MIN_QA_PER_SECTION    = 3      # generate more QA if a section has fewer than this
MAX_NEW_CHUNKS_CYCLE  = 20     # cap new chunks added per dream cycle
CONSOLIDATION_SIM     = 0.97   # cosine similarity above this = near-duplicate

# ── Curriculum probe questions (Class 5 Computer Science) ────────────────────
# These are the kinds of questions a student is likely to ask.
# The dream engine uses them to find holes in coverage.
CURRICULUM_PROBES = [
    # Generations of computers
    "What are first generation computers?",
    "What are second generation computers?",
    "What are third generation computers?",
    "What are fourth generation computers?",
    "What are fifth generation computers?",
    "What is ENIAC?",
    "What is UNIVAC?",
    "What are vacuum tubes?",
    "What are transistors in computers?",
    "What are integrated circuits?",
    # Hardware
    "What is a CPU?",
    "What is RAM?",
    "What is ROM?",
    "What is a hard disk?",
    "What are input devices?",
    "What are output devices?",
    "What is a keyboard?",
    "What is a monitor?",
    "What is a printer?",
    "What is a mouse?",
    # Software
    "What is an operating system?",
    "What is system software?",
    "What is application software?",
    "What is a computer program?",
    "What is programming?",
    # Networks
    "What is the internet?",
    "What is a network?",
    "What is Wi-Fi?",
    "What is a browser?",
    "What is email?",
    # Concepts
    "What is data?",
    "What is information?",
    "What is memory in a computer?",
    "What is storage?",
    "How does a computer work?",
    "What is booting?",
    "What is a file?",
    "What is a folder?",
    "What is a virus?",
    "What is antivirus software?",
]


class DreamEngine:
    """
    Background learning engine.

    Thread-safe. Safe to call notify_activity() from any thread.
    """

    def __init__(self,
                 collection,
                 markdown_store: Path | str,
                 idle_seconds:   int = IDLE_SECONDS):
        self._collection      = collection
        self._markdown_store  = Path(markdown_store)
        self._idle_seconds    = idle_seconds
        self._last_activity   = time.time()
        self._lock            = threading.Lock()
        self._stop_event      = threading.Event()
        self._thread: threading.Thread | None = None

        # Status exposed to monitoring dashboard
        self._status: dict[str, Any] = {
            "state":            "idle",        # idle | dreaming | stopped
            "cycles_completed": 0,
            "gaps_found":       0,
            "chunks_added":     0,
            "duplicates_removed": 0,
            "last_dream_at":    None,
            "last_gap_topics":  [],
            "log":              [],            # last 20 dream events
        }
        self._next_chunk_id = self._get_current_chunk_count()
        log.info("DreamEngine initialised — "
                 f"idle threshold={idle_seconds}s, "
                 f"existing chunks={self._next_chunk_id}")

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background dream thread. Call once after app loads."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._dream_loop,
            name="DreamEngine",
            daemon=True   # dies when main process exits — no cleanup needed
        )
        self._thread.start()
        log.info("DreamEngine started")
        self._log_event("Dream engine started")

    def stop(self):
        """Gracefully stop the dream thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._set_state("stopped")
        log.info("DreamEngine stopped")

    def notify_activity(self):
        """
        Call every time the student asks a question or the exam tab is used.
        Resets the idle timer, pausing any active dreaming until idle again.
        """
        with self._lock:
            self._last_activity = time.time()
        if self._status["state"] == "dreaming":
            log.debug("Dream interrupted by user activity")
            self._set_state("idle")

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of dream engine status for the dashboard."""
        with self._lock:
            idle_for = int(time.time() - self._last_activity)
            return {
                **self._status,
                "idle_for_seconds":    idle_for,
                "idle_threshold":      self._idle_seconds,
                "seconds_to_dream":    max(0, self._idle_seconds - idle_for),
            }

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _dream_loop(self):
        """Main loop: check idleness, then run dream cycles."""
        while not self._stop_event.is_set():
            time.sleep(CYCLE_INTERVAL)

            if self._stop_event.is_set():
                break

            idle_for = time.time() - self._last_activity
            if idle_for < self._idle_seconds:
                continue   # not idle yet

            # ── We are idle — start dreaming ─────────────────────────────────
            self._set_state("dreaming")
            log.info(f"Dream cycle starting (idle for {idle_for:.0f}s)")
            self._log_event(f"Dream cycle #{self._status['cycles_completed']+1} started")

            try:
                # Cycle 1: find coverage gaps
                gaps = self._find_coverage_gaps()

                # Cycle 2: enrich gaps with new QA
                if gaps and not self._stop_event.is_set():
                    added = self._enrich_gaps(gaps)
                    with self._lock:
                        self._status["chunks_added"] += added

                # Cycle 3: deepen thin sections
                if not self._stop_event.is_set():
                    added2 = self._deepen_thin_sections()
                    with self._lock:
                        self._status["chunks_added"] += added2

                # Cycle 4: consolidate duplicates (runs every 5 cycles)
                if (self._status["cycles_completed"] % 5 == 0
                        and not self._stop_event.is_set()):
                    removed = self._consolidate_duplicates()
                    with self._lock:
                        self._status["duplicates_removed"] += removed

                with self._lock:
                    self._status["cycles_completed"] += 1
                    self._status["last_dream_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()

                self._log_event(
                    f"Cycle done — gaps={len(gaps)} "
                    f"added={self._status['chunks_added']} total"
                )

            except Exception as e:
                log.error(f"Dream cycle error: {e}", exc_info=True)
                self._log_event(f"Cycle error: {e}")

            # After a full cycle, go back to idle and wait again
            self._set_state("idle")

    # ── Cycle 1: Find coverage gaps ───────────────────────────────────────────

    def _find_coverage_gaps(self) -> list[str]:
        """
        Probe the vector store with curriculum questions.
        Return a list of question strings whose top retrieval score
        is below WEAK_SCORE_THRESHOLD.
        """
        gaps: list[str] = []
        log.debug(f"Gap scan: probing {len(CURRICULUM_PROBES)} questions")

        for question in CURRICULUM_PROBES:
            if self._stop_event.is_set():
                break
            try:
                results = self._collection.query(
                    query_texts=[question],
                    n_results=1,
                    include=["distances"]
                )
                distances = results.get("distances", [[]])[0]
                if not distances:
                    gaps.append(question)
                    continue
                score = (1 - distances[0]) * 100
                if score < WEAK_SCORE_THRESHOLD:
                    gaps.append(question)
                    log.debug(f"Gap found: score={score:.1f}% q={question[:50]}")
            except Exception as e:
                log.debug(f"Gap probe failed for '{question[:40]}': {e}")

        with self._lock:
            self._status["gaps_found"]      = len(gaps)
            self._status["last_gap_topics"] = [
                q[:60] for q in gaps[:10]
            ]

        log.info(f"Gap scan complete: {len(gaps)}/{len(CURRICULUM_PROBES)} gaps found")
        self._log_event(f"Gap scan: {len(gaps)} weak topics found")
        return gaps

    # ── Cycle 2: Enrich gaps ──────────────────────────────────────────────────

    def _enrich_gaps(self, gaps: list[str]) -> int:
        """
        For each gap topic, find the most relevant Markdown section,
        generate new QA pairs, and add them to ChromaDB.
        Returns number of chunks added.
        """
        added = 0
        md_files = list(self._markdown_store.glob("*.md"))
        if not md_files:
            log.warning("Dream: no Markdown files in markdown_store/ — run ingest first")
            return 0

        for question in gaps[:MAX_NEW_CHUNKS_CYCLE]:
            if self._stop_event.is_set():
                break
            try:
                # Find most relevant markdown section for this gap
                context = self._find_markdown_context(question, md_files)
                if not context:
                    continue

                # Generate QA pairs
                qa_pairs = self._dream_generate_qa(question, context)
                if not qa_pairs:
                    continue

                # Add to ChromaDB
                n = self._add_qa_chunks(qa_pairs, source="dream")
                added += n
                log.debug(f"Enriched gap '{question[:40]}': +{n} chunks")

            except Exception as e:
                log.debug(f"Gap enrichment failed for '{question[:40]}': {e}")

        log.info(f"Gap enrichment: +{added} chunks added")
        self._log_event(f"Gap enrichment: +{added} QA chunks")
        return added

    # ── Cycle 3: Deepen thin sections ─────────────────────────────────────────

    def _deepen_thin_sections(self) -> int:
        """
        Read every .md file, find ### sections that have fewer than
        MIN_QA_PER_SECTION QA pairs in the corresponding .qa.json,
        and generate more pairs for them.
        Returns number of chunks added.
        """
        added = 0
        md_files = list(self._markdown_store.glob("*.md"))

        for md_path in md_files:
            if self._stop_event.is_set():
                break
            try:
                stem    = md_path.stem
                qa_path = self._markdown_store / f"{stem}.qa.json"
                existing_qa: list[dict] = []
                if qa_path.exists():
                    existing_qa = json.loads(
                        qa_path.read_text(encoding="utf-8")
                    )

                markdown = md_path.read_text(encoding="utf-8")
                sections = self._extract_sections(markdown)

                for section_heading, section_text in sections:
                    if self._stop_event.is_set():
                        break
                    if len(section_text.split()) < 20:
                        continue   # too short to generate QA from

                    # Count existing QA for this section
                    covered = sum(
                        1 for qa in existing_qa
                        if section_heading.lower()[:20]
                        in str(qa.get("q","")).lower()
                        or section_heading.lower()[:20]
                        in str(qa.get("a","")).lower()
                    )
                    if covered >= MIN_QA_PER_SECTION:
                        continue

                    # Generate new QA for this thin section
                    new_pairs = self._dream_generate_qa(
                        f"Generate questions about: {section_heading}",
                        section_text,
                        n=MIN_QA_PER_SECTION - covered + 2
                    )
                    if not new_pairs:
                        continue

                    # Persist new QA pairs to the .qa.json sidecar
                    all_qa = existing_qa + new_pairs
                    qa_path.write_text(
                        json.dumps(all_qa, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )

                    # Add to live ChromaDB
                    n = self._add_qa_chunks(new_pairs,
                                             source=md_path.name,
                                             section=section_heading)
                    added += n
                    log.debug(
                        f"Deepened section '{section_heading[:40]}' "
                        f"in {md_path.name}: +{n} chunks"
                    )

            except Exception as e:
                log.debug(f"Section deepening failed for {md_path.name}: {e}")

        log.info(f"Section deepening: +{added} chunks added")
        if added:
            self._log_event(f"Section deepening: +{added} chunks")
        return added

    # ── Cycle 4: Consolidate duplicates ───────────────────────────────────────

    def _consolidate_duplicates(self) -> int:
        """
        Find near-duplicate chunks (cosine similarity > CONSOLIDATION_SIM)
        and remove the lower-quality duplicate.
        Returns number of chunks removed.
        """
        removed = 0
        try:
            # Get all chunks generated by the dream engine.
            results = self._collection.get(
                where={"doc_type": "dream-qa"},
                include=["documents", "embeddings"]
            )
            ids  = results.get("ids", [])
            docs = results.get("documents", [])
            embs = results.get("embeddings", [])

            if len(ids) < 2 or not embs:
                return 0

            import numpy as np
            emb_arr    = np.array(embs)
            to_delete  = set()

            for i in range(len(ids)):
                if ids[i] in to_delete:
                    continue
                for j in range(i + 1, len(ids)):
                    if ids[j] in to_delete:
                        continue
                    # Cosine similarity
                    a, b = emb_arr[i], emb_arr[j]
                    sim  = float(np.dot(a, b) / (
                        np.linalg.norm(a) * np.linalg.norm(b) + 1e-9
                    ))
                    if sim > CONSOLIDATION_SIM:
                        # Keep the longer (richer) chunk, delete the shorter
                        if len(docs[i]) >= len(docs[j]):
                            to_delete.add(ids[j])
                        else:
                            to_delete.add(ids[i])

            if to_delete:
                self._collection.delete(ids=list(to_delete))
                removed = len(to_delete)
                log.info(f"Consolidation: removed {removed} near-duplicate chunks")
                self._log_event(f"Consolidation: removed {removed} duplicates")

        except Exception as e:
            log.debug(f"Consolidation skipped: {e}")

        return removed

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_markdown_context(self, question: str,
                                md_files: list[Path]) -> str:
        """
        Find the most relevant text passage from markdown files for a question.
        Simple keyword overlap — no embedding needed here.
        """
        q_words = set(re.sub(r'[^a-z ]', '', question.lower()).split()) - {
            'what', 'is', 'are', 'the', 'a', 'an', 'how', 'why',
            'explain', 'define', 'give', 'example', 'name', 'describe'
        }
        if not q_words:
            return ""

        best_score  = 0
        best_text   = ""

        for md_path in md_files:
            try:
                text     = md_path.read_text(encoding="utf-8")
                sections = self._extract_sections(text)
                for _, section_text in sections:
                    words   = set(section_text.lower().split())
                    overlap = sum(1 for w in q_words if w in words)
                    if overlap > best_score:
                        best_score = overlap
                        best_text  = section_text
            except Exception:
                continue

        return best_text[:2000] if best_text else ""

    def _extract_sections(self, markdown: str) -> list[tuple[str, str]]:
        """Split Markdown into (heading, body) pairs on ### boundaries."""
        sections: list[tuple[str, str]] = []
        pattern = re.compile(r'^###\s+(.+)$', re.MULTILINE)
        parts   = pattern.split(markdown)
        i = 0
        # Skip preamble
        if parts and not pattern.match(parts[0].strip()):
            i = 1
        while i < len(parts) - 1:
            heading = parts[i].strip()
            body    = re.sub(r'<!--.*?-->', '', parts[i+1],
                             flags=re.DOTALL).strip()
            if body:
                sections.append((heading, body))
            i += 2
        return sections

    def _dream_generate_qa(self, topic: str,
                            context: str,
                            n: int = 5) -> list[dict[str, str]]:
        """
        Generate QA pairs using LLM (Ollama → Groq → rule-based fallback).
        """
        if not context:
            return []

        system = (
            f"You are a Class 5 Computer Science exam question setter. "
            f"Generate exactly {n} question-answer pairs from the passage. "
            f"Focus on the topic: {topic}. "
            f"Output ONLY a JSON array: "
            f'[{{"q":"...","a":"..."}}] '
            f"No other text. Answers must be 1-3 sentences."
        )
        user = f"PASSAGE:\n{context[:2000]}"

        raw = self._call_llm(system, user)
        if raw:
            try:
                clean = re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
                m     = re.search(r'\[.*\]', clean, re.DOTALL)
                if m:
                    pairs = json.loads(m.group(0))
                    valid = [
                        p for p in pairs
                        if isinstance(p, dict)
                        and str(p.get("q", "")).strip()
                        and str(p.get("a", "")).strip()
                        and len(str(p["q"])) > 8
                    ]
                    return valid[:n]
            except Exception as e:
                log.debug(f"Dream QA JSON parse failed: {e}")

        # Rule-based fallback
        return self._rule_based_qa(context, n)

    def _rule_based_qa(self, text: str, n: int = 5) -> list[dict[str, str]]:
        """Generate simple QA pairs from definitions and key sentences."""
        pairs: list[dict[str, str]] = []
        # Extract definitions (Term: definition pattern)
        for m in re.finditer(
            r'(?:^|\n)([A-Z][a-zA-Z\s]{2,30})\s*[:\-]\s*([^\n]{20,150})',
            text
        ):
            term, defn = m.group(1).strip(), m.group(2).strip()
            pairs.append({"q": f"What is {term}?", "a": f"{term}: {defn}"})
            if len(pairs) >= n:
                return pairs

        # Extract bold definitions from Markdown (> **Term**: ...)
        for m in re.finditer(r'>\s*\*\*(.+?)\*\*:\s*(.+)', text):
            pairs.append({
                "q": f"What is {m.group(1).strip()}?",
                "a": f"{m.group(1).strip()}: {m.group(2).strip()}"
            })
            if len(pairs) >= n:
                return pairs

        return pairs

    def _add_qa_chunks(self, qa_pairs: list[dict],
                        source: str = "dream",
                        section: str = "Q&A") -> int:
        """Add QA pairs as new chunks to the live ChromaDB collection."""
        if not qa_pairs:
            return 0
        docs, metas, ids = [], [], []
        for qa in qa_pairs:
            q = str(qa.get("q", "")).strip()
            a = str(qa.get("a", "")).strip()
            if not q or not a:
                continue
            chunk_id = self._next_chunk_id
            self._next_chunk_id += 1
            docs.append(f"Question: {q}\nAnswer: {a}")
            metas.append({
                "source":      source,
                "page":        "dream",
                "section":     section,
                "chunk_id":    str(chunk_id),
                "doc_type":    "dream-qa",
                "total_pages": "0",
                "fingerprint": "dream",
            })
            ids.append(f"dream_chunk_{uuid.uuid4().hex}")

        if docs:
            try:
                self._collection.add(documents=docs, metadatas=metas, ids=ids)
                return len(docs)
            except Exception as e:
                log.warning(f"Failed to add dream chunks: {e}")
        return 0

    def _call_llm(self, system: str, user: str) -> str | None:
        """Try Ollama then Groq. Return raw response string or None."""
        # Ollama
        try:
            import requests
            r = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model":   "gemma2:2b",
                    "stream":  False,
                    "options": {"temperature": 0.4},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user}
                    ]
                },
                timeout=60
            )
            if r.status_code == 200:
                return r.json().get("message", {}).get("content", "").strip()
        except Exception:
            pass
        # Groq
        key = os.getenv("GROQ_API_KEY", "")
        if key:
            try:
                import requests
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                              "Content-Type": "application/json"},
                    json={
                        "model": "llama3-8b-8192",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": user}
                        ],
                        "max_tokens": 600,
                        "temperature": 0.4
                    },
                    timeout=30
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
        return None

    def _get_current_chunk_count(self) -> int:
        """Get current number of chunks to avoid ID collisions."""
        try:
            return self._collection.count()
        except Exception:
            return 10000   # safe fallback

    def _set_state(self, state: str):
        with self._lock:
            self._status["state"] = state

    def _log_event(self, message: str):
        """Add a timestamped entry to the in-memory dream log (last 20)."""
        entry = f"{datetime.now().strftime('%H:%M:%S')}  {message}"
        log.info(f"[Dream] {message}")
        with self._lock:
            self._status["log"].append(entry)
            if len(self._status["log"]) > 20:
                self._status["log"] = self._status["log"][-20:]
