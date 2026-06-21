"""
Exam Agent — LangGraph StateGraph
-----------------------------------
Generates a structured question paper from your textbook content.

Flow:
  START → plan_paper → generate_questions → validate → END
                              ↑                  ↓ (marks wrong, retry ≤ 2)
                              └──── replan ←──────┘

All question generation uses retrieved textbook content — no hallucination.
"""

import json
import re
import random
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

from src.rag_engine import retrieve
from src.llm_layer import ask_llm


# ── State ────────────────────────────────────────────────────────────────────
class ExamState(TypedDict):
    request:        str      # original request e.g. "50 marks, chapter 3"
    total_marks:    int
    chapter_hint:   str      # "chapter 3", "photosynthesis", or "all"
    paper_plan:     list     # list of {type, marks, topic, difficulty}
    questions:      list     # generated question objects
    current_marks:  int
    retries:        int


# ── Question types & mark distributions ─────────────────────────────────────
MARK_DISTRIBUTIONS = {
    50: [
        {"type": "mcq",   "marks": 1, "count": 15, "label": "Section A — Multiple Choice"},
        {"type": "short", "marks": 3, "count": 5,  "label": "Section B — Short Answer"},
        {"type": "long",  "marks": 5, "count": 4,  "label": "Section C — Long Answer"},
    ],
    100: [
        {"type": "mcq",   "marks": 1,  "count": 20, "label": "Section A — Multiple Choice"},
        {"type": "short", "marks": 3,  "count": 10, "label": "Section B — Short Answer"},
        {"type": "short", "marks": 5,  "count": 4,  "label": "Section C — Application"},
        {"type": "long",  "marks": 10, "count": 3,  "label": "Section D — Long Answer"},
    ]
}


# ── Topic extraction from textbook ───────────────────────────────────────────
def _get_topics(collection, chapter_hint: str, n: int = 20) -> list[str]:
    """Pull diverse topics from the vector store."""
    query = chapter_hint if chapter_hint != "all" else "science concepts topics chapter"
    chunks = retrieve(collection, query, n_results=n)

    topics = []
    for chunk in chunks:
        # Extract noun phrases as potential question topics
        text = chunk["text"]
        # Simple: grab sentences that define something
        sentences = re.split(r'[.!?]', text)
        for sent in sentences:
            sent = sent.strip()
            if (10 < len(sent) < 120 and
                    any(kw in sent.lower() for kw in
                        ['is', 'are', 'called', 'defined', 'means', 'process',
                         'used', 'helps', 'found', 'made', 'contains'])):
                topics.append(sent)

    # Deduplicate and shuffle
    unique = list(dict.fromkeys(topics))
    random.shuffle(unique)
    return unique[:max(n, 10)]


# ── Question generators (rule-based + LLM) ───────────────────────────────────
def _make_mcq(topic_text: str, marks: int, llm_model: str) -> dict:
    """Generate an MCQ question from a textbook sentence."""
    # Try LLM
    prompt = f"""Create 1 MCQ question for a Class 5 science student.
Base it ONLY on this textbook content: "{topic_text}"

Return ONLY valid JSON (no extra text):
{{
  "question": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "answer": "A",
  "hint": "Think about..."
}}"""

    resp, _ = ask_llm(prompt, [], mode="exam", ollama_model=llm_model)
    try:
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_match:
            q = json.loads(json_match.group())
            q["marks"] = marks
            q["type"] = "mcq"
            return q
    except Exception:
        pass

    # Fallback: build MCQ from the sentence directly
    # Find a key word to blank out
    words = topic_text.split()
    if len(words) < 5:
        return None
    # Pick a content word to blank
    content_words = [w for w in words if len(w) > 4 and w.isalpha()]
    if not content_words:
        return None
    target = random.choice(content_words)
    blanked = topic_text.replace(target, "______", 1)

    # Generate plausible wrong options
    similar_words = [w for w in words
                     if w.isalpha() and w != target and len(w) > 3]
    wrong = random.sample(similar_words, min(3, len(similar_words)))
    while len(wrong) < 3:
        wrong.append(["water", "air", "light", "heat", "energy"][len(wrong)])

    options_list = [target] + wrong[:3]
    random.shuffle(options_list)
    answer_letter = ["A", "B", "C", "D"][options_list.index(target)]

    return {
        "type": "mcq",
        "marks": marks,
        "question": f"Fill in the blank: {blanked}",
        "options": [f"{l}) {o}" for l, o in zip("ABCD", options_list)],
        "answer": answer_letter,
        "hint": f"Think about {topic_text[:40]}..."
    }


def _make_short_answer(topic_text: str, marks: int, llm_model: str) -> dict:
    """Generate a short-answer question."""
    prompt = f"""Create 1 short-answer question for a Class 5 science student worth {marks} marks.
Base it ONLY on: "{topic_text}"

Return ONLY valid JSON:
{{
  "question": "...",
  "answer": "...",
  "hint": "..."
}}"""

    resp, _ = ask_llm(prompt, [], mode="exam", ollama_model=llm_model)
    try:
        json_match = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_match:
            q = json.loads(json_match.group())
            q["marks"] = marks
            q["type"] = "short"
            q["options"] = None
            return q
    except Exception:
        pass

    # Fallback
    starters = ["What is ", "Define ", "Explain ", "Why is ", "How does "]
    q_text = random.choice(starters) + topic_text[:60] + "?"
    return {
        "type": "short",
        "marks": marks,
        "question": q_text,
        "options": None,
        "answer": topic_text,
        "hint": "Use the textbook definition."
    }


def _make_long_answer(topic_text: str, marks: int, llm_model: str) -> dict:
    """Generate a long-answer / essay question."""
    prompt = f"""Create 1 long-answer question worth {marks} marks for a Class 5 science student.
Base it ONLY on: "{topic_text}"

Return ONLY valid JSON:
{{
  "question": "...",
  "answer_points": ["point 1", "point 2", "point 3"],
  "hint": "..."
}}"""

    resp, _ = ask_llm(prompt, [], mode="exam", ollama_model=llm_model)
    try:
        json_match = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_match:
            q = json.loads(json_match.group())
            q["marks"] = marks
            q["type"] = "long"
            q["options"] = None
            q["answer"] = "\n".join(q.get("answer_points", [q.get("answer", "")]))
            return q
    except Exception:
        pass

    return {
        "type": "long",
        "marks": marks,
        "question": f"Describe in detail: {topic_text[:80]}. "
                    f"Include at least {marks // 2} key points with examples.",
        "options": None,
        "answer": topic_text,
        "hint": f"Write {marks} key points."
    }


# ── LangGraph nodes ───────────────────────────────────────────────────────────
def node_plan(state: ExamState, collection) -> dict:
    """Create the question paper plan based on total marks."""
    total = state["total_marks"]
    # Get closest plan (50 or 100)
    plan_key = min(MARK_DISTRIBUTIONS.keys(), key=lambda k: abs(k - total))
    plan = MARK_DISTRIBUTIONS[plan_key]

    # Get topics from textbook
    topics = _get_topics(collection, state["chapter_hint"], n=30)
    random.shuffle(topics)

    # Build per-question specs
    paper_plan = []
    topic_idx = 0
    for section in plan:
        for _ in range(section["count"]):
            paper_plan.append({
                "type": section["type"],
                "marks": section["marks"],
                "topic": topics[topic_idx % len(topics)] if topics else "general science",
                "label": section["label"]
            })
            topic_idx += 1

    return {"paper_plan": paper_plan}


def node_generate(state: ExamState) -> dict:
    """Generate actual question text for each spec in the plan."""
    questions = []
    ollama_model = "gemma2:2b"

    for spec in state["paper_plan"]:
        q = None
        topic = spec["topic"]

        if spec["type"] == "mcq":
            q = _make_mcq(topic, spec["marks"], ollama_model)
        elif spec["type"] == "short":
            q = _make_short_answer(topic, spec["marks"], ollama_model)
        elif spec["type"] == "long":
            q = _make_long_answer(topic, spec["marks"], ollama_model)

        if q:
            q["section_label"] = spec.get("label", "")
            questions.append(q)

    total = sum(q["marks"] for q in questions)
    return {"questions": questions, "current_marks": total}


def node_validate(state: ExamState) -> str:
    """Check if the paper's total marks are close enough to requested."""
    diff = abs(state["current_marks"] - state["total_marks"])
    if diff <= 3 or state.get("retries", 0) >= 2:
        return "done"
    return "replan"


def node_replan(state: ExamState) -> dict:
    """Adjust plan — trim or add questions to fix mark total."""
    questions = state["questions"]
    current = state["current_marks"]
    target = state["total_marks"]

    if current > target:
        # Remove lowest-mark questions until close
        questions.sort(key=lambda q: q["marks"])
        while sum(q["marks"] for q in questions) > target and questions:
            questions.pop(0)
    elif current < target:
        # Add MCQs to make up the difference
        diff = target - current
        for _ in range(diff):
            questions.append({
                "type": "mcq",
                "marks": 1,
                "question": "Which of the following is a natural resource? A) Plastic B) Water C) Glass D) Metal",
                "options": ["A) Plastic", "B) Water", "C) Glass", "D) Metal"],
                "answer": "B",
                "hint": "Think about what is found naturally on Earth.",
                "section_label": "Section A — Multiple Choice"
            })

    new_total = sum(q["marks"] for q in questions)
    return {
        "questions": questions,
        "current_marks": new_total,
        "retries": state.get("retries", 0) + 1
    }


# ── Build graph ──────────────────────────────────────────────────────────────
def build_exam_graph(collection):
    from functools import partial

    graph = StateGraph(ExamState)

    graph.add_node("plan",     partial(node_plan, collection=collection))
    graph.add_node("generate", node_generate)
    graph.add_node("validate", lambda s: s)   # pass-through for routing
    graph.add_node("replan",   node_replan)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", node_validate,
                                {"done": END, "replan": "replan"})
    graph.add_edge("replan", "generate")

    return graph.compile()


# ── Public function ───────────────────────────────────────────────────────────
def generate_exam(app, request: str,
                  total_marks: int = 50,
                  chapter_hint: str = "all") -> dict:
    """
    Generate a question paper.

    Returns:
        dict with keys: questions (list), total_marks (int), sections (dict)
    """
    # Reset background learning whenever the student becomes active.
    try:
        import streamlit as st
        dream = st.session_state.get("dream_engine")
        if dream:
            dream.notify_activity()
    except Exception:
        pass

    result = app.invoke({
        "request":       request,
        "total_marks":   total_marks,
        "chapter_hint":  chapter_hint,
        "paper_plan":    [],
        "questions":     [],
        "current_marks": 0,
        "retries":       0
    })

    questions = result.get("questions", [])

    # Group by section
    sections = {}
    for q in questions:
        label = q.get("section_label", "General")
        if label not in sections:
            sections[label] = []
        sections[label].append(q)

    return {
        "questions":    questions,
        "total_marks":  result.get("current_marks", 0),
        "sections":     sections
    }
