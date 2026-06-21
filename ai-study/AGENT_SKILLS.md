# Agent Skills For AI Study

Source catalog: https://github.com/VoltAgent/awesome-agent-skills/tree/main

This project is a local-first Class 5 study assistant using OCR, RAG,
ChromaDB, LangGraph, Streamlit, Ollama/Groq, and hallucination guards. Use
external agent skills only when they improve document ingestion, OCR/RAG
evaluation, testing, or local safety.

## Approved Skills

### OpenAI Document And Evaluation Skills

- `openai/doc`
- `openai/pdf`
- `openai/jupyter-notebook`
- `openai/security-best-practices`
- `openai/security-threat-model`

Use doc/pdf skills for textbook ingestion, page extraction checks, generated
study material, and exam-pack exports. Use notebook skills for OCR benchmarks,
retrieval-quality evaluation, grounding metrics, and hallucination-rate reports.
Use security skills for local file handling, upload limits, path validation,
prompt/context leakage, and Groq opt-in review.

### Testing And Python Quality

- `trailofbits/property-based-testing`
- `trailofbits/modern-python`
- `trailofbits/static-analysis`
- `trailofbits/insecure-defaults`

Use these for OCR normalization, chunking, retrieval confidence thresholds,
exam mark allocation, duplicate-question detection, file path safety, and
fallback-provider behavior.

### Hugging Face

- `huggingface/hugging-face-datasets`
- `huggingface/hugging-face-evaluation`

Use only for local or explicitly approved evaluation datasets, OCR benchmarks,
and model/embedding comparison. Keep the project offline-first by default.

### Optional Future Vector Store

- `redis/redis-development`

Use only if the project intentionally moves from local ChromaDB to Redis vector
search. Do not introduce Redis as a casual dependency.

## Project Guardrails

- Preserve the free/offline-first design.
- Do not require paid APIs for core tutor or exam workflows.
- Treat Groq as opt-in because textbook context leaves the machine.
- Keep answers grounded in retrieved textbook content.
- Refuse unsupported questions instead of inventing facts.
- Add file-size, page-count, and path-safety checks before accepting broader
  user uploads.

