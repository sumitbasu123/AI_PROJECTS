"""
dream_integration.py — Copy-paste snippets for app.py, tutor_agent.py, exam_agent.py
======================================================================================

This file is NOT imported anywhere. It contains the exact code blocks
you need to paste into the three existing files to activate the dream engine.
"""


# ══════════════════════════════════════════════════════════════════════════════
# 1.  app.py  — paste these three blocks into your existing app.py
# ══════════════════════════════════════════════════════════════════════════════

# ── Block A: add to the imports at the top of app.py ─────────────────────────
APP_IMPORTS = """
from src.dream_engine import DreamEngine
from src.structured_ingest import MARKDOWN_STORE
"""

# ── Block B: replace / extend your vector-store loading section ──────────────
# Find where you do  collection = load_vectorstore(...)  and add below it:
APP_LOAD_DREAM = """
# ── Dream Engine — start background learning ─────────────────────────────────
if "dream_engine" not in st.session_state:
    dream = DreamEngine(
        collection    = collection,
        markdown_store = MARKDOWN_STORE,
        idle_seconds  = 120,    # start dreaming after 2 min of no questions
    )
    dream.start()
    st.session_state["dream_engine"] = dream
"""

# ── Block C: add a Dream tab to your existing tab list ───────────────────────
# Find where you define your tabs, e.g.:
#   tab1, tab2, tab3 = st.tabs(["📚 Tutor", "📝 Exam", "📊 Monitoring"])
# Add a fourth tab:
#   tab1, tab2, tab3, tab4 = st.tabs(["📚 Tutor","📝 Exam","📊 Monitoring","🌙 Dream"])
APP_DREAM_TAB = '''
with tab4:   # 🌙 Dream tab
    st.subheader("🌙 Background Learning (Dream Mode)")

    dream: DreamEngine = st.session_state.get("dream_engine")
    if not dream:
        st.info("Dream engine not running. Load the vector store first.")
    else:
        status = dream.get_status()

        # ── Status row ───────────────────────────────────────────
        state_emoji = {
            "idle":     "💤 Idle",
            "dreaming": "🌙 Dreaming...",
            "stopped":  "⏹ Stopped",
        }.get(status["state"], status["state"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("State",           state_emoji)
        col2.metric("Cycles done",     status["cycles_completed"])
        col3.metric("Chunks added",    status["chunks_added"])
        col4.metric("Duplicates removed", status["duplicates_removed"])

        # ── Idle timer ───────────────────────────────────────────
        if status["state"] == "idle":
            secs = status["seconds_to_dream"]
            st.progress(
                max(0, 1 - secs / status["idle_threshold"]),
                text=f"Next dream in {secs}s  (idle for {status['idle_for_seconds']}s)"
            )
        else:
            st.success("🌙 Dream engine is actively strengthening the knowledge base...")

        # ── Last known gaps ───────────────────────────────────────
        if status["last_gap_topics"]:
            st.markdown("**📉 Last detected coverage gaps:**")
            for topic in status["last_gap_topics"]:
                st.markdown(f"  - {topic}")

        # ── Dream log ────────────────────────────────────────────
        if status["log"]:
            st.markdown("**📋 Dream log (last 20 events):**")
            st.code("\\n".join(reversed(status["log"])), language=None)

        # ── Manual controls ───────────────────────────────────────
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("⏸ Pause dreaming"):
                dream.stop()
                st.session_state["dream_engine"] = None
                st.rerun()
        with col_b:
            if st.button("🔄 Restart dreaming"):
                new_dream = DreamEngine(
                    collection     = collection,
                    markdown_store = MARKDOWN_STORE,
                    idle_seconds   = 120,
                )
                new_dream.start()
                st.session_state["dream_engine"] = new_dream
                st.rerun()

        st.caption(
            "Dream mode runs automatically when you stop asking questions "
            "for 2 minutes. It finds topics with weak coverage, generates "
            "new Q&A pairs, and adds them to the knowledge base."
        )

        # Auto-refresh every 10 seconds while dreaming
        if status["state"] == "dreaming":
            import time
            time.sleep(0.1)
            st.rerun()
'''


# ══════════════════════════════════════════════════════════════════════════════
# 2.  tutor_agent.py  — add ONE line inside ask_tutor()
# ══════════════════════════════════════════════════════════════════════════════

# Find the function  ask_tutor(question, collection, ...)
# Add this at the very start of the function body:

TUTOR_NOTIFY = """
def ask_tutor(question: str, collection, *args, **kwargs):
    # ── Notify dream engine that the user is active ───────────────────────────
    import streamlit as st
    dream = st.session_state.get("dream_engine")
    if dream:
        dream.notify_activity()
    # ... rest of your existing ask_tutor code unchanged ...
"""


# ══════════════════════════════════════════════════════════════════════════════
# 3.  exam_agent.py  — add ONE line inside generate_exam()
# ══════════════════════════════════════════════════════════════════════════════

# Find the function  generate_exam(topic, collection, ...)
# Add this at the very start of the function body:

EXAM_NOTIFY = """
def generate_exam(topic: str, collection, *args, **kwargs):
    # ── Notify dream engine that the user is active ───────────────────────────
    import streamlit as st
    dream = st.session_state.get("dream_engine")
    if dream:
        dream.notify_activity()
    # ... rest of your existing generate_exam code unchanged ...
"""


# ══════════════════════════════════════════════════════════════════════════════
# 4.  src/__init__.py  — add the dream engine export
# ══════════════════════════════════════════════════════════════════════════════

INIT_EXPORT = """
# Add this line to src/__init__.py:
from src.dream_engine import DreamEngine
"""
