---
name: external-agent-skills
description: Approved external agent-skill routing for AI Study: PDF/doc ingestion, RAG evaluation notebooks, Python testing, and security review.
category: tool
---

# External Agent Skills

Use this skill when improving AI Study with external agent-skill guidance from
the awesome-agent-skills catalog.

## Approved Skill Families

- OpenAI: `openai/doc`, `openai/pdf`, `openai/jupyter-notebook`,
  `openai/security-best-practices`, `openai/security-threat-model`
- Trail of Bits: `trailofbits/property-based-testing`,
  `trailofbits/modern-python`, `trailofbits/static-analysis`,
  `trailofbits/insecure-defaults`
- Hugging Face: `huggingface/hugging-face-datasets`,
  `huggingface/hugging-face-evaluation`
- Redis: `redis/redis-development` only for a deliberate future move from
  ChromaDB to Redis vector search

## When To Use

- PDF and document ingestion checks.
- OCR benchmark notebooks.
- Retrieval-quality and hallucination-rate evaluation.
- Exam generation invariants, mark allocation, and duplicate detection.
- Local file handling, path safety, upload limits, and Groq opt-in review.

## Do Not Use

- Do not make paid APIs mandatory.
- Do not weaken the offline-first default.
- Do not send textbook context to external providers without explicit opt-in.
- Do not answer outside retrieved textbook context.

