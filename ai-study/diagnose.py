"""
diagnose.py — Run this to find out exactly why JPEG OCR is failing.

Usage:
    python diagnose.py
    python diagnose.py "study_materials\\page1.jpg"   (test a specific file)
"""

import sys
import os

print("=" * 60)
print("  AI Study — JPEG OCR Diagnostics")
print("=" * 60)

all_ok = True

# ── Check 1: Pillow ──────────────────────────────────────────
print("\n[1/5] Checking Pillow (image processing)...")
try:
    from PIL import Image, ImageFilter, ImageEnhance
    print("      ✓ Pillow is installed")
except ImportError:
    print("      ✗ Pillow NOT installed")
    print("        Fix: pip install Pillow")
    all_ok = False

# ── Check 2: pytesseract Python module ──────────────────────
print("\n[2/5] Checking pytesseract Python module...")
try:
    import pytesseract
    print("      ✓ pytesseract module is installed")
except ImportError:
    print("      ✗ pytesseract NOT installed")
    print("        Fix: pip install pytesseract")
    all_ok = False

# ── Check 3: Tesseract binary ────────────────────────────────
print("\n[3/5] Checking Tesseract OCR binary...")
tesseract_found = False

# Common Windows install locations
windows_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe".format(
        os.environ.get("USERNAME", "user")
    ),
    r"C:\Tesseract-OCR\tesseract.exe",
]

for path in windows_paths:
    if os.path.exists(path):
        print(f"      ✓ Found at: {path}")
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = path
        tesseract_found = True
        break

if not tesseract_found:
    # Try PATH
    try:
        import pytesseract
        ver = pytesseract.get_tesseract_version()
        print(f"      ✓ Found in system PATH, version: {ver}")
        tesseract_found = True
    except Exception as e:
        print("      ✗ Tesseract binary NOT found anywhere")
        print()
        print("      THIS IS THE MOST COMMON CAUSE OF JPEG OCR FAILURE")
        print()
        print("      Fix — Install Tesseract:")
        print("        1. Go to: https://github.com/UB-Mannheim/tesseract/wiki")
        print("        2. Download the Windows installer (.exe)")
        print("        3. Install it (default path is fine)")
        print("        4. During install, check 'Add to PATH'")
        print("        5. RESTART Command Prompt after installing")
        print("        6. Run this script again to verify")
        all_ok = False

if tesseract_found:
    try:
        import pytesseract
        ver = pytesseract.get_tesseract_version()
        print(f"      ✓ Tesseract version: {ver}")
    except Exception as e:
        print(f"      ⚠ Found but version check failed: {e}")

# ── Check 4: Can it actually OCR a test image? ───────────────
print("\n[4/5] Testing OCR on a sample image...")
if all_ok or tesseract_found:
    try:
        from PIL import Image, ImageDraw
        import pytesseract

        # Create test image
        img = Image.new("RGB", (500, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "Computer", fill="black")
        draw.text((20, 70), "Input Output", fill="black")
        test_path = os.path.join(os.path.dirname(__file__), "_test_ocr.jpg")
        img.save(test_path, "JPEG")

        text = pytesseract.image_to_string(img, config="--psm 6")
        words = len(text.strip().split())

        # Clean up
        try: os.remove(test_path)
        except: pass

        if words >= 2:
            print(f"      ✓ OCR working — extracted {words} words: {text.strip()[:60]}")
        else:
            print(f"      ⚠ OCR ran but only got {words} word(s): {repr(text[:60])}")
            print("        Tesseract may be installed but language data is missing")
            print("        Fix: reinstall Tesseract and ensure 'English' language is selected")
            all_ok = False

    except Exception as e:
        print(f"      ✗ OCR test failed: {type(e).__name__}: {e}")
        all_ok = False
else:
    print("      ⏭ Skipped (fix Tesseract first)")

# ── Check 5: Test on a user-provided JPEG ────────────────────
print("\n[5/5] Testing on your actual JPEG file...")
if len(sys.argv) > 1:
    test_file = sys.argv[1]
    if os.path.exists(test_file):
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from src.rag_engine import ocr_jpeg
            text, method = ocr_jpeg(test_file)
            words = len(text.split()) if text else 0
            print(f"      File    : {test_file}")
            print(f"      Method  : {method}")
            print(f"      Words   : {words}")
            print(f"      Preview : {text[:200]}")
            if words >= 5:
                print("      ✓ Your JPEG file OCR is working!")
            else:
                print("      ⚠ Low word count — see image quality tips below")
                all_ok = False
        except Exception as e:
            print(f"      ✗ Failed on your file: {type(e).__name__}: {e}")
            all_ok = False
    else:
        print(f"      ✗ File not found: {test_file}")
else:
    print("      ⏭ No file provided. To test your JPEG run:")
    print(r'         python diagnose.py "study_materials\yourfile.jpg"')

# ── Summary ──────────────────────────────────────────────────
print()
print("=" * 60)
if all_ok:
    print("  ✅ All checks passed! JPEG OCR should work.")
    print("     Run: python ingest.py")
else:
    print("  ❌ Issues found — fix the items marked ✗ above.")
    print()
    print("  Image quality tips for better OCR results:")
    print("   • Use good lighting — no shadows on the page")
    print("   • Keep camera directly above, not at an angle")
    print("   • Minimum 1 MB file size (higher resolution = better)")
    print("   • Text should be horizontal, not tilted")
    print("   • Avoid glare/reflections on glossy pages")
print("=" * 60)
