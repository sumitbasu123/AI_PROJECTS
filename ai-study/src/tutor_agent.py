"""
Tutor Agent — LangGraph StateGraph
-----------------------------------
Flow:
  START → retrieve → grade → generate → END
                        ↓ (poor context)
                     rewrite → retrieve  (max 2 retries)

Conversation memory: stored in MemorySaver (per session_id).
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from src.rag_engine import retrieve
from src.llm_layer import ask_llm


# ── State ────────────────────────────────────────────────────────────────────
class TutorState(TypedDict):
    messages:   Annotated[list, add_messages]  # full chat history
    question:   str
    context:    list[dict]
    retries:    int
    answer:     str
    llm_used:   str


# ── Nodes ────────────────────────────────────────────────────────────────────
def node_retrieve(state: TutorState, collection) -> dict:
    chunks = retrieve(collection, state["question"], n_results=5)
    return {"context": chunks}


def node_grade(state: TutorState) -> str:
    """Routing function: is the retrieved context good enough?"""
    chunks = state.get("context", [])
    retries = state.get("retries", 0)

    if retries >= 2 or not chunks:
        return "generate"

    # Simple quality check: top chunk score > 25%
    if chunks and chunks[0]["score"] > 25:
        return "generate"
    return "rewrite"


def node_rewrite(state: TutorState) -> dict:
    """Rephrase question with science keywords for better retrieval."""
    q = state["question"]
    # Simple keyword expansion — no LLM needed
    science_terms = {
        "why": "explain the reason",
        "what is": "define and describe",
        "how does": "process mechanism of",
        "difference between": "compare contrast"
    }
    new_q = q
    for phrase, replacement in science_terms.items():
        if phrase in q.lower():
            new_q = q + f" ({replacement})"
            break
    return {
        "question": new_q,
        "retries": state.get("retries", 0) + 1
    }


def node_generate(state: TutorState, collection) -> dict:
    """Generate the tutor answer using the LLM layer."""
    # If context is thin, do one more targeted retrieval
    context = state.get("context", [])
    if not context:
        context = retrieve(collection, state["question"], n_results=3)

    answer, llm_used = ask_llm(
        question=state["question"],
        context_chunks=context,
        mode="tutor"
    )

    from langchain_core.messages import AIMessage
    return {
        "answer": answer,
        "llm_used": llm_used,
        "messages": [AIMessage(content=answer)]
    }


# ── Build graph ──────────────────────────────────────────────────────────────
def build_tutor_graph(collection):
    from functools import partial

    graph = StateGraph(TutorState)

    graph.add_node("retrieve", partial(node_retrieve, collection=collection))
    graph.add_node("rewrite",  node_rewrite)
    graph.add_node("generate", partial(node_generate, collection=collection))

    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        node_grade,
        {"generate": "generate", "rewrite": "rewrite"}
    )
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("generate", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# ── Public function ──────────────────────────────────────────────────────────
def ask_tutor(app, question: str, session_id: str = "default") -> dict:
    """
    Ask the tutor agent a question.

    Args:
        app:        Compiled LangGraph app (from build_tutor_graph)
        question:   Student's question string
        session_id: Unique ID per student/session (for memory)

    Returns:
        dict with keys: answer, llm_used, context_sources
    """
    from langchain_core.messages import HumanMessage

    # Reset background learning whenever the student becomes active.
    try:
        import streamlit as st
        dream = st.session_state.get("dream_engine")
        if dream:
            dream.notify_activity()
    except Exception:
        pass

    config = {"configurable": {"thread_id": session_id}}

    result = app.invoke(
        {
            "messages":  [HumanMessage(content=question)],
            "question":  question,
            "context":   [],
            "retries":   0,
            "answer":    "",
            "llm_used":  ""
        },
        config
    )

    # Collect sources used
    sources = []
    for chunk in result.get("context", []):
        src = f"{chunk['source']} p.{chunk['page']} ({chunk['score']}% match)"
        if src not in sources:
            sources.append(src)

    return {
        "answer":   result.get("answer", ""),
        "llm_used": result.get("llm_used", ""),
        "sources":  sources
    }
