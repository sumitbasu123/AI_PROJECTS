"""
logger.py — Centralised logging for AI Study
---------------------------------------------
Writes to:
  ./logs/ai_study.log     — all events (rotating, max 2 MB × 3 files)
  ./logs/ocr_failures.log — every JPEG that returned 0 words
  ./logs/hallucination_guard.log — every time the guard fires

Usage anywhere in the project:
    from src.logger import get_logger
    log = get_logger("rag_engine")
    log.info("Loaded 18 images")
    log.warning("Low OCR word count: 2 words from 1.jpg")
    log.error("Tesseract not found", exc_info=True)
"""

import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Formatters ───────────────────────────────────────────────
DETAILED = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
SIMPLE = logging.Formatter("%(levelname)-8s | %(name)s | %(message)s")

# ── Root rotating file handler (all modules) ─────────────────
_root_handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / "ai_study.log",
    maxBytes=2 * 1024 * 1024,   # 2 MB
    backupCount=3,
    encoding="utf-8"
)
_root_handler.setFormatter(DETAILED)
_root_handler.setLevel(logging.DEBUG)

# ── Console handler (INFO+ only, clean format) ───────────────
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(SIMPLE)
_console_handler.setLevel(logging.WARNING)  # only warnings+ to console

# ── Specialised loggers ──────────────────────────────────────
def _make_file_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    h = logging.handlers.RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=1 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8"
    )
    h.setFormatter(DETAILED)
    logger.addHandler(h)
    logger.addHandler(_root_handler)
    logger.propagate = False
    return logger

# These are module-level singletons
ocr_log   = _make_file_logger("ocr_failures",        "ocr_failures.log")
guard_log = _make_file_logger("hallucination_guard",  "hallucination_guard.log")


def get_logger(name: str) -> logging.Logger:
    """Get (or create) a named logger that writes to ai_study.log."""
    logger = logging.getLogger(f"ai_study.{name}")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_root_handler)
        logger.addHandler(_console_handler)
        logger.propagate = False
    return logger


def log_session_start(session_id: str, question: str):
    log = get_logger("session")
    log.info(f"SESSION={session_id[:8]} | Q={question[:80]}")


def log_retrieval(query: str, chunks: list, session_id: str = ""):
    log = get_logger("retrieval")
    scores = [c.get("score", 0) for c in chunks]
    top    = max(scores) if scores else 0
    log.info(
        f"SESSION={session_id[:8]} | query={query[:60]} | "
        f"chunks={len(chunks)} | top_score={top:.1f}%"
    )
    if top < 20:
        log.warning(
            f"LOW RETRIEVAL SCORE {top:.1f}% for query: {query[:60]}"
        )


def log_ocr_result(filename: str, words: int, method: str, error: str = ""):
    if words == 0:
        ocr_log.error(
            f"ZERO_WORDS | file={filename} | method={method} | error={error}"
        )
    elif words < 10:
        ocr_log.warning(
            f"LOW_WORDS={words} | file={filename} | method={method}"
        )
    else:
        ocr_log.info(
            f"OK words={words} | file={filename} | method={method}"
        )


def log_hallucination_guard(question: str, fired: bool, reason: str,
                             score: float, session_id: str = ""):
    guard_log.info(
        f"SESSION={session_id[:8]} | fired={fired} | score={score:.1f}% | "
        f"reason={reason} | q={question[:60]}"
    )


def get_log_stats() -> dict:
    """Return counts from log files for the monitoring dashboard."""
    stats = {
        "total_questions": 0,
        "ocr_failures": 0,
        "ocr_warnings": 0,
        "hallucination_guards_fired": 0,
        "low_retrieval_warnings": 0,
    }
    try:
        main_log = LOG_DIR / "ai_study.log"
        if main_log.exists():
            content = main_log.read_text(encoding="utf-8", errors="ignore")
            stats["total_questions"]        = content.count("SESSION=")
            stats["low_retrieval_warnings"] = content.count("LOW RETRIEVAL SCORE")

        ocr_f = LOG_DIR / "ocr_failures.log"
        if ocr_f.exists():
            content = ocr_f.read_text(encoding="utf-8", errors="ignore")
            stats["ocr_failures"] = content.count("ZERO_WORDS")
            stats["ocr_warnings"] = content.count("LOW_WORDS")

        guard_f = LOG_DIR / "hallucination_guard.log"
        if guard_f.exists():
            content = guard_f.read_text(encoding="utf-8", errors="ignore")
            stats["hallucination_guards_fired"] = content.count("fired=True")
    except Exception:
        pass
    return stats


def get_recent_logs(n: int = 30) -> list[str]:
    """Return the last N lines from the main log for the dashboard."""
    try:
        main_log = LOG_DIR / "ai_study.log"
        if main_log.exists():
            lines = main_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            return lines[-n:]
    except Exception:
        pass
    return []
