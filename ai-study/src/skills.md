# AI Study - Skills Definition

## Project Overview

AI Study is a local-first educational AI platform designed for school students. The system ingests textbook content from PDF and JPEG sources, converts them into structured knowledge, and provides AI-powered tutoring and exam preparation.

The platform operates entirely on local resources using OCR, RAG, ChromaDB, LangGraph agents, and local/open-source LLMs.

---

# Core Skills

## 1. Textbook Ingestion

### Capability

Read and process textbook content from:

* PDF files
* JPEG images
* PNG images
* Scanned textbook pages
* Mobile camera photographs

### Processing Pipeline

1. OCR extraction
2. Image preprocessing
3. OCR correction
4. Markdown conversion
5. Metadata generation
6. Semantic chunking
7. Embedding generation
8. Vector indexing

### Output

* Structured Markdown
* JSON metadata
* ChromaDB embeddings

---

# 2. OCR Enhancement

### Capability

Improve OCR accuracy for photographed textbook pages.

### Techniques

* Auto deskew
* Adaptive thresholding
* Noise reduction
* Contrast enhancement
* DPI scaling
* Multi-pass OCR
* OCR confidence scoring

### Quality Goal

Target OCR accuracy:

* Excellent: >98%
* Good: 95–98%
* Acceptable: 90–95%

---

# 3. Knowledge Extraction

### Capability

Transform textbook content into structured educational knowledge.

### Extract

* Chapters
* Topics
* Subtopics
* Definitions
* Important points
* Examples
* Exercises
* Question answers
* Diagrams and captions

### Output Structure

Chapter
→ Topic
→ Concept
→ Learning Content

---

# 4. Tutor Agent

## Purpose

Act as an intelligent textbook tutor.

### Skills

* Answer textbook questions
* Explain concepts
* Simplify difficult topics
* Provide examples
* Summarize chapters
* Create notes
* Generate revision material

### Restrictions

* Must answer only from retrieved textbook content
* Must refuse unsupported questions
* Must cite textbook context

### Workflow

Retrieve
→ Grade Context
→ Generate Answer
→ Verify Grounding

---

# 5. Exam Agent

## Purpose

Generate school-style examination papers.

### Skills

Generate:

* MCQs
* Fill in the blanks
* True/False
* Short questions
* Long questions
* Match the following
* Diagram-based questions

### Validation

Every question must:

* Exist in textbook content
* Match target difficulty
* Match class level
* Have answer key

---

# 6. Revision Assistant

### Skills

Generate:

* Chapter summaries
* Quick revision notes
* Last-minute preparation sheets
* Flash cards
* Important definitions

### Formats

* Bullet points
* Tables
* Question-answer
* Mind-map text

---

# 7. Learning Assessment

### Skills

Evaluate:

* Student answers
* Practice tests
* Mock exams

### Outputs

* Marks
* Feedback
* Improvement areas
* Suggested chapters for revision

---

# 8. Retrieval-Augmented Generation (RAG)

### Capability

Provide grounded responses using textbook content.

### Vector Store

* ChromaDB

### Retrieval Strategy

* Semantic search
* Metadata filtering
* Top-K retrieval
* Confidence scoring

### Safety

Reject answer generation if confidence threshold is below configured minimum.

---

# 9. Hallucination Prevention

### Rules

The system must:

* Answer only from textbook content
* Never invent facts
* Never create unsupported answers
* Refuse low-confidence responses

### Verification

* Context validation
* Retrieval score validation
* Grounding verification

---

# 10. Future Skills Roadmap

## Phase 2

* Bengali language support
* Handwritten note ingestion
* Diagram understanding
* Image-to-explanation generation
* Parent dashboard
* Progress tracking

## Phase 3

* Personalized learning paths
* Adaptive testing
* Voice tutor
* Interactive quizzes
* Multi-subject learning graph

---

# Technical Stack

## OCR

* Tesseract OCR
* EasyOCR (planned)
* PaddleOCR (planned)

## RAG

* LangChain
* ChromaDB
* Sentence Transformers

## Agent Framework

* LangGraph
* MemorySaver

## LLM

* Ollama / Local LLM
* Open-source models

## Storage

* Markdown Store
* JSON Metadata Store
* ChromaDB Vector Store

---

# Success Criteria

The system is considered successful when:

1. OCR accuracy exceeds 95%.
2. Retrieval precision exceeds 90%.
3. Hallucination rate remains below 5%.
4. Tutor responses are grounded in textbook content.
5. Exam questions accurately reflect textbook material.
6. Student receives age-appropriate explanations for Class 5 curriculum.
7. Entire system operates locally without dependency on paid APIs.
