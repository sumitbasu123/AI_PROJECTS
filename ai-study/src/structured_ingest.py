"""
structured_ingest.py  —  11-Stage Ingestion Pipeline
=====================================================

Stage 1  Page Crop       Detect page boundary in the photo, crop to just the page
Stage 2  Deskew          Fix rotation from tilted phone-camera photos
Stage 3  Dewarp          Correct perspective / keystone distortion
Stage 4  OCR             PyMuPDF page images → PaddleOCR → fallback OCR
Stage 5  OCR Correction  LLM cleans garbled OCR text (Ollama → Groq → skip)
Stage 6  Layout Extract  Docling → Marker → built-in layout fallback
Stage 7  Markdown        Save structured .md + .json sidecar
Stage 8  Synthetic QA    Generate Q&A pairs from each page (boosts retrieval)
Stage 9  Chunk           Semantic splits on Markdown section boundaries
Stage 10 Embed           SentenceTransformer all-MiniLM-L6-v2
Stage 11 ChromaDB        Persist vector store

Run:
    python ingest.py                         # default source dir
    python ingest.py --source "C:/books"     # custom folder
    python ingest.py --force                 # re-process even if cached
    python ingest.py --no-qa                 # skip synthetic QA (faster)
    python ingest.py --no-llm-correction     # skip LLM OCR correction

Storage layout:
    markdown_store/
        <stem>.md          structured Markdown
        <stem>.json        metadata sidecar
        <stem>.qa.json     synthetic QA pairs
    vectorstore/           ChromaDB database
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from src.logger import get_logger, log_ocr_result

log = get_logger("structured_ingest")

PROJECT_ROOT   = Path(__file__).parent.parent
MARKDOWN_STORE = PROJECT_ROOT / "markdown_store"
VECTORSTORE    = PROJECT_ROOT / "vectorstore"
SOURCE_DIR = Path(
    os.environ.get("STUDY_SOURCE_DIR", str(PROJECT_ROOT / "study_materials"))
)
PDF_DPI = int(os.environ.get("AI_STUDY_PDF_DPI", "300"))
PDF_CONVERTER = os.environ.get("AI_STUDY_PDF_CONVERTER", "auto").lower()

MARKDOWN_STORE.mkdir(exist_ok=True)
VECTORSTORE.mkdir(exist_ok=True)

_PADDLE_OCR = None


# ===============================================================================
# STAGE 1 — PAGE CROP
# Detect page boundary in the photo and warp to flat rectangle.
# ===============================================================================

def _order_corners(pts):
    import numpy as np
    rect = np.zeros((4, 2), dtype=np.float32)
    s, diff = pts.sum(axis=1), np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _crop_to_page(img):
    """
    Detect the largest white rectangular region (the page) inside a phone photo
    and warp it to a flat rectangle, removing desk/background.
    Falls back silently to the original image if no clear boundary is found.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        arr  = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        edges   = cv2.Canny(blurred, 30, 100)
        kernel  = np.ones((5, 5), np.uint8)
        closed  = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for cnt in contours[:8]:
            if cv2.contourArea(cnt) < w * h * 0.15:
                break
            peri   = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.025 * peri, True)
            if len(approx) == 4:
                corners = _order_corners(approx.reshape(4, 2).astype(np.float32))
                tl, tr, br, bl = corners
                out_w = int(max(np.linalg.norm(br-bl), np.linalg.norm(tr-tl)))
                out_h = int(max(np.linalg.norm(tr-br), np.linalg.norm(tl-bl)))
                if out_w < 200 or out_h < 200:
                    continue
                dst = np.array([[0,0],[out_w-1,0],[out_w-1,out_h-1],[0,out_h-1]],
                                dtype=np.float32)
                M      = cv2.getPerspectiveTransform(corners, dst)
                warped = cv2.warpPerspective(arr, M, (out_w, out_h),
                                              flags=cv2.INTER_LANCZOS4,
                                              borderMode=cv2.BORDER_REPLICATE)
                log.debug(f"Page crop: {img.size} -> {(out_w, out_h)}")
                return Image.fromarray(warped)

        log.debug("Page crop: no clear rectangle — using full image")
        return img
    except Exception as e:
        log.debug(f"Page crop skipped: {e}")
        return img


# ===============================================================================
# STAGE 2 — DESKEW
# Fix in-plane rotation using projection profile analysis.
# ===============================================================================

def _deskew(img):
    """
    Find the angle that maximises horizontal projection variance
    (text lines create sharp horizontal bands when properly aligned).
    Corrects up to +-10 degrees of rotation.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        gray = np.array(img.convert("L"))
        _, binary = cv2.threshold(gray, 0, 255,
                                   cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        best_angle, best_var = 0, 0.0
        for angle in range(-10, 11, 1):
            h2, w2 = binary.shape
            M   = cv2.getRotationMatrix2D((w2/2, h2/2), angle, 1.0)
            rot = cv2.warpAffine(binary, M, (w2, h2),
                                  flags=cv2.INTER_NEAREST, borderValue=0)
            var = float(rot.sum(axis=1).astype(float).var())
            if var > best_var:
                best_var, best_angle = var, angle

        if abs(best_angle) > 0.5:
            log.debug(f"Deskew: {best_angle} degrees")
            arr = np.array(img.convert("RGB"))
            h2, w2 = arr.shape[:2]
            M   = cv2.getRotationMatrix2D((w2/2, h2/2), best_angle, 1.0)
            rot = cv2.warpAffine(arr, M, (w2, h2),
                                  flags=cv2.INTER_LANCZOS4,
                                  borderValue=(255,255,255))
            return Image.fromarray(rot)
        return img
    except Exception as e:
        log.debug(f"Deskew skipped: {e}")
        return img


# ===============================================================================
# STAGE 3 — DEWARP
# Correct page curvature from book-spine bend or folded pages.
# ===============================================================================

def _dewarp(img):
    """
    Detect text-line positions and apply an inverse warp to flatten curved pages.
    Uses a polynomial fit to the line positions to estimate the warp curve.
    Skips if deviation is small (<0.5% of page height).
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        arr = np.array(img.convert("L"))
        h, w = arr.shape
        _, binary = cv2.threshold(arr, 0, 255,
                                   cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kern    = cv2.getStructuringElement(cv2.MORPH_RECT, (w//10, 1))
        dilated = cv2.dilate(binary, kern, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        line_ys = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw > w*0.3 and ch < h*0.08:
                line_ys.append(y + ch//2)

        if len(line_ys) < 4:
            return img

        line_ys = sorted(line_ys)
        xs      = np.arange(len(line_ys), dtype=float)
        ys      = np.array(line_ys, dtype=float)
        coeffs  = np.polyfit(xs, ys, 2)
        ideal   = np.polyval(coeffs, xs)
        max_dev = float(np.max(np.abs(ys - ideal)))

        if max_dev < h * 0.005:
            return img

        log.debug(f"Dewarp: max deviation {max_dev:.1f}px")
        map_y = np.zeros((h, w), dtype=np.float32)
        map_x = np.zeros((h, w), dtype=np.float32)
        n = len(line_ys) - 1
        for row in range(h):
            t   = row / h * n
            dev = float(np.polyval(coeffs, t)) - (t / n * (h-1))
            shift = -dev * 0.5
            map_y[row, :] = float(np.clip(row + shift, 0, h-1))
            map_x[row, :] = np.arange(w)

        rgb      = np.array(img.convert("RGB"))
        dewarped = cv2.remap(rgb, map_x, map_y,
                              cv2.INTER_LANCZOS4,
                              borderMode=cv2.BORDER_REPLICATE)
        return Image.fromarray(dewarped)
    except Exception as e:
        log.debug(f"Dewarp skipped: {e}")
        return img


# ===============================================================================
# STAGE 4 — OCR  (PaddleOCR -> Surya -> Tesseract)
# ===============================================================================

def _ocr_with_paddle(img):
    """PaddleOCR. Install: pip install paddlepaddle paddleocr"""
    global _PADDLE_OCR
    try:
        from paddleocr import PaddleOCR
        import numpy as np
        import logging

        # show_log was removed in PaddleOCR >= 2.7.
        # Suppress PaddlePaddle's verbose output by quieting its loggers directly.
        for noisy in ("ppocr", "paddle", "PaddleOCR"):
            logging.getLogger(noisy).setLevel(logging.ERROR)

        if _PADDLE_OCR is None:
            try:
                _PADDLE_OCR = PaddleOCR(
                    lang="en",
                    use_doc_orientation_classify=True,
                    use_doc_unwarping=True,
                    use_textline_orientation=True,
                    enable_mkldnn=False,
                )
            except TypeError:
                try:
                    _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="en")
                except TypeError:
                    _PADDLE_OCR = PaddleOCR(
                        use_angle_cls=True, lang="en", show_log=False
                    )

        arr = np.array(img.convert("RGB"))
        lines = []
        if hasattr(_PADDLE_OCR, "predict"):
            results = _PADDLE_OCR.predict(arr)
            for result in results or []:
                payload = getattr(result, "json", result)
                if callable(payload):
                    payload = payload()
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if isinstance(payload, dict) and "res" in payload:
                    payload = payload["res"]
                texts = payload.get("rec_texts", []) if isinstance(payload, dict) else []
                scores = payload.get("rec_scores", []) if isinstance(payload, dict) else []
                for index, text in enumerate(texts):
                    confidence = scores[index] if index < len(scores) else 1.0
                    if float(confidence) > 0.5 and str(text).strip():
                        lines.append(str(text).strip())
        else:
            result = _PADDLE_OCR.ocr(arr, cls=True)
            for block in (result[0] if result and result[0] else []):
                if block and len(block) >= 2:
                    text_confidence = block[1]
                    if isinstance(text_confidence, (list, tuple)):
                        text, confidence = text_confidence[:2]
                        if confidence > 0.5 and str(text).strip():
                            lines.append(str(text).strip())

        text = "\n".join(lines)
        return (text, "PaddleOCR") if len(text.split()) >= 5 else None
    except ImportError:
        return None
    except Exception as e:
        log.warning(f"PaddleOCR failed: {e}")
        return None


def _ocr_with_surya(img):
    """Surya OCR. Install: pip install surya-ocr"""
    try:
        from surya.ocr import run_ocr
        from surya.model.detection.model     import load_model as load_det
        from surya.model.detection.processor import load_processor as load_det_proc
        from surya.model.recognition.model     import load_model as load_rec
        from surya.model.recognition.processor import load_processor as load_rec_proc
        result = run_ocr(
            [img], [["en"]],
            load_det(), load_det_proc(),
            load_rec(), load_rec_proc()
        )
        if not result:
            return None
        lines = [ln.text.strip()
                 for pr in result for ln in pr.text_lines
                 if ln.text and ln.confidence > 0.4]
        text = "\n".join(lines)
        return (text, "Surya") if len(text.split()) >= 5 else None
    except ImportError:
        return None
    except Exception as e:
        log.warning(f"Surya OCR failed: {e}")
        return None


def _ocr_with_tesseract(img):
    """Tesseract fallback via rag_engine multi-variant pipeline."""
    try:
        from src.rag_engine import ocr_jpeg
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name, "PNG")
            path = tmp.name
        text, method = ocr_jpeg(path)
        os.unlink(path)
        return (text, f"Tesseract/{method}") if text else None
    except Exception as e:
        log.warning(f"Tesseract OCR failed: {e}")
        return None


def _ocr_image(img):
    """Run OCR: PaddleOCR -> Surya -> Tesseract. Returns (text, engine)."""
    for fn in [_ocr_with_paddle, _ocr_with_surya, _ocr_with_tesseract]:
        res = fn(img)
        if res and len(res[0].split()) >= 5:
            return res
    return "", "all-engines-failed"


def _ocr_source_file(file_path: Path) -> list[dict[str, Any]]:
    """Stages 1-4 for one file. Returns list of page dicts."""
    suffix = file_path.suffix.lower()
    pages: list[dict[str, Any]] = []

    if suffix in {".txt", ".md"}:
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        pages.append({"page":1,"raw_text":text,
                      "ocr_engine":"direct-read","word_count":len(text.split())})
        return pages

    if suffix in {".jpg",".jpeg",".png",".jpg",".jpeg",".png"}:
        from PIL import Image
        from src.rag_engine import prepare_ocr_image
        img = Image.open(file_path)
        img = _crop_to_page(img)
        img = _deskew(img)
        img = _dewarp(img)
        img = prepare_ocr_image(img)
        text, engine = _ocr_image(img)
        wc = len(text.split())
        log_ocr_result(file_path.name, wc, engine)
        pages.append({"page":1,"raw_text":text,
                      "ocr_engine":engine,"word_count":wc})
        print(f"    OCR: {wc} words [{engine}]")
        return pages

    if suffix == ".pdf":
        try:
            import fitz
            from PIL import Image
            doc = fitz.open(str(file_path))
            for page_num in range(len(doc)):
                page = doc[page_num]
                scale = PDF_DPI / 72
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
                from src.rag_engine import prepare_ocr_image
                img = _deskew(img)
                img = _dewarp(img)
                img = prepare_ocr_image(img)
                text, engine = _ocr_image(img)
                wc = len(text.split())
                log_ocr_result(f"{file_path.name}:p{page_num+1}", wc, engine)
                pages.append({"page":page_num+1,"raw_text":text,
                              "ocr_engine":engine,"word_count":wc})
                print(f"    Page {page_num+1}: {wc} words [{engine}]")
        except ImportError:
            try:
                from pypdf import PdfReader
                for i,p in enumerate(PdfReader(str(file_path)).pages):
                    t = (p.extract_text() or "").strip()
                    pages.append({"page":i+1,"raw_text":t,
                                  "ocr_engine":"pypdf","word_count":len(t.split())})
            except Exception as e:
                log.error(f"PDF read failed: {e}")
        except Exception as e:
            log.error(f"PDF failed: {file_path.name}: {e}", exc_info=True)
        return pages

    log.warning(f"Unsupported: {file_path}")
    return []


def _convert_pdf_with_docling(file_path: Path) -> str | None:
    """Convert a PDF to structured Markdown with Docling when installed."""
    try:
        from docling.document_converter import DocumentConverter

        result = DocumentConverter().convert(str(file_path))
        markdown = result.document.export_to_markdown().strip()
        return markdown if len(markdown.split()) >= 20 else None
    except ImportError:
        return None
    except Exception as exc:
        log.warning(f"Docling conversion failed for {file_path.name}: {exc}")
        return None


def _convert_pdf_with_marker(file_path: Path) -> str | None:
    """Convert a PDF to Markdown with Marker when installed."""
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered

        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(str(file_path))
        markdown, _, _ = text_from_rendered(rendered)
        markdown = markdown.strip()
        return markdown if len(markdown.split()) >= 20 else None
    except ImportError:
        return None
    except Exception as exc:
        log.warning(f"Marker conversion failed for {file_path.name}: {exc}")
        return None


def _convert_pdf_to_markdown(
    file_path: Path,
    pages_blocks: list[dict[str, Any]],
    converter: str = PDF_CONVERTER,
) -> tuple[str, str]:
    """
    Use Docling or Marker for document structure after PaddleOCR page OCR.

    The built-in formatter remains the deterministic fallback when optional
    document-conversion models are not installed or fail.
    """
    converter = (converter or "auto").lower()
    if converter not in {"auto", "docling", "marker", "builtin"}:
        raise ValueError(
            "PDF converter must be one of: auto, docling, marker, builtin"
        )

    candidates = {
        "auto": ("docling", "marker"),
        "docling": ("docling",),
        "marker": ("marker",),
        "builtin": (),
    }[converter]
    converters = {
        "docling": _convert_pdf_with_docling,
        "marker": _convert_pdf_with_marker,
    }

    for name in candidates:
        markdown = converters[name](file_path)
        if markdown:
            log.info(f"PDF Markdown converter: {name} ({file_path.name})")
            return markdown, name

    markdown = _blocks_to_markdown(pages_blocks, file_path.name)
    log.info(f"PDF Markdown converter: builtin ({file_path.name})")
    return markdown, "builtin"


# ===============================================================================
# STAGE 5 — OCR CORRECTION (LLM)
# ===============================================================================

_OCR_CORRECTION_SYSTEM = (
    "You are an OCR correction assistant for a Class 5 Computer Science textbook. "
    "Fix garbled words, broken characters, and split words from scanned pages. "
    "Preserve all facts exactly. Do not add facts that are not visible in the OCR. "
    "Output ONLY the corrected text."
)


def _ocr_text_quality(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    usable = 0
    for word in words:
        letters = sum(c.isalpha() for c in word)
        if letters >= 3:
            usable += 1
    return usable / len(words)


def _llm_correct_ocr(raw_text: str, source_name: str = "",
                      use_llm: bool = True) -> str:
    if not use_llm or not raw_text or len(raw_text.split()) < 10:
        return raw_text

    quality = _ocr_text_quality(raw_text)
    if quality < 0.45:
        log.warning(
            f"Skipping LLM OCR correction for {source_name}: "
            f"OCR quality too low ({quality:.0%}). Rescan/reprocess page."
        )
        return raw_text

    def _ollama(text):
        try:
            import requests
            r = requests.post("http://localhost:11434/api/chat", json={
                "model":"gemma2:2b","stream":False,
                "options":{"temperature":0},
                "messages":[{"role":"system","content":_OCR_CORRECTION_SYSTEM},
                             {"role":"user","content":text[:3000]}]
            }, timeout=60)
            if r.status_code == 200:
                return r.json().get("message",{}).get("content","").strip()
        except Exception:
            pass
        return None

    def _groq(text):
        key = os.getenv("GROQ_API_KEY","")
        if not key: return None
        try:
            import requests
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {key}",
                          "Content-Type":"application/json"},
                json={"model":"llama3-8b-8192","messages":[
                    {"role":"system","content":_OCR_CORRECTION_SYSTEM},
                    {"role":"user","content":text[:3000]}],
                    "max_tokens":1500,"temperature":0}, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        return None

    corrected = _ollama(raw_text) or _groq(raw_text)
    if corrected and len(corrected.split()) >= len(raw_text.split()) * 0.5:
        return corrected
    return raw_text


# ===============================================================================
# STAGE 6 — LAYOUT EXTRACTION
# ===============================================================================

_H_ALL_CAPS = re.compile(r'^([A-Z][A-Z\s\-:]{3,59})$')
_H_CHAPTER  = re.compile(r'^((?:Chapter|Unit|Lesson)\s+\d+.{0,55})$')
_H_NUMBERED = re.compile(r'^(\d+[\.\)]\s+[A-Z].{3,55})$')
_H_QA       = re.compile(r'^(Q(?:uestion)?\s*\.?\s*\d+[\.\)].{0,60})$', re.I)
_ANSWER_RE  = re.compile(r'^(?:Ans(?:wer)?|A)\s*[\.\):](.+)$', re.I)
_DEFN_RE    = re.compile(r'^([A-Za-z][a-zA-Z\s\-]{1,40})\s*[:\-\u2013]\s+(.+)$')
_BULLET_RE  = re.compile(r'^[\*\-\u2022\u25C6\u25AA\u2713\u2717]\s+(.+)$'
                          r'|^[a-d][\.\)]\s+(.+)$')


def _classify_line(s: str) -> str:
    if not s: return "blank"
    if len(s.split()) < 2: return "para"
    for p in [_H_CHAPTER, _H_NUMBERED, _H_QA]:
        if p.match(s): return "heading"
    if _H_ALL_CAPS.match(s): return "heading"
    if _ANSWER_RE.match(s):  return "answer"
    if _BULLET_RE.match(s):  return "bullet"
    if _DEFN_RE.match(s) and len(s) < 150: return "definition"
    return "para"


def _extract_layout(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    buf: list[str] = []

    def flush():
        if buf:
            t = " ".join(buf).strip()
            if t: blocks.append({"type":"para","text":t})
            buf.clear()

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            flush(); continue
        kind = _classify_line(s)
        if kind == "heading":
            flush(); blocks.append({"type":"heading","text":s})
        elif kind == "definition":
            flush(); blocks.append({"type":"definition","text":s})
        elif kind == "bullet":
            flush()
            m = _BULLET_RE.match(s)
            c = (m.group(1) or m.group(2)) if m else s
            blocks.append({"type":"bullet","text":(c or s).strip()})
        elif kind == "answer":
            flush()
            m = _ANSWER_RE.match(s)
            blocks.append({"type":"answer",
                           "text": m.group(1).strip() if m else s})
        else:
            buf.append(s)
    flush()
    return blocks


# ===============================================================================
# STAGE 7 — MARKDOWN + OBJECT STORE
# ===============================================================================

def _blocks_to_markdown(pages_blocks: list[dict[str,Any]],
                         source_name: str) -> str:
    title       = Path(source_name).stem.replace("_"," ").replace("-"," ").title()
    title_lower = title.lower()
    md: list[str] = [f"# {title}\n"]

    for pi in pages_blocks:
        pn, blocks, engine = pi["page"], pi["blocks"], pi.get("ocr_engine","")
        if not blocks: continue
        md.append(f"\n## Page {pn}\n")
        md.append(f"<!-- meta: source={source_name} page={pn} "
                  f"ocr_engine={engine} -->\n")
        for blk in blocks:
            t, text = blk["type"], blk["text"]
            if text.strip().lower() == title_lower: continue
            if t == "heading":
                md.append(f"\n### {text.title()}\n")
            elif t == "bullet":
                md.append(f"- {text}")
            elif t == "definition":
                m = _DEFN_RE.match(text)
                if m:
                    md.append(f"\n> **{m.group(1).strip()}**: "
                               f"{m.group(2).strip()}\n")
                else:
                    md.append(f"\n> {text}\n")
            elif t == "answer":
                md.append(f"  *Answer:* {text}")
            elif t == "para" and text:
                md.append(f"\n{text}\n")
    return "\n".join(md)


def _source_fingerprint(fp: Path) -> str:
    sha = hashlib.sha1()
    with open(fp,"rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            sha.update(blk)
    return sha.hexdigest()[:12]


def _store_artifacts(stem, markdown, metadata, qa_pairs=None):
    md_p = MARKDOWN_STORE / f"{stem}.md"
    js_p = MARKDOWN_STORE / f"{stem}.json"
    md_p.write_text(markdown, encoding="utf-8")
    js_p.write_text(json.dumps(metadata, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    if qa_pairs:
        qa_p = MARKDOWN_STORE / f"{stem}.qa.json"
        qa_p.write_text(json.dumps(qa_pairs, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return md_p, js_p


def _load_cached(stem):
    md_p = MARKDOWN_STORE / f"{stem}.md"
    js_p = MARKDOWN_STORE / f"{stem}.json"
    if md_p.exists() and js_p.exists():
        qa_p = MARKDOWN_STORE / f"{stem}.qa.json"
        qa   = json.loads(qa_p.read_text(encoding="utf-8")) if qa_p.exists() else []
        return (md_p.read_text(encoding="utf-8"),
                json.loads(js_p.read_text(encoding="utf-8")), qa)
    return None


# ===============================================================================
# STAGE 8 — SYNTHETIC QA GENERATION
# ===============================================================================

_QA_SYSTEM = (
    "You are a Class 5 Computer Science exam question setter. "
    "Generate 3-6 Q&A pairs from the textbook passage. "
    "Include 'what is', 'explain', 'name', 'give example' style questions. "
    "Output ONLY a JSON array: "
    '[{"q":"What is ENIAC?","a":"ENIAC stands for..."}]'
    " No other text."
)


def _generate_qa(markdown_text: str, source_name: str,
                  use_llm: bool = True) -> list[dict[str,str]]:
    if not use_llm:
        return _rule_based_qa(markdown_text)

    text_in = " ".join(markdown_text.split()[:2000])

    def _call(text):
        # Ollama
        try:
            import requests
            r = requests.post("http://localhost:11434/api/chat", json={
                "model":"gemma2:2b","stream":False,
                "options":{"temperature":0.3},
                "messages":[{"role":"system","content":_QA_SYSTEM},
                             {"role":"user","content":text}]
            }, timeout=90)
            if r.status_code == 200:
                return r.json().get("message",{}).get("content","").strip()
        except Exception:
            pass
        # Groq
        key = os.getenv("GROQ_API_KEY","")
        if key:
            try:
                import requests
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {key}",
                              "Content-Type":"application/json"},
                    json={"model":"llama3-8b-8192",
                          "messages":[{"role":"system","content":_QA_SYSTEM},
                                       {"role":"user","content":text}],
                          "max_tokens":800,"temperature":0.3}, timeout=30)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
        return None

    raw = _call(text_in)
    if raw:
        try:
            clean = re.sub(r'```(?:json)?\s*|\s*```','',raw).strip()
            m     = re.search(r'\[.*\]', clean, re.DOTALL)
            if m:
                pairs = json.loads(m.group(0))
                valid = [p for p in pairs
                         if isinstance(p,dict) and p.get("q") and p.get("a")
                         and len(str(p["q"])) > 5]
                if valid:
                    return valid
        except Exception:
            pass
    return _rule_based_qa(markdown_text)


def _rule_based_qa(markdown_text: str) -> list[dict[str,str]]:
    pairs, lines = [], markdown_text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'^>\s*\*\*(.+?)\*\*:\s*(.+)$', line)
        if m:
            pairs.append({"q":f"What is {m.group(1).strip()}?",
                          "a":f"{m.group(1).strip()}: {m.group(2).strip()}"})
        if line.startswith("### ") and i+1 < len(lines):
            heading = line.lstrip("# ").strip()
            ctx = [lines[j].strip() for j in range(i+1,min(i+5,len(lines)))
                   if lines[j].strip() and not lines[j].startswith("#")
                   and not lines[j].startswith("<!--")][:2]
            if ctx:
                pairs.append({"q":f"Explain {heading}.",
                               "a":" ".join(ctx)})
    return pairs[:8]


# ===============================================================================
# STAGE 9 — SEMANTIC CHUNKING
# ===============================================================================

def _real_word_ratio(text: str) -> float:
    t = text.split()
    return sum(1 for w in t if sum(c.isalpha() for c in w) >= 3) / len(t) if t else 0.0


def _is_quality_chunk(text: str) -> bool:
    return len(text.split()) >= 15 and _real_word_ratio(text) >= 0.55


def _make_chunk(text, source, page, section, idx, doc_meta):
    return {"text":text.strip(),"source":source,"page":page,
            "section":section,"chunk_id":idx,
            "doc_type":doc_meta.get("doc_type",""),
            "total_pages":doc_meta.get("total_pages",1),
            "fingerprint":doc_meta.get("fingerprint","")}


def _semantic_chunks(markdown: str, metadata: dict[str,Any],
                      qa_pairs: list[dict],
                      max_chars: int = 800,
                      overlap_chars: int = 120) -> list[dict[str,Any]]:
    source    = metadata.get("source","unknown")
    chunks:   list[dict[str,Any]] = []
    idx       = 0
    prev_tail = ""
    sec_re    = re.compile(r'^(#{2,3}\s+.+)$', re.MULTILINE)
    parts     = sec_re.split(markdown)

    # Preamble
    preamble, i = "", 0
    if parts and not sec_re.match(parts[0].strip()):
        raw = re.sub(r'<!--.*?-->','',parts[0],flags=re.DOTALL)
        pre_lines = [ln for ln in raw.splitlines()
                     if not re.match(r'^#\s',ln.strip()) and ln.strip()]
        preamble = "\n".join(pre_lines).strip()
        i = 1
    if preamble and _is_quality_chunk(preamble):
        chunks.append(_make_chunk(preamble,source,1,"Introduction",idx,metadata))
        idx += 1
        prev_tail = preamble[-overlap_chars:]

    # Sections
    sections: list[tuple[str,str]] = []
    while i < len(parts)-1:
        sections.append((parts[i].strip(), parts[i+1] if i+1<len(parts) else ""))
        i += 2

    for heading, body in sections:
        pm    = re.search(r'page=(\d+)', body)
        page  = int(pm.group(1)) if pm else metadata.get("page",1)
        clean = re.sub(r'<!--.*?-->','',body,flags=re.DOTALL).strip()
        if not clean: continue
        ht    = heading.lstrip("#").strip()
        full  = f"{ht}\n\n{clean}"

        if len(full) <= max_chars:
            text = (prev_tail+"\n\n"+full).strip() if prev_tail else full
            if _is_quality_chunk(text):
                chunks.append(_make_chunk(text,source,page,ht,idx,metadata))
                idx += 1
            prev_tail = full[-overlap_chars:]
            continue

        paras   = re.split(r'\n{2,}', clean)
        current = ht
        cur_pg  = page
        for para in paras:
            para = para.strip()
            if not para: continue
            pm2 = re.search(r'page=(\d+)', para)
            if pm2:
                cur_pg = int(pm2.group(1))
                para   = re.sub(r'<!--.*?-->','',para).strip()
            cand = (current+"\n\n"+para).strip()
            if len(cand) > max_chars and current != ht:
                text = (prev_tail+"\n\n"+current).strip() if prev_tail else current
                if _is_quality_chunk(text):
                    chunks.append(_make_chunk(text,source,cur_pg,ht,idx,metadata))
                    idx += 1
                prev_tail = current[-overlap_chars:]
                current   = ht+"\n\n"+para
            else:
                current = cand
        if current.strip() and current.strip() != ht:
            text = (prev_tail+"\n\n"+current).strip() if prev_tail else current
            if _is_quality_chunk(text):
                chunks.append(_make_chunk(text,source,cur_pg,ht,idx,metadata))
                idx += 1
            prev_tail = current[-overlap_chars:]

    # QA chunks
    for qa in qa_pairs:
        q, a = str(qa.get("q","")), str(qa.get("a",""))
        if q and a:
            chunks.append({"text":f"Question: {q}\nAnswer: {a}",
                           "source":source,"page":metadata.get("page",1),
                           "section":"Q&A","chunk_id":idx,"doc_type":"qa",
                           "total_pages":metadata.get("total_pages",1),
                           "fingerprint":metadata.get("fingerprint","")})
            idx += 1

    log.info(f"Chunks: {len(chunks)} from '{source}' ({len(qa_pairs)} QA)")
    return chunks


# ===============================================================================
# STAGES 10+11 — EMBED + CHROMADB
# ===============================================================================

def build_vectorstore_from_chunks(chunks, persist_dir, collection_name="science_books"):
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    log.info(f"Building vector store: {len(chunks)} chunks -> {persist_dir}")
    print(f"\n   Embedding {len(chunks)} chunks into ChromaDB...")
    embed_fn   = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client     = chromadb.PersistentClient(path=str(persist_dir))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        collection_name, embedding_function=embed_fn,
        metadata={"hnsw:space":"cosine"}
    )
    for i in range(0, len(chunks), 100):
        batch = chunks[i:i+100]
        collection.add(
            documents=[c["text"] for c in batch],
            metadatas=[{"source":c["source"],"page":str(c["page"]),
                        "section":c.get("section",""),
                        "chunk_id":str(c["chunk_id"]),
                        "doc_type":c.get("doc_type",""),
                        "total_pages":str(c.get("total_pages",1)),
                        "fingerprint":c.get("fingerprint","")}
                       for c in batch],
            ids=[f"chunk_{i+j}" for j in range(len(batch))]
        )
        print(f"   Indexed {min(i+100,len(chunks))}/{len(chunks)}")
    print(f"   Vector store saved to {persist_dir}")
    return collection


def load_vectorstore(persist_dir, collection_name="science_books"):
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return chromadb.PersistentClient(path=str(persist_dir)).get_collection(
        collection_name, embedding_function=embed_fn
    )


def retrieve(collection, query: str, n_results: int = 5) -> list[dict[str,Any]]:
    from src.logger import log_retrieval
    results = collection.query(
        query_texts=[query], n_results=n_results,
        include=["documents","metadatas","distances"]
    )
    chunks = []
    for doc, meta, dist in zip(results["documents"][0],
                                results["metadatas"][0],
                                results["distances"][0]):
        chunks.append({"text":doc,"source":meta.get("source",""),
                       "page":meta.get("page",""),"section":meta.get("section",""),
                       "score":round((1-dist)*100,1)})
    log_retrieval(query, chunks)
    return chunks


# ===============================================================================
# MAIN PIPELINE ORCHESTRATOR
# ===============================================================================

def run_pipeline(source_dir=None, vectorstore_dir=VECTORSTORE,
                  force_reprocess=False, use_llm_correction=True,
                  generate_qa=True,
                  pdf_converter=PDF_CONVERTER) -> dict[str,Any]:
    source_dir      = Path(source_dir or SOURCE_DIR)
    vectorstore_dir = Path(vectorstore_dir)

    if not source_dir.exists():
        raise FileNotFoundError(
            f"Source folder not found: {source_dir}\n"
            "Set STUDY_SOURCE_DIR env var or use --source flag."
        )

    exts  = {".pdf",".jpg",".jpeg",".png",".JPG",".JPEG",".PNG",".txt",".md"}
    files = sorted(f for f in source_dir.rglob("*") if f.suffix in exts)

    print(f"\n{'='*62}")
    print(f"  AI Study  --  11-Stage Ingestion Pipeline")
    print(f"  Source  : {source_dir}")
    print(f"  Store   : {MARKDOWN_STORE}")
    print(f"  VecDB   : {vectorstore_dir}")
    print(f"  LLM correction : {'ON' if use_llm_correction else 'OFF'}")
    print(f"  Synthetic QA   : {'ON' if generate_qa else 'OFF'}")
    print(f"  PDF converter  : {pdf_converter}")
    print(f"  PDF render DPI : {PDF_DPI}")
    print(f"{'='*62}")

    if not files:
        print("No supported files found.")
        return {}

    print(f"\n{len(files)} file(s):")
    for f in files:
        print(f"   {f.name}")

    all_chunks: list[dict] = []
    summary = {"files":0,"cached":0,"pages":0,"chunks":0,"qa_pairs":0,"errors":0}

    for file_path in files:
        stem = file_path.stem
        print(f"\n{'─'*62}")
        print(f"  {file_path.name}")

        try: fp = _source_fingerprint(file_path)
        except Exception: fp = "unknown"

        # Cache check
        cached = _load_cached(stem)
        if cached and not force_reprocess:
            stored_md, stored_meta, stored_qa = cached
            if stored_meta.get("fingerprint") == fp:
                print("  Cache hit")
                chunks = _semantic_chunks(stored_md, stored_meta, stored_qa)
                all_chunks.extend(chunks)
                summary["cached"]   += 1
                summary["chunks"]   += len(chunks)
                summary["qa_pairs"] += len(stored_qa)
                continue

        # Stage 1-4
        print("  [1-4] Crop / Deskew / Dewarp / OCR...")
        try:
            pages = _ocr_source_file(file_path)
        except Exception as e:
            log.error(f"OCR failed: {e}", exc_info=True)
            print(f"  OCR error: {e}")
            summary["errors"] += 1
            continue

        if not pages:
            summary["errors"] += 1
            continue

        total_words = sum(p["word_count"] for p in pages)
        engines     = list({p["ocr_engine"] for p in pages})
        print(f"  OCR: {len(pages)} pages, {total_words} words, {engines}")

        # Stage 5
        if use_llm_correction:
            print("  [5] LLM OCR correction...")
        for p in pages:
            p["raw_text"] = _llm_correct_ocr(
                p["raw_text"], file_path.name, use_llm=use_llm_correction
            )

        # Stage 6
        print("  [6] Layout extraction...")
        pages_blocks = [{"page":p["page"],"ocr_engine":p["ocr_engine"],
                          "blocks":_extract_layout(p["raw_text"])} for p in pages]

        # Stage 7
        print("  [7] Markdown conversion...")
        markdown_converter = "builtin"
        if file_path.suffix.lower() == ".pdf":
            markdown, markdown_converter = _convert_pdf_to_markdown(
                file_path, pages_blocks, pdf_converter
            )
        else:
            markdown = _blocks_to_markdown(pages_blocks, file_path.name)
        doc_meta = {
            "source":file_path.name, "stem":stem,
            "doc_type":file_path.suffix.lower().lstrip("."),
            "total_pages":len(pages), "total_words":total_words,
            "fingerprint":fp,
            "ingested_at":datetime.now(timezone.utc).isoformat(),
            "ocr_engines":engines,
            "markdown_converter":markdown_converter,
            "pdf_render_dpi":PDF_DPI if file_path.suffix.lower() == ".pdf" else None,
        }

        # Stage 8
        qa_pairs: list[dict] = []
        if generate_qa:
            print("  [8] Synthetic QA generation...")
            qa_pairs = _generate_qa(markdown, file_path.name,
                                     use_llm=use_llm_correction)
            print(f"      {len(qa_pairs)} QA pairs")

        _store_artifacts(stem, markdown, doc_meta, qa_pairs)
        print(f"  [7] Stored: {stem}.md ({len(markdown):,} chars)")

        # Stage 9
        print("  [9] Semantic chunking...")
        chunks = _semantic_chunks(markdown, doc_meta, qa_pairs)
        print(f"      {len(chunks)} chunks ({len(qa_pairs)} QA)")

        all_chunks.extend(chunks)
        summary["files"]    += 1
        summary["pages"]    += len(pages)
        summary["chunks"]   += len(chunks)
        summary["qa_pairs"] += len(qa_pairs)

    if not all_chunks:
        print("\nNo chunks produced. Check logs/ocr_failures.log")
        return summary

    # Stages 10+11
    print(f"\n{'─'*62}")
    print(f"  [10-11] Embedding + ChromaDB...")
    build_vectorstore_from_chunks(all_chunks, vectorstore_dir)

    print(f"\n{'='*62}")
    print(f"  Pipeline complete!")
    print(f"  Files processed  : {summary['files']}")
    print(f"  Files from cache : {summary['cached']}")
    print(f"  Total pages      : {summary['pages']}")
    print(f"  Total chunks     : {summary['chunks']}")
    print(f"  Synthetic QA     : {summary['qa_pairs']} pairs")
    print(f"  Errors           : {summary['errors']}")
    print(f"{'='*62}\n")
    log.info(f"Pipeline complete: {summary}")
    return summary
