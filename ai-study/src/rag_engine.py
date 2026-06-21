"""
RAG Engine â€” 100% free, runs locally.

JPEG improvements in this version:
  - 6 preprocessing variants tried per image (up from 3)
  - Auto-deskew for tilted phone-camera photos
  - Adaptive thresholding (much better than fixed 128)
  - DPI upscaling to 300 DPI before OCR
  - Tesseract path hard-searched at startup and cached
  - Every OCR result logged to logs/ocr_failures.log
"""

import os
import re
from pathlib import Path

from src.logger import get_logger, log_ocr_result

log = get_logger("rag_engine")

PROJECT_ROOT = Path(__file__).parent.parent
OCR_DEBUG_DIR = PROJECT_ROOT / "ocr_debug"
OCR_DEBUG = os.environ.get("STUDY_OCR_DEBUG", "").strip().lower() in {
    "1", "true", "yes", "on"
}
if OCR_DEBUG:
    OCR_DEBUG_DIR.mkdir(exist_ok=True)

# â”€â”€ Find and cache Tesseract path once at import time â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _find_tesseract() -> str | None:
    """Search all common Windows locations for tesseract.exe."""
    import shutil
    # Check PATH first (Linux/Mac and Windows if added to PATH)
    if shutil.which("tesseract"):
        log.info("Tesseract found in system PATH")
        return shutil.which("tesseract")

    username = os.environ.get("USERNAME", "user")
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Tesseract-OCR\tesseract.exe",
        r"C:\tools\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Programs", "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""),
                     "AppData", "Local", "Programs", "Tesseract-OCR",
                     "tesseract.exe"),
        rf"C:\Users\{username}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            log.info(f"Tesseract found at: {path}")
            return path

    log.error(
        "Tesseract NOT FOUND. Install from: "
        "https://github.com/UB-Mannheim/tesseract/wiki"
    )
    return None

_TESSERACT_PATH = _find_tesseract()


def _set_tesseract():
    """Set pytesseract path from cached value."""
    if _TESSERACT_PATH:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH
            return True
        except ImportError:
            log.error("pytesseract not installed. Run: pip install pytesseract")
            return False
    return False


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# IMAGE PREPROCESSING â€” 8 variants, designed for coloured textbook pages
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _upscale_to_300dpi(img, assumed_dpi: int = 96):
    """Upscale image to ~300 DPI equivalent. Tesseract needs 300+."""
    from PIL import Image
    w, h = img.size
    if w < 1800:   # below 300 DPI for A4 width
        scale = max(2.0, 300 / assumed_dpi)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        log.debug(f"Upscaled image: {w}x{h} â†’ {new_w}x{new_h}")
    return img


def _save_debug_image(img, stem: str, label: str):
    """Save OCR preprocessing images only when STUDY_OCR_DEBUG=1."""
    if not OCR_DEBUG:
        return
    try:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)[:80]
        img.save(OCR_DEBUG_DIR / f"{safe}_{label}.png")
    except Exception as e:
        log.debug(f"Could not save OCR debug image {label}: {e}")


def _normalize_illumination(img):
    """
    Remove phone-photo shadows and uneven page lighting without deleting
    coloured headings or callout text.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        gray = np.array(img.convert("L"))
        bg = cv2.medianBlur(gray, 35)
        norm = cv2.divide(gray, bg, scale=255)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        norm = clahe.apply(norm)
        return Image.fromarray(norm)
    except Exception as e:
        log.debug(f"Illumination normalization skipped: {e}")
        return img.convert("L")


def _sauvola_like_threshold(img, block_size: int = 35, c: int = 11):
    """
    Adaptive threshold for photographed pages. It handles shadows better
    than a single fixed threshold.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        gray = np.array(img.convert("L"))
        if block_size % 2 == 0:
            block_size += 1
        block_size = max(15, block_size)
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block_size,
            c,
        )
        return Image.fromarray(binary)
    except Exception as e:
        log.debug(f"Adaptive threshold skipped: {e}")
        return img.convert("L")


def _suppress_large_pictures_keep_text(img):
    """
    Lightly suppress big illustrations while keeping coloured text. The old
    colour cleaner removed all high-saturation pixels, which can erase useful
    textbook headings and labels.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        rgb = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        colour_mask = cv2.inRange(hsv[:, :, 1], 70, 255)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        large_colour = cv2.morphologyEx(
            colour_mask, cv2.MORPH_CLOSE, kernel, iterations=1
        )
        contours, _ = cv2.findContours(
            large_colour, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        h, w = gray.shape
        cleaned = gray.copy()
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            if area > (w * h * 0.015) and cw > 80 and ch > 40:
                roi = cleaned[y:y+ch, x:x+cw]
                cleaned[y:y+ch, x:x+cw] = np.maximum(roi, 235)

        return Image.fromarray(cleaned)
    except Exception as e:
        log.debug(f"Picture suppression skipped: {e}")
        return img.convert("L")


def _remove_colour_regions(img):
    """
    Backward-compatible name for the safer textbook cleaner. It fades large
    illustration regions but keeps coloured headings and labels.
    """
    return _suppress_large_pictures_keep_text(img)


def _deskew(img):
    """
    Correct slight rotation caused by phone-camera angle.
    Falls back silently if it can't detect angle.
    """
    try:
        import pytesseract
        _set_tesseract()
        osd = pytesseract.image_to_osd(
            img, config="--psm 0 -c min_characters_to_try=5",
            nice=0, output_type=pytesseract.Output.DICT
        )
        angle = osd.get("rotate", 0)
        if angle and abs(angle) > 1:
            log.debug(f"Deskewing by {angle}Â°")
            img = img.rotate(-angle, expand=True, fillcolor=255)
    except Exception:
        pass
    return img


def _variant_colour_clean(img):
    """Picture suppression + shadow cleanup + adaptive threshold."""
    from PIL import ImageFilter, ImageEnhance
    img = _upscale_to_300dpi(img)
    img = _remove_colour_regions(img)
    img = _normalize_illumination(img)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    return _sauvola_like_threshold(img, block_size=41, c=10)


def _variant_enhanced(img):
    """
    Variant 2: grayscale + upscale + denoise + adaptive threshold.
    Gaussian blur radius reduced from 15 â†’ 5 to prevent halos around
    dark image regions bleeding into adjacent text.
    """
    from PIL import Image, ImageFilter, ImageEnhance
    import numpy as np
    img = img.convert("L")
    img = _upscale_to_300dpi(img)
    img = _normalize_illumination(img)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(2.5)
    # Adaptive threshold with smaller radius (was 15, now 5) to avoid halos
    blurred  = img.filter(ImageFilter.GaussianBlur(radius=5))
    arr      = np.array(img)
    arr_blur = np.array(blurred)
    binary   = ((arr.astype(int) - arr_blur.astype(int)) > -15).astype(np.uint8) * 255
    return Image.fromarray(binary)


def _variant_otsu(img):
    """Variant 3: grayscale + upscale + Otsu global threshold."""
    from PIL import Image, ImageFilter, ImageEnhance
    import numpy as np
    img = img.convert("L")
    img = _upscale_to_300dpi(img)
    img = _normalize_illumination(img)
    img = img.filter(ImageFilter.MedianFilter(3))
    arr = np.array(img)
    hist, _ = np.histogram(arr.flatten(), 256, [0, 256])
    total     = arr.size
    sum_total = np.dot(np.arange(256), hist)
    sum_b, w_b, max_var, threshold = 0, 0, 0, 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0: continue
        w_f = total - w_b
        if w_f == 0: break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var, threshold = var, t
    binary = (arr > threshold).astype(np.uint8) * 255
    return Image.fromarray(binary)


def _variant_deskewed(img):
    """Variant 4: deskew first, then tight fixed threshold."""
    from PIL import Image, ImageFilter, ImageEnhance
    img = img.convert("L")
    img = _upscale_to_300dpi(img)
    img = _normalize_illumination(img)
    img = _deskew(img)
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.point(lambda p: 255 if p > 140 else 0)
    return img


def _variant_colour_clean_deskewed(img):
    """Picture suppression + shadow cleanup + deskew + adaptive threshold."""
    from PIL import ImageFilter, ImageEnhance
    img = _upscale_to_300dpi(img)
    img = _remove_colour_regions(img)
    img = _normalize_illumination(img)
    img = _deskew(img)
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    return _sauvola_like_threshold(img, block_size=41, c=9)


def _variant_shadow_adaptive(img):
    """Shadow removal + adaptive threshold, no colour suppression."""
    from PIL import ImageFilter, ImageEnhance
    img = _upscale_to_300dpi(img)
    img = _normalize_illumination(img)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = ImageEnhance.Contrast(img).enhance(2.2)
    return _sauvola_like_threshold(img, block_size=35, c=8)


def _variant_inverted(img):
    """Variant 6: for dark-background / white-text pages."""
    from PIL import Image, ImageOps
    img = img.convert("L")
    img = _upscale_to_300dpi(img)
    img = ImageOps.invert(img)
    img = img.point(lambda p: 255 if p > 128 else 0)
    return img


def _variant_raw_gray(img):
    """Variant 7: simple grayscale â€” for already-clean scans."""
    from PIL import Image
    img = img.convert("L")
    img = _upscale_to_300dpi(img)
    return img


def _variant_original(img):
    """Variant 8: RGB original â€” fallback."""
    return _upscale_to_300dpi(img.copy())


def prepare_ocr_image(img):
    """
    Public helper for the structured pipeline. It returns a high-resolution,
    shadow-normalized page image while preserving coloured textbook text.
    """
    from PIL import ImageFilter, ImageEnhance
    img = _upscale_to_300dpi(img)
    img = _suppress_large_pictures_keep_text(img)
    img = _normalize_illumination(img)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.filter(ImageFilter.SHARPEN)
    return ImageEnhance.Contrast(img).enhance(1.8)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# OCR PIPELINE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# PSM modes tried per variant.
# PSM 3 (fully automatic) removed â€” it tries to detect columns/images and
# goes wrong on mixed-layout textbook pages. Replaced with PSM 12 (sparse
# text with OSD) which handles single text column beside an image correctly.
_PSM_CONFIGS = [
    "--psm 6 --oem 3",   # uniform block of text â€” best for textbook pages
    "--psm 4 --oem 3",   # single column of text
    "--psm 12 --oem 3",  # sparse text with OSD â€” good for mixed layouts
    "--psm 11 --oem 3",  # sparse text â€” good for noisy/fragmented scans
]


def _run_tesseract(img, config: str) -> str:
    """Run pytesseract on a PIL image and return text."""
    try:
        import pytesseract
        _set_tesseract()
        return pytesseract.image_to_string(img, config=config).strip()
    except Exception as e:
        log.debug(f"Tesseract run failed ({config}): {e}")
        return ""


def _score_text(text: str) -> float:
    """
    Quality score for OCR output.
    Rewards real words, penalises symbol noise.
    Returns a float â€” higher is better.
    """
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0

    # Count words that look like real English (3+ alpha chars)
    real_words = sum(1 for w in words if sum(c.isalpha() for c in w) >= 3)
    alpha_chars = sum(1 for c in text if c.isalpha())
    alnum_chars = sum(1 for c in text if c.isalnum())
    # Penalise lines that are mostly symbols
    noise_chars = sum(1 for c in text if c in r'|}{\\/@#$%^&*~`<>')
    noise_ratio = noise_chars / max(len(text), 1)
    alpha_ratio = alpha_chars / max(alnum_chars, 1)
    short_line_penalty = sum(1 for line in text.splitlines()
                             if 0 < len(line.strip()) < 4)

    score = real_words
    score -= noise_ratio * len(words) * 3
    score -= short_line_penalty * 0.5
    if alpha_ratio < 0.55:
        score *= 0.5
    return max(score, 0.0)


def _ocr_text_regions(img, stem: str = "") -> str:
    """
    Detect likely text blocks and OCR each block separately. This helps
    textbook photos with side illustrations, coloured boxes, and captions.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        base = _variant_shadow_adaptive(img.copy())
        gray = np.array(base.convert("L"))
        ink = 255 - gray
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 5))
        dilated = cv2.dilate(ink, kernel, iterations=2)
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        h, w = gray.shape
        boxes = []
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if bw < 80 or bh < 18:
                continue
            if area < w * h * 0.0008 or area > w * h * 0.45:
                continue
            boxes.append((x, y, bw, bh))

        if len(boxes) < 2:
            return ""

        boxes.sort(key=lambda b: (b[1], b[0]))
        lines = []
        for i, (x, y, bw, bh) in enumerate(boxes[:80]):
            pad = 10
            crop = base.crop((
                max(0, x - pad),
                max(0, y - pad),
                min(w, x + bw + pad),
                min(h, y + bh + pad),
            ))
            if OCR_DEBUG and i < 20:
                _save_debug_image(crop, stem, f"region_{i:02d}")
            text = _run_tesseract(crop, "--psm 6 --oem 3")
            if _score_text(text) >= 2:
                lines.append(text.strip())

        return "\n".join(lines)
    except Exception as e:
        log.debug(f"Region OCR failed: {e}")
        return ""


def ocr_jpeg(img_path: str) -> tuple[str, str]:
    """
    Full 6-variant OCR pipeline for JPEG and PNG files.

    Tries 6 image preprocessing variants Ã— 4 PSM configs = up to 24 attempts.
    Returns whichever produced the highest quality text.

    Returns:
        (extracted_text, method_description)
    """
    if not _TESSERACT_PATH:
        msg = (
            "Tesseract not installed. "
            "Download from https://github.com/UB-Mannheim/tesseract/wiki"
        )
        log_ocr_result(str(img_path), 0, "missing-tesseract", msg)
        return "", "tesseract-not-installed"

    try:
        from PIL import Image
        img_orig = Image.open(img_path)
        log.debug(f"OCR start: {Path(img_path).name} "
                  f"({img_orig.width}x{img_orig.height}, mode={img_orig.mode})")
    except Exception as e:
        log.error(f"Cannot open image {img_path}: {e}")
        log_ocr_result(str(img_path), 0, "open-failed", str(e))
        return "", f"open-error: {e}"

    variants = [
        (_variant_colour_clean,          "colour-clean"),          # NEW: best for textbooks
        (_variant_colour_clean_deskewed, "colour-clean-deskewed"), # NEW: coloured + rotated
        (_variant_shadow_adaptive,       "shadow-adaptive"),
        (_variant_enhanced,              "adaptive-threshold"),
        (_variant_otsu,                  "otsu-threshold"),
        (_variant_deskewed,              "deskewed"),
        (_variant_inverted,              "inverted"),
        (_variant_raw_gray,              "raw-gray"),
        (_variant_original,              "original-rgb"),
    ]

    best_text   = ""
    best_score  = 0.0
    best_method = "none"

    for variant_fn, variant_name in variants:
        try:
            processed = variant_fn(img_orig.copy())
            _save_debug_image(processed, Path(img_path).stem, variant_name)
        except Exception as e:
            log.debug(f"Variant {variant_name} preprocessing failed: {e}")
            continue

        for psm_config in _PSM_CONFIGS:
            text = _run_tesseract(processed, psm_config)
            score = _score_text(text)
            method = f"{variant_name}+{psm_config.split()[0][2:]}"

            log.debug(
                f"{Path(img_path).name} | {method} | "
                f"words={len(text.split())} score={score:.1f}"
            )

            if score > best_score:
                best_score  = score
                best_text   = text
                best_method = method
        # Note: we intentionally try ALL variants and ALL PSM configs.
        # The old early-exit at score>50 would stop after the first
        # variant that extracted 50+ words, potentially missing 3x more
        # content available from a better preprocessing choice.

    region_text = _ocr_text_regions(img_orig.copy(), Path(img_path).stem)
    region_score = _score_text(region_text)
    if region_score > best_score * 1.10:
        best_text = region_text
        best_score = region_score
        best_method = "text-regions+psm6"

    best_text = _clean_ocr_text(best_text)
    word_count = len(best_text.split())

    # Log every result
    log_ocr_result(
        filename=Path(img_path).name,
        words=word_count,
        method=best_method,
        error="" if word_count > 0 else "all_variants_failed"
    )

    if word_count == 0:
        log.warning(
            f"ALL VARIANTS FAILED for {Path(img_path).name}. "
            f"Check: 1) Tesseract English language data installed, "
            f"2) image not too blurry/dark, 3) text is not handwritten."
        )
    else:
        log.info(
            f"OCR OK: {Path(img_path).name} | "
            f"{word_count} words | method={best_method}"
        )

    return best_text, best_method


def _clean_ocr_text(text: str) -> str:
    """
    Remove OCR noise and fix common substitution errors from scanned textbooks.

    Changes vs original:
    - alnum threshold raised from 2 â†’ 4 (stops 'I I', '1 2', '. ,' noise lines)
    - Strips lines that are purely punctuation/symbols even if they pass alnum
    - Fixes common scanned-textbook OCR errors: rnâ†’m, clâ†’d, fi ligature, etc.
    - Collapses excessive whitespace from column-layout PDFs
    """
    if not text:
        return ""
    lines = text.splitlines()
    clean = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Require at least 4 real alphanumeric chars (raised from 2)
        if sum(c.isalnum() for c in s) < 4:
            continue
        # Skip lines that are purely numbers/punctuation (page numbers, leaders)
        alpha_chars = sum(c.isalpha() for c in s)
        if alpha_chars < 2:
            continue
        clean.append(s)

    text = "\n".join(clean)

    # â”€â”€ Whitespace cleanup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{3,}', '  ', text)

    # â”€â”€ Common OCR substitution fixes for printed textbooks â”€â”€
    text = text.replace("|", "I")
    # 0 mistaken for o/O in words
    text = re.sub(r'(?<=[a-z])0(?=[a-z])', 'o', text)
    text = re.sub(r'(?<=[A-Z])0(?=[A-Z])', 'O', text)
    # rn often misread as m in serif fonts
    text = re.sub(r'\brn\b', 'm', text)
    # Common ligature failures
    text = text.replace("ï¬", "fi").replace("ï¬‚", "fl").replace("ï¬€", "ff")
    text = text.replace("ï¬ƒ", "ffi").replace("ï¬„", "ffl")
    # l mistaken for 1 at word start
    text = re.sub(r'\b1([a-z]{3,})', r'l\1', text)

    return text.strip()


def ocr_pdf_page(pdf_path: str, page_num: int) -> str:
    """
    OCR a scanned PDF page by rendering it to a high-resolution image first.

    Render at 400 DPI (5.56x zoom from 72 DPI base) â€” the previous 2.5x
    produced only ~180 DPI which caused Tesseract to miss characters.
    Saves temp file as PNG (lossless) to avoid JPEG compression artifacts
    on thin strokes and fine serif text.
    """
    try:
        import fitz
        from PIL import Image, ImageFilter, ImageEnhance
        doc  = fitz.open(pdf_path)
        page = doc[page_num]
        # 5.56x zoom â†’ 400 DPI from a 72 DPI PDF source
        # 400 DPI is the sweet spot: 300 is minimum, 600 is diminishing returns
        mat  = fitz.Matrix(5.56, 5.56)
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Light pre-processing before handing to the 6-variant OCR pipeline:
        # convert to grayscale and boost contrast so faint print reads cleanly
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.8)
        img = img.filter(ImageFilter.SHARPEN)

        log.debug(
            f"PDF page {page_num+1} rendered: {pix.width}x{pix.height}px "
            f"({pix.width/5.56:.0f}x{pix.height/5.56:.0f} logical)"
        )

        import tempfile
        # PNG = lossless; JPEG would introduce compression artifacts on thin strokes
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name, "PNG")
            text, method = ocr_jpeg(tmp.name)
        os.unlink(tmp.name)
        log.info(f"PDF page {page_num+1} OCR: {len(text.split())} words [{method}]")
        return text
    except ImportError:
        log.warning("PyMuPDF not installed â€” scanned PDF pages will be skipped. "
                    "Run: pip install PyMuPDF")
        return ""
    except Exception as e:
        log.error(f"PDF page OCR failed (page {page_num}): {e}", exc_info=True)
        return ""


# Legacy alias
def ocr_image(img_path: str) -> str:
    text, _ = ocr_jpeg(img_path)
    return text


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# DOCUMENT LOADING
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def load_documents(folder: str) -> list[dict]:
    """Load all supported files from folder. Returns list of document dicts."""
    folder_path = Path(folder)
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    pdf_files  = sorted(folder_path.rglob("*.pdf"))
    jpeg_files = (sorted(folder_path.rglob("*.jpg"))  +
                  sorted(folder_path.rglob("*.jpeg")) +
                  sorted(folder_path.rglob("*.JPG"))  +
                  sorted(folder_path.rglob("*.JPEG")))
    png_files  = (sorted(folder_path.rglob("*.png"))  +
                  sorted(folder_path.rglob("*.PNG")))
    txt_files  = (sorted(folder_path.rglob("*.txt"))  +
                  sorted(folder_path.rglob("*.md")))

    total = len(pdf_files) + len(jpeg_files) + len(png_files) + len(txt_files)
    log.info(f"Scanning {folder}: {len(pdf_files)} PDFs, "
             f"{len(jpeg_files)} JPEGs, {len(png_files)} PNGs, "
             f"{len(txt_files)} text â€” total {total}")

    print(f"\nFiles found in: {folder}")
    print(f"  PDFs   : {len(pdf_files)}")
    print(f"  JPEGs  : {len(jpeg_files)}")
    print(f"  PNGs   : {len(png_files)}")
    print(f"  Text   : {len(txt_files)}")
    print(f"  Total  : {total}")

    if total == 0:
        log.warning(f"No supported files found in {folder}")
        return []

    documents = []
    ocr_zero_count = 0

    # â”€â”€ PDFs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if pdf_files:
        print(f"\nðŸ“„ Processing PDFs ({len(pdf_files)})...")
    for pdf_path in pdf_files:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            page_count = len(reader.pages)
            ocr_pages = 0
            for page_num, page in enumerate(reader.pages):
                raw = page.extract_text() or ""
                # Count real alphanumeric characters â€” not total length.
                # Scanned PDFs often produce whitespace, null bytes, or a handful
                # of stray characters that pass a simple len() check but contain
                # no real content. We require at least 40 real alnum chars.
                real_chars = sum(1 for c in raw if c.isalnum())
                if real_chars < 40:
                    # Scanned page â€” render to high-res image and OCR it
                    text = ocr_pdf_page(str(pdf_path), page_num)
                    ocr_pages += 1
                else:
                    text = raw.strip()
                if text.strip():
                    documents.append({
                        "text": text.strip(), "source": pdf_path.name,
                        "page": page_num + 1, "type": "pdf"
                    })
            label = f"{page_count} pages"
            if ocr_pages:
                label += f", {ocr_pages} scannedâ†’OCR"
            print(f"  âœ“ {pdf_path.name} â€” {label}")
            log.info(f"PDF loaded: {pdf_path.name} ({page_count} pages, {ocr_pages} OCR'd)")
        except Exception as e:
            print(f"  âœ— {pdf_path.name} â€” {e}")
            log.error(f"PDF load failed: {pdf_path.name}: {e}")

    # â”€â”€ JPEGs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if jpeg_files:
        print(f"\nðŸ–¼  Processing JPEGs ({len(jpeg_files)})...")
        print("    (Running 6-variant OCR pipeline per image...)")
    for img_path in jpeg_files:
        try:
            text, method = ocr_jpeg(str(img_path))
            wc = len(text.split()) if text else 0
            if wc >= 5:
                documents.append({
                    "text": text.strip(), "source": img_path.name,
                    "page": 1, "type": "jpeg"
                })
                print(f"  âœ“ {img_path.name} â€” {wc} words [{method}]")
            else:
                ocr_zero_count += 1
                print(f"  âš  {img_path.name} â€” only {wc} words "
                      f"(logged to logs/ocr_failures.log)")
        except Exception as e:
            log.error(f"JPEG load failed: {img_path.name}: {e}", exc_info=True)
            print(f"  âœ— {img_path.name} â€” {e}")

    # â”€â”€ PNGs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if png_files:
        print(f"\nðŸ–¼  Processing PNGs ({len(png_files)})...")
    for img_path in png_files:
        try:
            text, method = ocr_jpeg(str(img_path))
            wc = len(text.split()) if text else 0
            if wc >= 5:
                documents.append({
                    "text": text.strip(), "source": img_path.name,
                    "page": 1, "type": "png"
                })
                print(f"  âœ“ {img_path.name} â€” {wc} words [{method}]")
            else:
                ocr_zero_count += 1
                print(f"  âš  {img_path.name} â€” only {wc} words")
        except Exception as e:
            log.error(f"PNG load failed: {img_path.name}: {e}")
            print(f"  âœ— {img_path.name} â€” {e}")

    # â”€â”€ Text files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if txt_files:
        print(f"\nðŸ“ Processing text files ({len(txt_files)})...")
    for txt_path in txt_files:
        try:
            text = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                documents.append({
                    "text": text, "source": txt_path.name,
                    "page": 1, "type": "text"
                })
                print(f"  âœ“ {txt_path.name}")
        except Exception as e:
            log.error(f"Text load failed: {txt_path.name}: {e}")

    if ocr_zero_count:
        print(f"\n  âš  {ocr_zero_count} images returned 0 words.")
        print(f"    See logs/ocr_failures.log for details.")
        print(f"    Common fixes:")
        print(f"    â€¢ Run: python fix_tesseract.py")
        print(f"    â€¢ Use better-lit, sharper photos")

    log.info(f"Load complete: {len(documents)} documents, "
             f"{ocr_zero_count} OCR failures")
    print(f"\nâœ“ Total documents loaded: {len(documents)}")
    return documents


load_pdfs = load_documents   # backward-compat alias


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CHUNKING
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def chunk_documents(documents: list[dict],
                    chunk_size: int = 600,
                    chunk_overlap: int = 100) -> list[dict]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " "]
    )
    chunks = []
    for doc in documents:
        for i, part in enumerate(splitter.split_text(doc["text"])):
            if len(part.strip()) > 40:
                chunks.append({
                    "text": part.strip(), "source": doc["source"],
                    "page": doc["page"], "chunk_id": i
                })
    log.info(f"Chunking complete: {len(chunks)} chunks from {len(documents)} docs")
    return chunks


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# VECTOR STORE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def build_vectorstore(chunks: list[dict], persist_dir: str):
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    log.info(f"Building vector store: {len(chunks)} chunks â†’ {persist_dir}")
    print(f"\nBuilding vector store with {len(chunks)} chunks...")
    print("(First run downloads embedding model ~90 MB â€” one time only)")

    embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client   = chromadb.PersistentClient(path=persist_dir)
    try:
        client.delete_collection("science_books")
    except Exception:
        pass

    collection = client.create_collection(
        "science_books", embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"}
    )
    for i in range(0, len(chunks), 100):
        batch = chunks[i:i+100]
        collection.add(
            documents=[c["text"] for c in batch],
            metadatas=[{"source": c["source"], "page": str(c["page"]),
                        "chunk_id": str(c["chunk_id"])} for c in batch],
            ids=[f"chunk_{i+j}" for j in range(len(batch))]
        )
        print(f"  Indexed {min(i+100, len(chunks))}/{len(chunks)} chunks")

    log.info(f"Vector store built: {persist_dir}")
    print(f"âœ“ Vector store saved to {persist_dir}")
    return collection


def load_vectorstore(persist_dir: str):
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client   = chromadb.PersistentClient(path=persist_dir)
    log.info(f"Vector store loaded from {persist_dir}")
    return client.get_collection("science_books", embedding_function=embed_fn)


def retrieve(collection, query: str, n_results: int = 5) -> list[dict]:
    from src.logger import log_retrieval
    results = collection.query(
        query_texts=[query], n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )
    chunks = []
    for doc, meta, dist in zip(results["documents"][0],
                                results["metadatas"][0],
                                results["distances"][0]):
        chunks.append({
            "text":   doc,
            "source": meta.get("source", ""),
            "page":   meta.get("page", ""),
            "score":  round((1 - dist) * 100, 1)
        })
    log_retrieval(query, chunks)
    return chunks

