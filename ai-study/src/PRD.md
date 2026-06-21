# AI Study Product Requirements Document

**Product:** AI Study  
**Current domain:** Class 5 Computer Science  
**Document status:** Current-state baseline and forward product specification  
**Last updated:** 2026-06-14

## 1. Product Summary

AI Study is a local-first learning application that converts textbook PDFs,
scans, and photographs into a searchable knowledge base. It gives a student:

- A textbook-grounded conversational tutor.
- A configurable 50-mark or 100-mark examination generator.
- Monitoring for OCR quality, retrieval quality, and hallucination controls.
- A background DREAM process that strengthens weak knowledge coverage while
  the application is idle.

The product is designed to work without paid APIs. Ollama is the preferred
local language model provider, Groq is an optional cloud fallback, and a
rule-based textbook-excerpt mode remains available when no LLM is reachable.

## 2. Problem Statement

School textbooks are often available only as scanned PDFs or phone
photographs. Conventional chatbots cannot reliably answer from those books,
may invent facts, and often require paid cloud services. Students and parents
need a simple system that:

1. Reads imperfect textbook images.
2. Preserves inspectable source content.
3. Answers only when the textbook provides adequate evidence.
4. Produces age-appropriate revision and assessment material.
5. Runs privately and affordably on a home computer.

## 3. Vision

Create a trustworthy, local educational platform that can ingest a student's
curriculum, teach from it, generate assessments, identify knowledge coverage
gaps, and progressively improve its study material without sending student
data to a paid service.

## 4. Goals

### 4.1 Product Goals

- Make textbook ingestion usable for PDFs, JPG/JPEG, PNG, TXT, and Markdown.
- Keep generated answers grounded in retrieved textbook content.
- Present explanations suitable for a Class 5 student.
- Generate complete school-style question papers with answer keys.
- Make OCR and AI failures visible through logs and monitoring.
- Support an offline path from ingestion through tutoring.
- Preserve structured Markdown and metadata for human inspection and repair.

### 4.2 Quality Goals

| Area | Target |
|---|---:|
| OCR accuracy on benchmark pages | Greater than 95% |
| Retrieval precision on curated questions | Greater than 90% |
| Grounded tutor response rate | Greater than 95% |
| Valid exam questions traceable to source | Greater than 95% |
| Typical tutor response time after warm-up | Less than 5 seconds |
| Mandatory paid API cost | INR 0 |

### 4.3 Non-Goals for the Current Release

- General-purpose web search or open-domain tutoring.
- Teacher-grade automated scoring of free-form student answers.
- Cloud synchronization across devices.
- Mobile-native applications.
- Production multi-user authentication and authorization.
- Guaranteed diagram understanding, handwriting recognition, or multilingual
  OCR.

## 5. Users and Personas

### 5.1 Primary Student

A Class 5 student who wants simple explanations, textbook citations, revision
help, and practice examinations.

**Needs:** low-friction questions, readable answers, safe refusals, visible
sources, and predictable exam formats.

### 5.2 Parent or Guardian

Sets up the application, adds textbook files, monitors failures, and generates
practice papers.

**Needs:** straightforward setup, no recurring cost, understandable logs, and
confidence that answers are tied to the textbook.

### 5.3 Maintainer

Installs OCR and model dependencies, runs ingestion, diagnoses failures, and
extends the codebase.

**Needs:** modular architecture, inspectable artifacts, configurable paths,
diagnostic tools, stable data contracts, and technical documentation.

## 6. Product Scope

### 6.1 Ingestion and Knowledge Base

The system shall:

- Recursively discover supported source files.
- Crop, deskew, and dewarp photographed pages where possible.
- Render scanned PDF pages at configurable DPI.
- Attempt PaddleOCR, Surya, and Tesseract according to availability and input.
- Optionally correct OCR text through Ollama or Groq.
- Convert content to structured Markdown using Docling, Marker, or the built-in
  converter.
- Store Markdown, metadata JSON, and optional synthetic QA JSON in
  `markdown_store/`.
- Cache by source fingerprint and skip unchanged files unless forced.
- Split content by Markdown sections with overlap and quality filtering.
- Embed chunks with `all-MiniLM-L6-v2`.
- Rebuild the `science_books` ChromaDB collection.

### 6.2 Tutor

The tutor shall:

- Accept natural-language questions.
- Retrieve the five most relevant chunks.
- Rewrite weak queries up to two times.
- Refuse answers below the configured retrieval confidence gate.
- Try Ollama first, then Groq, then direct textbook excerpts.
- Apply a lexical grounding check to generated LLM answers.
- Replace an insufficiently grounded answer with textbook excerpts.
- Return source file, page, and match score.
- Maintain LangGraph conversation state by Streamlit session ID.

### 6.3 Exam Generator

The exam generator shall:

- Accept 50-mark and 100-mark paper requests.
- Optionally focus on a chapter or topic.
- Retrieve diverse source topics.
- Generate MCQ, short-answer, application, and long-answer questions according
  to the configured mark distribution.
- Include answer and hint fields for each question.
- Validate the total marks and retry adjustment up to two times.
- Group questions by section.
- Allow the paper to be downloaded as text.

### 6.4 Monitoring

The application shall expose:

- Total question activity.
- OCR zero-word failures and low-word warnings.
- Hallucination guard events.
- Low-retrieval warnings.
- Recent application logs.
- Download access to available log files.
- Current LLM availability.

### 6.5 DREAM Background Learning

While the student is inactive, the system shall:

- Probe curriculum questions for weak retrieval coverage.
- Locate related sections in the Markdown store.
- Generate and add QA chunks for weak topics.
- Add QA pairs for thin Markdown sections.
- Periodically remove near-duplicate DREAM chunks.
- Persist newly generated section QA to sidecar files.
- Pause or reset its idle timer when tutor or exam activity occurs.
- Expose thread-safe status to the Streamlit DREAM tab.

## 7. Primary User Journeys

### 7.1 Build the Knowledge Base

1. The parent places textbook files in the configured source directory.
2. The maintainer runs `python ingest.py`.
3. The pipeline creates inspectable Markdown and metadata artifacts.
4. Quality chunks are embedded into ChromaDB.
5. The command reports processed, cached, failed, and indexed counts.

### 7.2 Ask the Tutor

1. The student opens the Tutor tab.
2. The student submits a question.
3. The agent retrieves and grades textbook context.
4. Weak context triggers query rewriting and another retrieval.
5. The LLM layer gates, answers, and verifies grounding.
6. The UI displays the answer, source list, and engine used.

### 7.3 Generate an Exam

1. The user selects 50 or 100 marks and an optional chapter.
2. The exam graph plans the required question mix.
3. Questions are generated from retrieved textbook topic statements.
4. The graph validates and adjusts the total marks.
5. The UI renders sections and optionally reveals answers.
6. The user downloads the paper as a text file.

### 7.4 Improve Coverage While Idle

1. The app starts one DREAM engine per Streamlit session.
2. Student activity resets the idle timer.
3. After the configured idle period, DREAM scans for weak topics.
4. It enriches ChromaDB and section QA sidecars.
5. The DREAM tab displays progress and allows pause or restart.

## 8. Functional Requirements

### 8.1 Ingestion

- **FR-ING-01:** Support `.pdf`, `.jpg`, `.jpeg`, `.png`, `.txt`, and `.md`.
- **FR-ING-02:** Preserve source, page, section, document type, fingerprint, and
  total page metadata on indexed chunks.
- **FR-ING-03:** A matching source fingerprint shall produce a cache hit.
- **FR-ING-04:** `--force` shall bypass the fingerprint cache.
- **FR-ING-05:** `--no-qa` and `--no-llm-correction` shall disable optional
  stages.
- **FR-ING-06:** `--pdf-converter` shall support `auto`, `docling`, `marker`,
  and `builtin`.
- **FR-ING-07:** A failed source file shall not stop processing other files.
- **FR-ING-08:** The pipeline shall not build a vector store when no valid
  chunks are produced.

### 8.2 Tutor

- **FR-TUT-01:** Questions shall be processed by the compiled tutor graph.
- **FR-TUT-02:** Retrieval shall return text, source, page, section, and score.
- **FR-TUT-03:** The tutor shall attempt no more than two query rewrites.
- **FR-TUT-04:** Low-confidence questions shall receive a safe refusal.
- **FR-TUT-05:** Unsupported LLM output shall be replaced with source excerpts.
- **FR-TUT-06:** The response shall identify the serving engine.
- **FR-TUT-07:** Conversation memory shall be scoped by session/thread ID.

### 8.3 Exam

- **FR-EXM-01:** The graph shall use predefined mark distributions for 50 and
  100 marks.
- **FR-EXM-02:** Every generated question shall include type and marks.
- **FR-EXM-03:** MCQs shall include four options and an answer.
- **FR-EXM-04:** Total marks shall be validated before presentation.
- **FR-EXM-05:** The UI shall support an optional answer-key view.

### 8.4 Operations

- **FR-OPS-01:** Logs shall rotate to avoid unbounded file growth.
- **FR-OPS-02:** OCR and guard events shall be written to dedicated logs.
- **FR-OPS-03:** Diagnostics shall verify Pillow, pytesseract, the Tesseract
  binary, English language data, and a live OCR sample.
- **FR-OPS-04:** The application shall clearly instruct the user to run
  ingestion when the vector store is absent.

## 9. Non-Functional Requirements

### 9.1 Privacy and Security

- Local processing is the default.
- Groq use is opt-in through `GROQ_API_KEY`.
- Student questions and textbook content shall not be sent to cloud providers
  unless the operator configures a cloud provider.
- Secrets shall be read from environment variables and never committed.
- Logs should avoid storing unnecessary personal data.

### 9.2 Reliability

- Optional engines shall fail gracefully to the next available engine.
- Cached Markdown shall remain readable and manually correctable.
- Background DREAM failures shall be logged without crashing the UI.
- A single source-file ingestion failure shall be isolated.

### 9.3 Maintainability

- Agent state contracts shall remain explicit `TypedDict` models.
- UI code shall call public module functions rather than internal helpers.
- Retrieval results shall use one documented schema across tutor and exam
  modules.
- Configuration currently expressed as constants should migrate to a single
  configuration module.

### 9.4 Compatibility

- Primary development platform: Windows.
- Recommended scanned-PDF environment: Python 3.11.
- Core packages are listed in `requirements.txt`.
- PaddleOCR/Docling and Marker remain separately installable profiles.

## 10. Data and Content Requirements

### 10.1 Source Artifact

Each source should produce:

- `<stem>.md`: structured, human-readable textbook content.
- `<stem>.json`: source fingerprint and ingestion metadata.
- `<stem>.qa.json`: synthetic and DREAM-generated QA pairs when available.

### 10.2 Vector Chunk

Each vector record must contain:

```json
{
  "text": "Chunk text",
  "source": "chapter1.pdf",
  "page": "3",
  "section": "Input Devices",
  "chunk_id": "12",
  "doc_type": "pdf",
  "total_pages": "20",
  "fingerprint": "abc123def456"
}
```

### 10.3 Generated Question

```json
{
  "type": "mcq",
  "marks": 1,
  "question": "Which device is used for input?",
  "options": ["A) Monitor", "B) Keyboard", "C) Printer", "D) Speaker"],
  "answer": "B",
  "hint": "Think about typing.",
  "section_label": "Section A - Multiple Choice"
}
```

## 11. Success Measurement

- Maintain a reviewed OCR benchmark set of representative pages.
- Maintain a retrieval evaluation set of textbook questions with expected
  pages/sections.
- Sample tutor answers for factual correctness, readability, and citation.
- Validate generated exams for marks, duplicate questions, source grounding,
  and age appropriateness.
- Track confidence-gate and grounding-fallback rates over time.
- Track ingestion duration, cache-hit rate, and average response latency.

## 12. Acceptance Criteria

The current release is acceptable when:

1. A supported textbook file can be ingested into Markdown and ChromaDB.
2. Re-running ingestion on unchanged files uses the cache.
3. A known textbook question returns an answer with at least one source.
4. An unrelated question is refused or answered only with safe fallback text.
5. A 50-mark and a 100-mark paper can be generated and downloaded.
6. Monitoring displays log-derived counters without crashing.
7. The application remains usable when Ollama and Groq are unavailable.
8. DREAM can start, report status, react to activity, and stop cleanly.

## 13. Known Product Risks

- The current exam LLM path calls `ask_llm` with an empty context, so the
  confidence gate can block LLM-based question construction; rule-based
  fallbacks currently keep generation working.
- Exam replan can insert a hard-coded natural-resources question that may not
  belong to the Computer Science textbook.
- Retrieval thresholds differ between the tutor graph and the LLM confidence
  gate.
- DREAM writes generated QA into the live vector store without a separate
  human approval stage.
- The Streamlit app mixes presentation and orchestration in one large module.
- There is no automated test suite or formal evaluation harness in the current
  repository.
- Some documentation and source comments contain legacy encoding artifacts.

## 14. Roadmap Priorities

### P0 - Trust and Correctness

- Fix exam generation so all LLM prompts receive grounded source context.
- Remove hard-coded off-domain replan questions.
- Add automated unit, graph, ingestion, and retrieval evaluation tests.
- Add provenance and approval controls for DREAM-generated chunks.

### P1 - Architecture and Operations

- Centralize configuration and paths.
- Separate Streamlit views from service orchestration.
- Add structured event metrics instead of deriving all counters from log text.
- Add deterministic schemas and validation for LLM JSON output.

### P2 - Learning Features

- Revision notes and flashcards.
- Student answer assessment and progress tracking.
- Adaptive difficulty and targeted practice.
- Parent and teacher dashboards.

### P3 - Multimodal and Curriculum Expansion

- Diagram understanding and visual question answering.
- Bengali and Hindi support.
- Multi-grade, multi-subject, and multi-board curriculum profiles.
- Voice tutor and mobile delivery.
