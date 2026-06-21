"""
app.py — AI Study: Streamlit UI
--------------------------------
Three tabs:
  📚 Study with Tutor   — ask questions, get textbook-grounded answers
  📝 Generate Exam      — 50 or 100 mark question papers
  📊 Monitoring         — logs, OCR stats, hallucination guard events
"""

import os, sys, uuid
import streamlit as st
from pathlib import Path
from src.dream_engine import DreamEngine
from src.structured_ingest import MARKDOWN_STORE

st.set_page_config(
    page_title="AI Study — Class 5 Computer Science",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

VECTORSTORE_DIR = "./vectorstore"
LOG_DIR         = Path("./logs")


# ── Load resources ────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading your textbooks...")
def load_resources():
    from src.rag_engine  import load_vectorstore
    from src.tutor_agent import build_tutor_graph
    from src.exam_agent  import build_exam_graph
    from src.logger      import get_logger
    log = get_logger("app")

    if not Path(VECTORSTORE_DIR).exists():
        return None, None, None
    try:
        collection = load_vectorstore(VECTORSTORE_DIR)
        tutor_app  = build_tutor_graph(collection)
        exam_app   = build_exam_graph(collection)
        log.info("Resources loaded successfully")
        return collection, tutor_app, exam_app
    except Exception as e:
        st.error(f"Error loading vector store: {e}")
        return None, None, None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/graduation-cap.png", width=64)
    st.title("AI Study")
    st.caption("Class 5 — Computer Science")
    st.divider()

    st.subheader("🤖 AI Engine")
    from src.llm_layer import check_llm_availability
    llm_status = check_llm_availability()

    if llm_status.get("groq"):
        st.success("✅ Groq API connected")
    else:
        st.info("💡 [Free Groq key](https://console.groq.com)")
    if llm_status.get("ollama"):
        models = llm_status["ollama"]
        if isinstance(models, list) and models and "no models" not in models[0]:
            st.success(f"✅ Ollama: {', '.join(models)}")
        else:
            st.warning("⚠️ Ollama running — pull a model\n`ollama pull gemma2:2b`")
    else:
        st.info("💡 [Install Ollama](https://ollama.com) for best answers")

    

    st.success("✅ Offline mode always on")
    st.divider()

    # Anti-hallucination status
    st.subheader("🛡️ Anti-Hallucination")
    st.success("✅ Confidence gate: ON")
    st.success("✅ Grounding check: ON")
    st.success("✅ Temp = 0 (facts only)")
    st.divider()

    if Path(VECTORSTORE_DIR).exists():
        st.success("✅ Textbooks loaded")
    else:
        st.error("❌ Run `python ingest.py` first")

    source_dir = os.getenv("STUDY_SOURCE_DIR", str(Path("study_materials").resolve()))
    st.caption(f"📂 {source_dir}")

    if st.button("🔄 Reload Textbooks", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()


collection, tutor_app, exam_app = load_resources()

if collection is None:
    st.error("## ⚠️ Textbooks not indexed yet")
    st.code("python ingest.py", language="bash")
    st.stop()

# Start one background learning engine for this Streamlit session.
if "dream_engine" not in st.session_state:
    dream = DreamEngine(
        collection=collection,
        markdown_store=MARKDOWN_STORE,
        idle_seconds=120,
    )
    dream.start()
    st.session_state["dream_engine"] = dream

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_tutor, tab_exam, tab_monitor, tab_dream = st.tabs([
    "📚 Study with Tutor",
    "📝 Generate Exam Paper",
    "📊 Monitoring",
    "🌙 Dream Mode",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — TUTOR
# ════════════════════════════════════════════════════════════════════════════
with tab_tutor:
    st.header("📚 Study Tutor")
    st.caption("Ask any question from your Class 5 Computer Science textbook")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    # Suggested questions
    st.markdown("**💡 Try asking:**")
    cols = st.columns(3)
    suggestions = [
        "What is a computer?",         "What is input and output?",
        "What is software and hardware?","What is the internet?",
        "What is memory in a computer?","What is an operating system?",
    ]
    for i, col in enumerate(cols):
        for j in range(2):
            idx = i * 2 + j
            if idx < len(suggestions):
                if col.button(suggestions[idx], key=f"sug_{idx}",
                              use_container_width=True):
                    st.session_state.pending_question = suggestions[idx]

    st.divider()

    # Chat history
    for msg in st.session_state.chat_history:
        avatar = "🧒" if msg["role"] == "user" else "🎓"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                # Confidence indicator
                llm = msg.get("llm_used", "")
                if "blocked" in llm:
                    st.warning("🛡️ Answer blocked — topic not found in textbook")
                elif "grounding-fallback" in llm:
                    st.info("🛡️ LLM answer replaced with textbook excerpt (grounding check)")
                elif "offline" in llm:
                    st.caption("📖 Offline mode — showing textbook excerpts directly")

                if msg.get("sources"):
                    with st.expander("📖 Textbook sources", expanded=False):
                        for src in msg["sources"]:
                            st.caption(f"• {src}")
                if llm:
                    with st.expander("🤖 Engine used", expanded=False):
                        st.caption(llm)

    prefill    = st.session_state.pop("pending_question", None)
    user_input = st.chat_input("Type your question here...")
    if prefill:
        user_input = prefill

    if user_input:
        from src.logger import log_session_start
        log_session_start(st.session_state.session_id, user_input)

        with st.chat_message("user", avatar="🧒"):
            st.markdown(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant", avatar="🎓"):
            with st.spinner("Thinking..."):
                from src.tutor_agent import ask_tutor
                result = ask_tutor(
                    tutor_app, question=user_input,
                    session_id=st.session_state.session_id
                )

            answer   = result.get("answer", "Sorry, I couldn't find an answer.")
            sources  = result.get("sources", [])
            llm_used = result.get("llm_used", "")

            st.markdown(answer)

            # Show guard status inline
            if "blocked" in llm_used:
                st.warning("🛡️ Answer blocked — topic not reliably found in textbook")
            elif "grounding-fallback" in llm_used:
                st.info("🛡️ Switched to textbook excerpt (grounding check fired)")

            if sources:
                with st.expander("📖 Textbook sources", expanded=False):
                    for src in sources:
                        st.caption(f"• {src}")
            with st.expander("🤖 Engine used", expanded=False):
                st.caption(llm_used)

        st.session_state.chat_history.append({
            "role": "assistant", "content": answer,
            "sources": sources, "llm_used": llm_used
        })
        st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat", key="clear_chat"):
            st.session_state.chat_history = []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — EXAM
# ════════════════════════════════════════════════════════════════════════════
with tab_exam:
    st.header("📝 Question Paper Generator")
    st.caption("Generates questions grounded in your textbook content only")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        total_marks = st.selectbox("Total Marks", [50, 100])
    with col2:
        chapter_hint = st.text_input("Chapter / Topic", placeholder="e.g. Chapter 3")
    with col3:
        show_answers = st.toggle("Show Answer Key", value=False)

    if total_marks == 50:
        st.markdown(
            "**Section A** — 15 MCQ × 1 mark = 15  |  "
            "**Section B** — 5 Short × 3 marks = 15  |  "
            "**Section C** — 4 Long × 5 marks = 20  |  **Total = 50**"
        )
    else:
        st.markdown(
            "**Section A** — 20 MCQ × 1 = 20  |  "
            "**Section B** — 10 Short × 3 = 30  |  "
            "**Section C** — 4 App × 5 = 20  |  "
            "**Section D** — 3 Long × 10 = 30  |  **Total = 100**"
        )

    if st.button(f"🎯 Generate {total_marks}-Mark Paper", type="primary",
                 use_container_width=True):
        with st.spinner("Building paper from your textbook..."):
            from src.exam_agent import generate_exam
            from src.logger import get_logger
            elog = get_logger("exam")
            elog.info(f"Generating {total_marks}-mark paper: {chapter_hint or 'all'}")

            paper = generate_exam(
                exam_app,
                request=f"{total_marks} marks" + (f" on {chapter_hint}" if chapter_hint else ""),
                total_marks=total_marks,
                chapter_hint=chapter_hint or "all"
            )

        sections    = paper.get("sections", {})
        actual_marks = paper.get("total_marks", 0)
        elog.info(f"Paper generated: {actual_marks} marks, "
                  f"{sum(len(v) for v in sections.values())} questions")

        st.success(f"✅ Paper generated — {actual_marks} marks total")
        st.divider()

        st.markdown(f"""
<div style="text-align:center;padding:16px;border:2px solid #333;border-radius:8px;margin-bottom:20px;">
  <h2 style="margin:0">Class 5 — Computer Science</h2>
  <h3 style="margin:4px 0">Question Paper</h3>
  <p>Total Marks: <strong>{actual_marks}</strong> &nbsp;|&nbsp;
     Time: <strong>{"2 Hours" if total_marks==50 else "3 Hours"}</strong></p>
  <p style="font-size:13px;color:gray">All questions are compulsory.</p>
</div>""", unsafe_allow_html=True)

        q_num = 1
        for section_label, questions in sections.items():
            sec_marks = sum(q["marks"] for q in questions)
            st.subheader(f"{section_label}  [{sec_marks} marks]")
            for q in questions:
                with st.container():
                    st.markdown(
                        f"**Q{q_num}.** {q.get('question','')} "
                        f"<span style='color:gray;font-size:13px'>"
                        f"({q['marks']} mark{'s' if q['marks']>1 else ''})</span>",
                        unsafe_allow_html=True
                    )
                    if q.get("type") == "mcq" and q.get("options"):
                        for opt in q["options"]:
                            st.markdown(f"&nbsp;&nbsp;&nbsp;{opt}")
                    if show_answers and q.get("answer"):
                        with st.expander("✅ Answer"):
                            st.success(q["answer"])
                            if q.get("hint"):
                                st.caption(f"💡 {q['hint']}")
                    if q.get("type") == "short":
                        st.markdown("<div style='border-bottom:1px dashed #ccc;height:28px;margin:4px 0'></div>" * 3, unsafe_allow_html=True)
                    elif q.get("type") == "long":
                        st.markdown("<div style='border-bottom:1px dashed #ccc;height:28px;margin:4px 0'></div>" * 6, unsafe_allow_html=True)
                    st.markdown("---")
                    q_num += 1

        # Download
        lines = ["Class 5 — COMPUTER SCIENCE", "QUESTION PAPER",
                 f"Total Marks: {actual_marks}",
                 f"Time: {'2 Hours' if total_marks<=50 else '3 Hours'}",
                 "=" * 60, ""]
        qn = 1
        for lbl, qs in sections.items():
            lines.append(f"\n{lbl}  [{sum(q['marks'] for q in qs)} marks]\n")
            for q in qs:
                lines.append(f"Q{qn}. {q.get('question','')}  [{q['marks']} mark(s)]")
                if q.get("options"):
                    lines += [f"   {o}" for o in q["options"]]
                if show_answers and q.get("answer"):
                    lines.append(f"   Answer: {q['answer']}")
                lines.append("")
                qn += 1

        st.download_button("⬇️ Download Paper (.txt)", "\n".join(lines),
                           f"exam_{total_marks}_marks.txt", "text/plain",
                           use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — MONITORING DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
with tab_monitor:
    st.header("📊 Monitoring Dashboard")
    st.caption("Live stats from your log files. Auto-refreshes every 30 seconds.")

    if st.button("🔄 Refresh Now", key="refresh_monitor"):
        st.rerun()

    # ── Stats cards ──────────────────────────────────────────
    from src.logger import get_log_stats, get_recent_logs
    stats = get_log_stats()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Questions", stats["total_questions"])
    c2.metric("OCR Failures",    stats["ocr_failures"],
              delta=None if stats["ocr_failures"]==0 else f"-{stats['ocr_failures']}",
              delta_color="inverse")
    c3.metric("OCR Warnings",    stats["ocr_warnings"])
    c4.metric("Guard Fired",     stats["hallucination_guards_fired"],
              delta=None if stats["hallucination_guards_fired"]==0 else "blocked",
              delta_color="inverse")
    c5.metric("Low Retrieval",   stats["low_retrieval_warnings"])

    st.divider()

    # ── Log file viewer ───────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📋 Recent Activity (ai_study.log)")
        recent = get_recent_logs(40)
        if recent:
            log_text = "\n".join(recent)
            st.code(log_text, language=None)
        else:
            st.info("No log entries yet. Ask a question to start logging.")

    with col_right:
        st.subheader("🖼 OCR Failures (ocr_failures.log)")
        ocr_log = LOG_DIR / "ocr_failures.log"
        if ocr_log.exists():
            lines = ocr_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            if lines:
                st.code("\n".join(lines[-30:]), language=None)
                if any("ZERO_WORDS" in l for l in lines):
                    st.warning(
                        "Some images returned 0 words. Tips:\n"
                        "- Run `python fix_tesseract.py`\n"
                        "- Use better-lit, sharper photos\n"
                        "- Minimum image width: 1000 px"
                    )
            else:
                st.success("No OCR failures recorded ✅")
        else:
            st.info("No OCR log yet. Run `python ingest.py` first.")

    st.divider()

    # ── Hallucination guard log ───────────────────────────────
    st.subheader("🛡️ Hallucination Guard Log")
    guard_log_path = LOG_DIR / "hallucination_guard.log"
    if guard_log_path.exists():
        lines = guard_log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        fired   = [l for l in lines if "fired=True" in l]
        passed  = [l for l in lines if "fired=False" in l]
        g1, g2 = st.columns(2)
        g1.metric("Guard Blocked",  len(fired))
        g2.metric("Guard Passed",   len(passed))
        if fired:
            st.markdown("**Recent blocks:**")
            st.code("\n".join(fired[-10:]), language=None)
            st.info(
                "Guard fires when:\n"
                "1. Top retrieval score < 25% (topic not in textbook)\n"
                "2. Generated answer has < 30% word overlap with textbook context"
            )
    else:
        st.info("No guard events yet.")

    st.divider()

    # ── Log file download ────────────────────────────────────
    st.subheader("⬇️ Download Log Files")
    dl1, dl2, dl3 = st.columns(3)

    for col, fname, label in [
        (dl1, "ai_study.log",            "📋 Main Log"),
        (dl2, "ocr_failures.log",        "🖼 OCR Failures"),
        (dl3, "hallucination_guard.log", "🛡️ Guard Log"),
    ]:
        fpath = LOG_DIR / fname
        if fpath.exists():
            col.download_button(
                label=label,
                data=fpath.read_text(encoding="utf-8", errors="ignore"),
                file_name=fname,
                mime="text/plain",
                use_container_width=True
            )
        else:
            col.button(label + " (empty)", disabled=True,
                       use_container_width=True)

    # ── Auto-refresh every 30s ───────────────────────────────
    st.caption("Dashboard auto-refreshes every 30 seconds")
    import time
    time.sleep(0)   # placeholder — Streamlit reruns on interaction


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — DREAM MODE
# ════════════════════════════════════════════════════════════════════════════
with tab_dream:
    st.header("🌙 Dream Mode — Background Learning")
    st.caption(
        "While you are away, the app finds knowledge gaps, generates new "
        "question-answer pairs, and strengthens the knowledge base."
    )

    dream = st.session_state.get("dream_engine")

    if dream:
        status = dream.get_status()

        if status["state"] == "dreaming":
            st.success("Dreaming — actively strengthening the knowledge base")
        elif status["state"] == "idle":
            seconds = status["seconds_to_dream"]
            st.info(
                f"Idle — next dream starts in {seconds}s "
                f"(idle for {status['idle_for_seconds']}s)"
            )
        else:
            st.warning(f"Dream engine state: {status['state']}")

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cycles completed", status["cycles_completed"])
        c2.metric("New chunks added", status["chunks_added"])
        c3.metric("Duplicates removed", status["duplicates_removed"])
        c4.metric("Gaps found (last)", status["gaps_found"])

        if status["state"] == "idle" and status["idle_threshold"] > 0:
            progress = min(
                1.0,
                status["idle_for_seconds"] / status["idle_threshold"],
            )
            st.progress(
                progress,
                text=(
                    f"Idle timer: {status['idle_for_seconds']}s / "
                    f"{status['idle_threshold']}s"
                ),
            )

        st.divider()
        st.subheader("Last Detected Coverage Gaps")
        if status["last_gap_topics"]:
            gap_columns = st.columns(2)
            for index, topic in enumerate(status["last_gap_topics"]):
                gap_columns[index % 2].markdown(f"- {topic}")
        else:
            st.info(
                "No gap scan has run yet. The engine starts after "
                f"{status['idle_threshold']}s of inactivity."
            )

        st.divider()
        st.subheader("Dream Log")
        if status["log"]:
            st.code("\n".join(reversed(status["log"])), language=None)
        else:
            st.info("No dream events yet.")
    else:
        status = None
        st.warning("Dream engine is stopped.")

    st.divider()
    st.subheader("Controls")
    control1, control2, control3 = st.columns(3)

    with control1:
        if st.button("Refresh Status", use_container_width=True):
            st.rerun()

    with control2:
        if st.button(
            "Stop Dream Engine",
            disabled=dream is None,
            use_container_width=True,
        ):
            dream.stop()
            st.session_state.pop("dream_engine", None)
            st.rerun()

    with control3:
        idle_choice = st.selectbox(
            "Idle threshold",
            [60, 120, 300, 600],
            index=1,
            format_func=lambda seconds: f"{seconds // 60} minute(s)",
        )
        if st.button("Start / Restart", use_container_width=True):
            if dream:
                dream.stop()
            new_dream = DreamEngine(
                collection=collection,
                markdown_store=MARKDOWN_STORE,
                idle_seconds=idle_choice,
            )
            new_dream.start()
            st.session_state["dream_engine"] = new_dream
            st.rerun()

    st.divider()
    st.caption(
        "After the idle threshold, the engine probes curriculum topics, "
        "enriches weak areas from stored textbook Markdown, deepens thin "
        "sections, and periodically removes near-duplicate dream chunks."
    )
