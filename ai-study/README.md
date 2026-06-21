# AI Study

An offline-first, textbook-grounded study assistant built with Streamlit, OCR, retrieval-augmented generation, and LangGraph.

## Features

- Ingests photographed pages, PDFs, Markdown, and text notes.
- Uses a multi-stage OCR pipeline with deskewing, dewarping, layout extraction, and quality checks.
- Builds a local ChromaDB vector store with sentence-transformer embeddings.
- Answers through a corrective RAG tutor with confidence and grounding gates.
- Generates structured exam papers and validates mark totals.
- Supports Ollama locally, optional Groq, and a no-LLM fallback.
- Logs OCR failures and hallucination-guard decisions for transparency.

## Architecture

```text
study material -> OCR and layout extraction -> Markdown
               -> chunking and embeddings -> ChromaDB
               -> tutor/exam LangGraph agents -> Streamlit UI
```

The ingestion pipeline lives in `src/structured_ingest.py`, retrieval in `src/rag_engine.py`, agent workflows in `src/tutor_agent.py` and `src/exam_agent.py`, and the interface in `app.py`.

## Quick start

Requires Python 3.11 and, for image OCR, a local Tesseract installation.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Place learning material in `study_materials/` or set `STUDY_SOURCE_DIR` to another local folder:

```powershell
$env:STUDY_SOURCE_DIR="C:\path\to\study-materials"
python ingest.py
python -m streamlit run app.py
```

For fully local generation, install Ollama and pull a small model:

```powershell
ollama pull gemma2:2b
```

Groq is optional and should be configured only through the environment:

```powershell
$env:GROQ_API_KEY="your-key"
```

## Privacy

Textbooks, extracted Markdown, embeddings, vector databases, logs, generated exams, and API keys remain local and are excluded from Git. Do not upload copyrighted learning material unless you have permission to distribute it.

## Responsible use

Grounding checks reduce unsupported answers but do not guarantee correctness. A learner or guardian should verify important answers against the original material.

## License

MIT
