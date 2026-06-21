"""
fix_tesseract.py
Run this FIRST to check and fix Tesseract, then run ingest.py

Usage:  python fix_tesseract.py
"""
import os, sys, subprocess
from pathlib import Path

print("=" * 60)
print("  Tesseract Diagnostic & Fix")
print("=" * 60)

# ── 1. Check pytesseract module ──────────────────────────────
print("\n[1] pytesseract Python module...")
try:
    import pytesseract
    print("    ✓ Installed")
except ImportError:
    print("    ✗ NOT installed")
    print("    Run:  pip install pytesseract")
    sys.exit(1)

# ── 2. Find tesseract.exe ────────────────────────────────────
print("\n[2] Searching for tesseract.exe on this PC...")

search_locations = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
    r"C:\tools\Tesseract-OCR\tesseract.exe",
    os.path.join(os.environ.get("LOCALAPPDATA",""),
                 "Programs", "Tesseract-OCR", "tesseract.exe"),
    os.path.join(os.environ.get("USERPROFILE",""),
                 "AppData","Local","Programs","Tesseract-OCR","tesseract.exe"),
]

found = None
for loc in search_locations:
    if os.path.exists(loc):
        found = loc
        print(f"    ✓ Found: {loc}")
        break

# Also check PATH
if not found:
    try:
        result = subprocess.run(["where", "tesseract"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            found = result.stdout.strip().splitlines()[0]
            print(f"    ✓ Found in PATH: {found}")
    except Exception:
        pass

if not found:
    print("    ✗ tesseract.exe NOT FOUND anywhere on this PC")
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  SOLUTION: Install Tesseract OCR                ║")
    print("  ╠══════════════════════════════════════════════════╣")
    print("  ║  1. Open this link in your browser:             ║")
    print("  ║                                                  ║")
    print("  ║  https://github.com/UB-Mannheim/tesseract/wiki  ║")
    print("  ║                                                  ║")
    print("  ║  2. Click the download link for Windows 64-bit  ║")
    print("  ║     (file named tesseract-ocr-w64-setup-*.exe)  ║")
    print("  ║                                                  ║")
    print("  ║  3. Run the .exe installer                      ║")
    print("  ║     - Keep default install folder               ║")
    print("  ║     - Check 'Add to PATH' if shown              ║")
    print("  ║                                                  ║")
    print("  ║  4. CLOSE this Command Prompt window            ║")
    print("  ║     Open a NEW Command Prompt                   ║")
    print("  ║                                                  ║")
    print("  ║  5. Run:  python fix_tesseract.py  again        ║")
    print("  ╚══════════════════════════════════════════════════╝")
    sys.exit(1)

# ── 3. Set path and test it actually works ───────────────────
print("\n[3] Testing Tesseract works...")
pytesseract.pytesseract.tesseract_cmd = found

try:
    ver = pytesseract.get_tesseract_version()
    print(f"    ✓ Version: {ver}")
except Exception as e:
    print(f"    ✗ Found but not working: {e}")
    print("    Try reinstalling Tesseract")
    sys.exit(1)

# ── 4. Check English language data is installed ──────────────
print("\n[4] Checking English language data...")
try:
    langs = pytesseract.get_languages()
    print(f"    Available languages: {langs}")
    if "eng" in langs:
        print("    ✓ English (eng) is installed")
    else:
        print("    ✗ English language data NOT found!")
        print("    Reinstall Tesseract and select 'English' language during setup")
        sys.exit(1)
except Exception as e:
    print(f"    ⚠ Could not check languages: {e}")

# ── 5. Live OCR test on a real image ────────────────────────
print("\n[5] Running live OCR test...")
try:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 120), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "Computer Science", fill="black")
    draw.text((10, 60), "Input and Output", fill="black")
    text = pytesseract.image_to_string(img, config="--psm 6")
    words = len(text.strip().split())
    if words >= 3:
        print(f"    ✓ OCR working! Extracted: {text.strip()}")
    else:
        print(f"    ⚠ OCR ran but got few words: {repr(text)}")
except Exception as e:
    print(f"    ✗ OCR test failed: {e}")
    sys.exit(1)

# ── 6. Write the tesseract path into rag_engine permanently ──
print("\n[6] Saving Tesseract path into rag_engine.py...")
rag_path = Path(__file__).parent / "src" / "rag_engine.py"
if rag_path.exists():
    content = rag_path.read_text(encoding="utf-8")
    # Add a hard-coded path at the top of ocr_jpeg function
    old_line = 'import pytesseract\n        from PIL import Image\n\n        # On Windows, Tesseract is usually here'
    new_line = f'import pytesseract\n        from PIL import Image\n\n        # Hard-coded path found by fix_tesseract.py\n        pytesseract.pytesseract.tesseract_cmd = r"{found}"\n\n        # On Windows, Tesseract is usually here'
    if 'Hard-coded path found by fix_tesseract.py' not in content:
        content = content.replace(old_line, new_line)
        rag_path.write_text(content, encoding="utf-8")
        print(f"    ✓ Path saved: {found}")
    else:
        print(f"    ✓ Path already saved")
else:
    print(f"    ⚠ src/rag_engine.py not found at {rag_path}")
    print(f"    Manually set this at top of rag_engine.py:")
    print(f'    pytesseract.pytesseract.tesseract_cmd = r"{found}"')

# ── Done ─────────────────────────────────────────────────────
print()
print("=" * 60)
print("  ✅ Tesseract is installed and working!")
print("  Now run:  python ingest.py")
print("=" * 60)
