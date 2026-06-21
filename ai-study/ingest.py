"""
ingest.py — 11-Stage Ingestion Pipeline Entry Point

Stages:
  1  Page Crop       — detect and crop to the page inside a phone photo
  2  Deskew          — fix rotation from tilted camera
  3  Dewarp          — correct book-spine curve / perspective warp
  4  OCR             — PyMuPDF page images -> PaddleOCR -> fallback OCR
  5  OCR Correction  — LLM fixes garbled OCR text
  6  Layout Extract  — Docling -> Marker -> built-in layout fallback
  7  Markdown        — save structured .md + .json to markdown_store/
  8  Synthetic QA    — generate Q&A pairs to boost RAG retrieval
  9  Chunk           — semantic splits on Markdown section boundaries
  10 Embed           — SentenceTransformer all-MiniLM-L6-v2
  11 ChromaDB        — persist vector store

Usage:
    python ingest.py
    python ingest.py --source "C:/my/books"
    python ingest.py --force
    python ingest.py --no-qa
    python ingest.py --no-llm-correction
    python ingest.py --pdf-converter docling
    python ingest.py --force --no-qa --no-llm-correction   (fastest)
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="AI Study — 11-stage ingestion pipeline"
    )
    parser.add_argument(
        "--source", default=None,
        help=("Folder containing book files "
              "(default: ./study_materials or STUDY_SOURCE_DIR env var)")
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-process even if Markdown is already cached"
    )
    parser.add_argument(
        "--no-qa", action="store_true",
        help="Skip synthetic QA generation (Stage 8) — faster"
    )
    parser.add_argument(
        "--no-llm-correction", action="store_true",
        help="Skip LLM OCR correction (Stage 5) — faster, needs no Ollama/Groq"
    )
    parser.add_argument(
        "--pdf-converter",
        choices=["auto", "docling", "marker", "builtin"],
        default="auto",
        help="PDF-to-Markdown converter (default: Docling, then Marker fallback)",
    )
    args = parser.parse_args()

    try:
        from src.structured_ingest import run_pipeline
    except ImportError as e:
        print(f"\nImport error: {e}")
        print("Run this from the project root folder:")
        print("    cd path/to/ai-study")
        print("    python ingest.py")
        sys.exit(1)

    try:
        summary = run_pipeline(
            source_dir          = args.source,
            force_reprocess     = args.force,
            use_llm_correction  = not args.no_llm_correction,
            generate_qa         = not args.no_qa,
            pdf_converter       = args.pdf_converter,
        )
        if summary.get("errors", 0) and summary.get("chunks", 0) == 0:
            sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
