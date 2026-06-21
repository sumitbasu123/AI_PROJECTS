# Structured Ingestion Pipeline — Upgrade Notes

## Scanned PDF Pipeline

```text
Scanned PDF
  -> PyMuPDF page rendering (300 DPI)
  -> PaddleOCR
  -> Docling (default) or Marker
  -> Markdown
  -> section-aware semantic chunking
  -> SentenceTransformer embeddings
  -> ChromaDB
  -> Tutor and exam agents
```

Recommended Python 3.11 setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_python311.ps1
.\.venv311\Scripts\Activate.ps1
python ingest.py --pdf-converter docling
```

Use `--pdf-converter auto`, `docling`, `marker`, or `builtin`.

## What Changed

The old `ingest.py` converted scanned images directly into raw text chunks and
stored them in ChromaDB. The upgraded pipeline adds three intermediate stages
that produce structured, reusable artifacts before building the vector store.

---

## New Pipeline (5 stages)

```
Your JPEG / PDF files  (`study_materials/` or `STUDY_SOURCE_DIR`)
          │
          ▼  Stage 1 — OCR  (unchanged 6-variant engine, run ONCE per file)
    ┌─────────────┐
    │  Tesseract  │  6 variants × 4 PSM modes, picks best result
    └──────┬──────┘
           │ raw text per page
           ▼  Stage 2 — Markdown conversion
    ┌──────────────────────┐
    │  Text → Markdown     │  Detects headings, lists, definitions
    │  Structuring         │  Adds page metadata as HTML comments
    └──────┬───────────────┘
           │ structured .md
           ▼  Stage 3 — Object Storage  (local filesystem)
    ┌──────────────────────┐
    │  markdown_store/     │  One .md + .json per source file
    │  <stem>.md           │  Fingerprint cache — skip unchanged files
    │  <stem>.json         │
    └──────┬───────────────┘
           │ stored markdown
           ▼  Stage 4 — Semantic Chunking
    ┌──────────────────────┐
    │  Section-aware       │  Splits on ## / ### headings, not char count
    │  Chunker             │  Preserves heading context in every chunk
    │                      │  Overlap carries across section boundaries
    └──────┬───────────────┘
           │ rich chunk dicts
           ▼  Stage 5 — Embeddings
    ┌──────────────────────┐
    │  ChromaDB            │  Same as before, now with richer metadata:
    │  all-MiniLM-L6-v2   │  source, page, section, doc_type, fingerprint
    └──────────────────────┘
           │
    RAG retrieval (tutor / exam agents unchanged)
```

---

## New Files

| File | Purpose |
|------|---------|
| `src/structured_ingest.py` | Full 5-stage pipeline |
| `ingest.py` | Updated entry point (same command as before) |
| `src/__init__.py` | Updated exports |
| `markdown_store/` | Auto-created: one .md + .json per source file |

---

## Storage Layout After Running

```
project_root/
├── markdown_store/
│   ├── chapter1.md          ← structured Markdown (human-readable!)
│   ├── chapter1.json        ← metadata sidecar
│   ├── page_scan_01.md
│   ├── page_scan_01.json
│   └── ...
│
└── vectorstore/             ← ChromaDB (same location as before)
```

---

## How to Run

Exactly the same command as before:

```cmd
cd "path\to\ai-study"
python ingest.py
```

Optional flags:

```cmd
# Use a different source folder
python ingest.py --source "C:\my\other\books"

# Force re-process all files (ignore cache)
python ingest.py --force
```

---

## Key Improvements

### 1. OCR runs only once per file
The Markdown is saved to `markdown_store/`. On the next run, if the source file
hasn't changed (SHA-1 fingerprint match), the cached Markdown is used directly —
no re-OCR.

### 2. Structured Markdown is human-readable
Open any `.md` file in `markdown_store/` to inspect what the system "sees".
This makes it easy to spot OCR errors or add manual corrections without
re-running OCR.

### 3. Semantic chunking respects document structure
Old approach: fixed character-count splits (may cut mid-sentence or mid-topic).
New approach: splits on `##` / `###` headings, so each chunk maps to a natural
section of the textbook. Every chunk carries its section heading as context.

### 4. Richer metadata in vector store
Each chunk now stores: `source`, `page`, `section`, `doc_type`, `total_pages`,
`fingerprint`. The tutor agent can reference the exact section name when citing
the textbook.

### 5. Manual corrections are easy
To fix bad OCR on a specific file:
1. Edit `markdown_store/<stem>.md` directly
2. Run `python ingest.py` — it will see the .md already exists and re-chunk
   from your corrected version (without re-OCR)

To force a full re-OCR of everything: `python ingest.py --force`

---

## Backward Compatibility

- `app.py`, `tutor_agent.py`, `exam_agent.py` do **not** need changes.
- `rag_engine.py` is unchanged. Its `retrieve()` function still works.
- The new `structured_ingest.retrieve()` is a drop-in replacement that also
  returns a `section` field in each result chunk.
- The ChromaDB collection name (`science_books`) is unchanged.
