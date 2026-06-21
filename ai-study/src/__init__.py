# AI Study — src package
# Legacy exports (rag_engine still used by tutor/exam agents for vector store loading)
from src.rag_engine import load_pdfs, chunk_documents, build_vectorstore, load_vectorstore, retrieve

# New structured ingestion pipeline
from src.structured_ingest import (
    run_pipeline,           # full 5-stage pipeline
    retrieve as structured_retrieve,  # richer retrieve (adds 'section' field)
    load_vectorstore as load_structured_vectorstore,
    build_vectorstore_from_chunks,
    MARKDOWN_STORE,
    VECTORSTORE,
)

from src.llm_layer import ask_llm, check_llm_availability
from src.tutor_agent import build_tutor_graph, ask_tutor
from src.exam_agent import build_exam_graph, generate_exam
from src.dream_engine import DreamEngine
