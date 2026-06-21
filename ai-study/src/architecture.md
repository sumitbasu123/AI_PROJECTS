# AI Study - System Architecture

## Overview

AI Study is a local-first educational AI platform designed to transform textbook images and PDFs into an intelligent tutoring and examination system.

The platform uses OCR, Retrieval Augmented Generation (RAG), LangGraph agents, and local LLMs to provide grounded educational assistance.

---

# High Level Architecture

```text
                     ┌─────────────────┐
                     │ PDF / JPEG Book │
                     └────────┬────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │ Document Ingestion  │
                   └────────┬────────────┘
                            │
                            ▼
                   ┌─────────────────────┐
                   │ OCR Processing      │
                   │ Tesseract/EasyOCR   │
                   └────────┬────────────┘
                            │
                            ▼
                   ┌─────────────────────┐
                   │ OCR Correction      │
                   └────────┬────────────┘
                            │
                            ▼
                   ┌─────────────────────┐
                   │ Markdown Generator  │
                   └────────┬────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼

      markdown_store/            metadata_store/

               │
               ▼
       ┌──────────────────┐
       │ Semantic Chunker │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Embedding Engine │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ ChromaDB         │
       └────────┬─────────┘
                │
        ┌───────┴──────────┐
        ▼                  ▼

 Tutor Agent          Exam Agent
```

---

# Component Architecture

## Ingestion Layer

### Responsibility

Convert textbook pages into machine-readable content.

### Input

* PDF
* JPG
* PNG
* Scanned images

### Output

* Markdown
* JSON metadata

---

# OCR Layer

## Current

* Tesseract OCR

## Future

* EasyOCR
* PaddleOCR
* Vision-based extraction

## Preprocessing

* Deskew
* Denoise
* Adaptive thresholding
* Perspective correction
* DPI normalization

---

# Knowledge Layer

## Markdown Store

Purpose:

Store structured textbook content.

Example:

```markdown
# Chapter 1

## Water Cycle

The water cycle is...
```

---

# Metadata Store

Purpose:

Store document metadata.

Example:

```json
{
  "chapter":"Water Cycle",
  "page":12,
  "subject":"Science",
  "grade":"Class 5"
}
```

---

# RAG Layer

## Chunking Strategy

Hierarchy:

Chapter
→ Topic
→ Concept

Chunk Size Target:

300-600 tokens

Overlap:

50-100 tokens

---

## Embedding Layer

Current Candidate Models

* BAAI/bge-small-en
* all-MiniLM-L6-v2
* nomic-embed-text

Recommended

BAAI/bge-small-en-v1.5

---

## Vector Database

ChromaDB

Stores:

* Chunk text
* Metadata
* Embeddings

---

# Tutor Agent

Framework:

LangGraph

Workflow:

START
→ Retrieve
→ Grade Context
→ Generate Answer
→ Verify
→ END

Fallback:

Rewrite Query
→ Retrieve Again

Maximum retries:

2

---

# Exam Agent

Framework:

LangGraph

Workflow:

START
→ Plan Exam
→ Generate Questions
→ Validate
→ Generate Answer Key
→ END

Validation:

* Marks check
* Difficulty check
* Textbook grounding check

---

# Memory Layer

Framework:

MemorySaver

Stores:

* Conversation history
* Student preferences
* Session context

Scope:

Per student session

---

# LLM Layer

Supported Models

## Small

* Gemma 3
* Phi 4 Mini

## Medium

* Qwen 3 8B
* Llama 3 8B

## Recommended

Qwen 3 8B

Best balance of:

* Accuracy
* Speed
* Educational reasoning

---

# Logging Layer

Logs

logs/

Contains:

* OCR failures
* Retrieval failures
* Hallucination guard
* Agent execution traces

---

# Security Principles

* Local-first processing
* No student data leaves device
* No paid API dependency
* Offline operation supported

---

# Future Architecture

Phase 2

Add:

* Diagram understanding
* Image captioning
* Bengali OCR

Phase 3

Add:

* Voice tutor
* Parent dashboard
* Learning analytics

Phase 4

Add:

* Multi-grade support
* Adaptive learning engine
* Personalized curriculum generation
