from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from database import (
    add_interview_result,
    add_job,
    delete_job,
    get_interview_results,
    get_jobs,
    init_db,
    update_job_status,
)
from services import (
    DEFAULT_PROFILE,
    analyze_job_description,
    build_daily_summary,
    discover_jobs,
    extract_docx_text,
    fetch_job_page,
    generate_questions,
    improve_answer,
    normalize_job,
    parse_linkedin_alert_text,
    resume_recommendations,
    score_answer,
    score_job,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CV = APP_DIR / "resume.docx"

st.set_page_config(
    page_title="Career Command Center",
    page_icon="CC",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_db()

for secret_name in [
    "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "OPENAI_API_KEY", "OPENAI_MODEL"
]:
    if not os.getenv(secret_name):
        try:
            if secret_name in st.secrets:
                os.environ[secret_name] = str(st.secrets[secret_name])
        except FileNotFoundError:
            pass


def load_profile() -> dict:
    path = APP_DIR / "profile.json"
    if path.exists():
        return {**DEFAULT_PROFILE, **json.loads(path.read_text(encoding="utf-8"))}
    return DEFAULT_PROFILE.copy()


def save_profile(profile: dict) -> None:
    (APP_DIR / "profile.json").write_text(
        json.dumps(profile, indent=2), encoding="utf-8"
    )


def load_settings() -> dict:
    path = APP_DIR / "settings.json"
    defaults = {
        "location": "India",
        "minimum_score": 68,
        "providers": ["Remotive", "Arbeitnow"],
        "adzuna_app_id": os.getenv("ADZUNA_APP_ID", ""),
        "adzuna_app_key": os.getenv("ADZUNA_APP_KEY", ""),
    }
    if path.exists():
        return {**defaults, **json.loads(path.read_text(encoding="utf-8"))}
    return defaults


def save_settings(settings: dict) -> None:
    (APP_DIR / "settings.json").write_text(
        json.dumps(settings, indent=2), encoding="utf-8"
    )


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f4f2ec; color: #17231f; }
        [data-testid="stSidebar"] { background: #143d32; }
        [data-testid="stSidebar"] * { color: #f8fbf8; }
        [data-testid="stMetric"] {
            background: #fffdf8; border: 1px solid #ddd9cf;
            padding: 18px; border-radius: 12px;
        }
        .hero {
            padding: 32px 38px; border-radius: 16px; color: white;
            background: linear-gradient(130deg, #1f5b49, #143d32);
            margin-bottom: 18px;
        }
        .hero h1 { font-family: Georgia, serif; font-weight: 500; margin: 5px 0; }
        .hero p { color: #c6d8d0; margin: 0; }
        .eyebrow {
            color: #86a595; font-size: 11px; font-weight: 800;
            letter-spacing: .14em; text-transform: uppercase;
        }
        .score-high { color: #1f5b49; font-weight: 800; }
        .score-medium { color: #a65f27; font-weight: 800; }
        .score-low { color: #aa4038; font-weight: 800; }
        div[data-testid="stExpander"] {
            background: #fffdf8; border: 1px solid #ddd9cf; border-radius: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(score: int) -> str:
    css = "score-high" if score >= 80 else "score-medium" if score >= 65 else "score-low"
    return f'<span class="{css}">{score}/100</span>'


def overview_page(profile: dict) -> None:
    jobs = get_jobs()
    results = get_interview_results()
    scores = [score_job(row, profile)["score"] for row in jobs.to_dict("records")]
    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">YOUR NEXT MOVE</div>
          <h1>Turn deep experience into a sharper market story.</h1>
          <p>{profile["headline"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active opportunities", len(jobs[jobs["status"] != "Archive"]))
    c2.metric("High-fit roles", sum(score >= 80 for score in scores))
    average = round(results["overall_score"].mean()) if not results.empty else 0
    c3.metric("Mock interview average", f"{average}%" if average else "Not started")
    c4.metric("Applications", len(jobs[jobs["status"].isin(["Applied", "Interview"])]))
    if not jobs.empty and "credibility_score" in jobs:
        credible = jobs["credibility_score"].fillna(0).astype(int)
        st.caption(
            f"Pipeline health: {sum(credible >= 70)} trusted-source jobs; "
            f"{sum(credible < 50)} jobs need source verification."
        )

    left, right = st.columns([1.5, 1])
    with left:
        st.subheader("Top opportunities")
        if jobs.empty:
            st.info("Add a job description to begin building your pipeline.")
        else:
            rows = []
            for job in jobs.to_dict("records"):
                analysis = score_job(job, profile)
                rows.append(
                    {
                        "Fit": analysis["score"],
                        "Role": job["title"],
                        "Company": job["company"],
                        "Status": job["status"],
                    }
                )
            st.dataframe(
                pd.DataFrame(rows).sort_values("Fit", ascending=False).head(5),
                hide_index=True,
                use_container_width=True,
            )
    with right:
        st.subheader("Strongest evidence")
        st.markdown(
            """
            - **19 years** in technology and data delivery
            - **15+ engineers** currently led
            - **5 years** of US onsite experience
            - Azure, Snowflake, dbt, and Snowpark architecture
            - Retail, healthcare, payments, and BFSI delivery
            """
        )


def jobs_page(profile: dict) -> None:
    st.title("Job Intelligence")
    st.caption("Score trusted opportunities and track each application.")
    (
        live_tab, pipeline_tab, alert_tab, import_tab,
        resume_tab, summary_tab, add_tab,
    ) = st.tabs(
        [
            "Search internet", "Application pipeline", "LinkedIn alerts",
            "Official URL import", "Resume agent", "Daily summary", "Add job",
        ]
    )
    with live_tab:
        settings = load_settings()
        st.subheader("Find matching jobs from supported internet sources")
        st.caption(
            "Searches are generated from your CV, target roles, skills, and location. "
            "Strong matches are shortlisted automatically."
        )
        c1, c2, c3 = st.columns([1.2, 1, 1])
        location = c1.text_input("Search location", settings["location"])
        minimum_score = c2.slider(
            "Minimum fit score", 40, 95, int(settings["minimum_score"])
        )
        max_queries = c3.selectbox("Search breadth", [2, 3, 5, 7], index=2)
        providers = st.multiselect(
            "Job providers",
            ["Adzuna India", "Remotive", "Arbeitnow"],
            default=settings["providers"],
            help=(
                "Adzuna is best for India and requires free API credentials. "
                "Remotive and Arbeitnow work without API keys."
            ),
        )
        with st.expander("Adzuna India API credentials"):
            st.markdown(
                "Register at [Adzuna Developer](https://developer.adzuna.com/) "
                "to receive an app ID and app key."
            )
            adzuna_app_id = st.text_input(
                "Adzuna app ID", settings["adzuna_app_id"]
            )
            adzuna_app_key = st.text_input(
                "Adzuna app key", settings["adzuna_app_key"], type="password"
            )
        if st.button("Search and refresh dashboard", type="primary"):
            if not providers:
                st.error("Select at least one job provider.")
            elif "Adzuna India" in providers and not (
                adzuna_app_id and adzuna_app_key
            ):
                st.error("Enter Adzuna credentials or deselect Adzuna India.")
            else:
                updated_settings = {
                    "location": location,
                    "minimum_score": minimum_score,
                    "providers": providers,
                    "adzuna_app_id": adzuna_app_id,
                    "adzuna_app_key": adzuna_app_key,
                }
                save_settings(updated_settings)
                resume_text = profile.get("resume_text", "")
                if not resume_text and DEFAULT_CV.exists():
                    resume_text = extract_docx_text(DEFAULT_CV)
                with st.spinner("Searching supported job sources and scoring matches..."):
                    result = discover_jobs(
                        profile=profile,
                        resume_text=resume_text,
                        location=location,
                        providers=providers,
                        adzuna_app_id=adzuna_app_id,
                        adzuna_app_key=adzuna_app_key,
                        minimum_score=minimum_score,
                        max_queries=max_queries,
                    )
                added = sum(
                    add_job(job, job["analysis"]) for job in result["jobs"]
                )
                st.session_state["last_discovery"] = result
                st.success(
                    f"Found {len(result['jobs'])} matching jobs; "
                    f"added {added} new jobs to the dashboard."
                )
        if result := st.session_state.get("last_discovery"):
            st.write("**Searches used:**", " | ".join(result["queries"]))
            if result["errors"]:
                st.warning("\n".join(result["errors"]))
            preview = [
                {
                    "Fit": job["analysis"]["score"],
                    "Trust": job["analysis"]["credibility_score"],
                    "Role": job["title"],
                    "Company": job["company"],
                    "Location": job["location"],
                    "Source": job["source"],
                    "Status": job["status"],
                    "Action": job["analysis"]["suggested_action"],
                    "Apply": job["url"],
                }
                for job in result["jobs"][:30]
            ]
            if preview:
                st.dataframe(
                    pd.DataFrame(preview),
                    hide_index=True,
                    use_container_width=True,
                    column_config={"Apply": st.column_config.LinkColumn()},
                )
            else:
                st.info(
                    "No jobs passed the selected score. Lower the minimum score "
                    "or enable Adzuna India for broader local coverage."
                )

    with add_tab:
        with st.form("job_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            title = c1.text_input("Job title")
            company = c2.text_input("Company")
            c3, c4 = st.columns(2)
            location = c3.text_input("Location", "India / Remote")
            source = c4.selectbox(
                "Source",
                [
                    "Company career page", "Greenhouse", "Lever", "Workday",
                    "LinkedIn alert", "Naukri", "Recruiter / consultancy",
                ],
            )
            url = st.text_input("Official apply URL")
            description = st.text_area("Job description", height=260)
            submitted = st.form_submit_button("Score and save", type="primary")
        if submitted:
            if not title or not company or len(description) < 80:
                st.error("Enter the title, company, and a complete job description.")
            else:
                record = {
                    "title": title, "company": company, "location": location,
                    "source": source, "url": url, "description": description,
                }
                record = normalize_job(record)
                analysis = score_job(record, profile)
                add_job(record, analysis)
                st.success(f"Saved with a fit score of {analysis['score']}/100.")

    with pipeline_tab:
        jobs = get_jobs()
        if jobs.empty:
            st.info("No opportunities saved yet.")
        else:
            search = st.text_input("Search pipeline")
            statuses = [
                "Review", "Shortlisted", "Apply", "Applied", "Interview", "Archive"
            ]
            status_filter = st.multiselect(
                "Status", statuses, default=statuses[:-1]
            )
            display = jobs[jobs["status"].isin(status_filter)]
            if search:
                mask = (
                    display["title"].str.contains(search, case=False, na=False)
                    | display["company"].str.contains(search, case=False, na=False)
                    | display["description"].str.contains(search, case=False, na=False)
                )
                display = display[mask]
            for job in display.to_dict("records"):
                analysis = score_job(job, profile)
                with st.expander(
                    f"{analysis['score']}/100 | {job['title']} - {job['company']}"
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Location:** {job['location'] or 'Not specified'}")
                    c2.markdown(f"**Source:** {job['source']}")
                    c3.markdown(f"**Status:** {job['status']}")
                    st.markdown(
                        f"**Fit:** {status_badge(analysis['score'])}",
                        unsafe_allow_html=True,
                    )
                    st.write("**Why it matches:**", analysis["reason"])
                    st.write("**Suggested action:**", analysis["suggested_action"])
                    st.write(
                        "**Credibility:**",
                        f"{analysis['credibility_score']}/100",
                    )
                    st.write("**Matched skills:**", ", ".join(analysis["matched_skills"]) or "None")
                    st.write("**Risks:**", ", ".join(analysis["risks"]) or "No major risk")
                    st.write(
                        "**Resume keywords:**",
                        ", ".join(analysis["resume_keywords"]) or "None",
                    )
                    st.caption(
                        " | ".join(
                            [
                                f"Work mode: {job.get('work_mode') or 'Not specified'}",
                                (
                                    f"Experience: {job.get('experience_min') or '?'}"
                                    f"-{job.get('experience_max') or '?'} years"
                                ),
                                f"Domain: {job.get('domain') or 'Not classified'}",
                                f"Salary: {job.get('salary') or 'Not provided'}",
                            ]
                        )
                    )
                    if job["url"]:
                        st.link_button("Open official listing", job["url"])
                    new_status = st.selectbox(
                        "Update status",
                        statuses,
                        index=statuses.index(job["status"]),
                        key=f"status_{job['id']}",
                    )
                    b1, b2 = st.columns(2)
                    if b1.button("Save status", key=f"save_{job['id']}"):
                        update_job_status(job["id"], new_status)
                        st.rerun()
                    if b2.button("Delete", key=f"delete_{job['id']}"):
                        delete_job(job["id"])
                        st.rerun()
            st.download_button(
                "Download pipeline CSV",
                display.to_csv(index=False).encode("utf-8"),
                "job_pipeline.csv",
                "text/csv",
            )

    with alert_tab:
        st.subheader("Import LinkedIn job-alert email text")
        st.caption(
            "Paste alert email content. The app parses public job links and "
            "context without logging in to or scraping LinkedIn."
        )
        alert_text = st.text_area(
            "LinkedIn alert text",
            height=280,
            placeholder="Paste one or more LinkedIn job-alert emails...",
        )
        if st.button("Parse alert"):
            parsed = parse_linkedin_alert_text(alert_text)
            st.session_state["parsed_alert_jobs"] = parsed
            if parsed:
                st.success(f"Parsed {len(parsed)} unique job links.")
            else:
                st.warning(
                    "No LinkedIn job links were found. Paste the complete "
                    "plain-text alert including its URLs."
                )
        parsed_jobs = st.session_state.get("parsed_alert_jobs", [])
        if parsed_jobs:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Role": job["title"],
                            "Company": job["company"],
                            "Source": job["source"],
                            "URL": job["url"],
                        }
                        for job in parsed_jobs
                    ]
                ),
                hide_index=True,
                use_container_width=True,
                column_config={"URL": st.column_config.LinkColumn()},
            )
            if st.button("Score and save parsed alerts", type="primary"):
                saved = 0
                for job in parsed_jobs:
                    analysis = score_job(job, profile)
                    job["status"] = (
                        "Shortlisted"
                        if analysis["suggested_action"] == "Apply"
                        else "Review"
                    )
                    saved += add_job(job, analysis)
                st.success(f"Added {saved} new jobs to the pipeline.")

    with import_tab:
        st.warning(
            "Use official company or ATS pages. This performs one page request; "
            "it does not crawl LinkedIn or bypass site controls."
        )
        page_url = st.text_input("Job page URL")
        if st.button("Fetch page"):
            try:
                st.session_state["imported_job"] = fetch_job_page(page_url)
            except (ValueError, requests.RequestException) as exc:
                st.error(str(exc))
        if imported := st.session_state.get("imported_job"):
            st.subheader(imported["title"])
            st.caption(imported["url"])
            st.text_area("Extracted text", imported["text"], height=300)
            c1, c2 = st.columns(2)
            imported_title = c1.text_input(
                "Role title", value=imported["title"], key="import_title"
            )
            imported_company = c2.text_input(
                "Company", key="import_company"
            )
            imported_location = st.text_input(
                "Location", key="import_location"
            )
            if st.button("Normalize, score, and save official page"):
                if not imported_company:
                    st.error("Enter the employer name before saving.")
                else:
                    record = normalize_job(
                        {
                            "title": imported_title,
                            "company": imported_company,
                            "location": imported_location,
                            "source": "Company career page",
                            "url": imported["url"],
                            "description": imported["text"],
                            "raw_payload": imported,
                        }
                    )
                    analysis = score_job(record, profile)
                    record["status"] = (
                        "Shortlisted"
                        if analysis["suggested_action"] == "Apply"
                        else "Review"
                    )
                    if add_job(record, analysis):
                        st.success(
                            f"Saved with fit {analysis['score']}/100 and "
                            f"credibility {analysis['credibility_score']}/100."
                        )
                    else:
                        st.info("This application URL is already in the pipeline.")

    with resume_tab:
        jobs = get_jobs()
        candidates = jobs[
            jobs["status"].isin(["Shortlisted", "Apply", "Applied", "Interview"])
        ] if not jobs.empty else jobs
        if candidates.empty:
            st.info("Shortlist a job before using the Resume Agent.")
        else:
            options = {
                f"{row['title']} - {row['company']} ({row['fit_score']}/100)": row
                for row in candidates.to_dict("records")
            }
            selected_label = st.selectbox(
                "Choose a job for resume guidance",
                list(options),
                key="resume_agent_job",
            )
            advice = resume_recommendations(options[selected_label], profile)
            st.markdown("### Recommended headline")
            st.code(advice["headline"])
            st.markdown("### Keywords to highlight")
            st.write(", ".join(advice["keywords"]) or "No exact keywords found")
            st.markdown("### Existing proof points to prioritize")
            for point in advice["proof_points"]:
                st.markdown(f"- {point}")
            if advice["gaps"]:
                st.markdown("### Gaps to address honestly")
                st.write(", ".join(advice["gaps"]))
            st.markdown("### Short cover note")
            st.text_area(
                "Cover note",
                advice["cover_note"],
                height=160,
                label_visibility="collapsed",
            )
            st.warning(
                "These suggestions use only saved profile facts. Review every "
                "claim before using it."
            )

    with summary_tab:
        jobs = get_jobs()
        summary = build_daily_summary(jobs)
        st.subheader("Notification Agent daily digest")
        st.caption(
            "Generate a daily review for email, notes, or scheduling. "
            "Nothing is sent without your action."
        )
        st.markdown(summary)
        st.download_button(
            "Download daily summary",
            summary.encode("utf-8"),
            "career_command_daily_summary.md",
            "text/markdown",
        )


def interview_page(profile: dict) -> None:
    st.title("Personal Interview Coach")
    st.caption("Prepare from real experience without inventing claims.")
    shortlist_tab, analyzer, questions_tab, mock_tab, history_tab = st.tabs(
        ["Prepare shortlisted job", "JD analyzer", "Question bank", "Mock interview", "History"]
    )
    with shortlist_tab:
        jobs = get_jobs()
        shortlisted = jobs[
            jobs["status"].isin(["Shortlisted", "Apply", "Applied", "Interview"])
        ] if not jobs.empty else jobs
        if shortlisted.empty:
            st.info(
                "No shortlisted jobs yet. Run Search internet and shortlist a role first."
            )
        else:
            options = {
                f"{row['title']} - {row['company']} ({row['fit_score']}/100)": row
                for row in shortlisted.to_dict("records")
            }
            selected_label = st.selectbox(
                "Choose a shortlisted job", list(options)
            )
            selected = options[selected_label]
            st.write(
                f"**Location:** {selected['location']}  \n"
                f"**Source:** {selected['source']}  \n"
                f"**Current status:** {selected['status']}"
            )
            if selected["url"]:
                st.link_button("Review job listing", selected["url"])
            if st.button("Prepare interview for this job", type="primary"):
                analysis = analyze_job_description(
                    selected["title"],
                    selected["company"],
                    selected["description"],
                    profile,
                )
                st.session_state["jd_analysis"] = analysis
                st.session_state["questions"] = generate_questions(analysis, profile)
                st.session_state["mock_index"] = 0
                st.session_state["selected_job_id"] = selected["id"]
                st.success(
                    "Interview pack prepared. Open Question bank or Mock interview."
                )
            st.text_area(
                "Job description",
                selected["description"],
                height=260,
                disabled=True,
            )
    with analyzer:
        c1, c2 = st.columns(2)
        role = c1.text_input("Target role", "Cloud Data Platform Architect")
        company = c2.text_input("Company")
        jd = st.text_area("Job description", height=300)
        use_ai = st.checkbox(
            "Use OpenAI for additional coaching",
            help="Requires OPENAI_API_KEY. Rules-based analysis always works.",
        )
        if st.button("Analyze role", type="primary"):
            if len(jd) < 80:
                st.error("Paste a complete job description first.")
            else:
                analysis = analyze_job_description(role, company, jd, profile)
                st.session_state["jd_analysis"] = analysis
                st.session_state["questions"] = generate_questions(analysis, profile)
                st.session_state["use_ai"] = use_ai
        if analysis := st.session_state.get("jd_analysis"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Profile match", f"{analysis['score']}/100")
            c2.metric("Matched skills", len(analysis["matched_skills"]))
            c3.metric("Preparation gaps", len(analysis["gaps"]))
            st.write("**Matched strengths:**", ", ".join(analysis["matched_skills"]) or "Leadership and architecture")
            st.write("**Gaps:**", ", ".join(analysis["gaps"]) or "No major tool gap")
            st.write("**Likely rounds:**")
            for item in analysis["likely_rounds"]:
                st.markdown(f"- {item}")

    with questions_tab:
        questions = st.session_state.get(
            "questions",
            generate_questions(
                analyze_job_description("Cloud Data Platform Architect", "", "", profile),
                profile,
            ),
        )
        category = st.selectbox(
            "Category", ["All", "Technical", "Architecture", "Scenario", "Behavioral"]
        )
        filtered = [q for q in questions if category == "All" or q["type"] == category]
        for index, question in enumerate(filtered, 1):
            with st.expander(f"{index}. [{question['type']}] {question['question']}"):
                st.write(question["guide"])

    with mock_tab:
        questions = st.session_state.get("questions")
        if not questions:
            st.info("Analyze a job description first.")
        else:
            index = st.session_state.get("mock_index", 0) % len(questions)
            current = questions[index]
            st.caption(f"{current['type']} | Question {index + 1} of {len(questions)}")
            st.subheader(current["question"])
            answer = st.text_area(
                "Your answer", height=250, key=f"answer_{index}",
                placeholder="Use context, your decision, tradeoffs, implementation, and outcome.",
            )
            c1, c2 = st.columns(2)
            if c1.button("Score answer", type="primary"):
                if len(answer.split()) < 25:
                    st.error("Give a fuller answer before scoring.")
                else:
                    scores = score_answer(answer)
                    analysis = st.session_state.get("jd_analysis", {})
                    feedback = improve_answer(
                        current["question"], answer, profile, analysis,
                        use_ai=st.session_state.get("use_ai", False),
                    )
                    add_interview_result(
                        analysis.get("role", "Target role"),
                        analysis.get("company", ""),
                        current["question"], answer, scores, feedback,
                    )
                    st.session_state["last_feedback"] = (scores, feedback)
            if c2.button("Next question"):
                st.session_state["mock_index"] = index + 1
                st.rerun()
            if result := st.session_state.get("last_feedback"):
                scores, feedback = result
                cols = st.columns(5)
                for col, name in zip(
                    cols, ["overall", "clarity", "depth", "seniority", "evidence"]
                ):
                    col.metric(name.title(), scores[name])
                st.markdown("### Coach feedback")
                st.write(feedback)

    with history_tab:
        results = get_interview_results()
        if results.empty:
            st.info("No mock interview results yet.")
        else:
            st.dataframe(results, hide_index=True, use_container_width=True)
            st.download_button(
                "Download interview history CSV",
                results.to_csv(index=False).encode("utf-8"),
                "interview_history.csv",
                "text/csv",
            )


def profile_page(profile: dict) -> None:
    st.title("Career Profile")
    st.caption("This profile drives job scoring and interview coaching.")
    with st.form("profile_form"):
        headline = st.text_input("Professional headline", profile["headline"])
        summary = st.text_area("Executive summary", profile["summary"], height=150)
        c1, c2 = st.columns(2)
        years = c1.number_input("Years of experience", 1, 50, profile["years"])
        team = c2.number_input("Current team size", 0, 1000, profile["team"])
        linkedin_url = st.text_input(
            "LinkedIn profile URL", profile.get("linkedin_url", "")
        )
        st.caption(
            "The URL is stored as a reference. The app does not scrape LinkedIn."
        )
        linkedin_text = st.text_area(
            "LinkedIn About / experience text",
            profile.get("linkedin_text", ""),
            height=130,
            help=(
                "Paste text exported from your LinkedIn profile if it contains "
                "useful details not already present in the CV."
            ),
        )
        roles = st.text_area("Target roles, one per line", "\n".join(profile["roles"]))
        target_companies = st.text_area(
            "Target companies, one per line",
            "\n".join(profile.get("target_companies", [])),
            height=120,
        )
        locations = st.text_input("Preferred locations", ", ".join(profile["locations"]))
        skills = st.text_area("Core skills", ", ".join(profile["skills"]), height=120)
        proof = st.text_area("Proof points, one per line", "\n".join(profile["proof"]), height=180)
        if st.form_submit_button("Save profile", type="primary"):
            updated = {
                "headline": headline.strip(), "summary": summary.strip(),
                "years": int(years), "team": int(team),
                "linkedin_url": linkedin_url.strip(),
                "linkedin_text": linkedin_text.strip(),
                "roles": [x.strip() for x in roles.splitlines() if x.strip()],
                "target_companies": [
                    x.strip() for x in target_companies.splitlines() if x.strip()
                ],
                "locations": [x.strip() for x in locations.split(",") if x.strip()],
                "skills": [x.strip() for x in skills.split(",") if x.strip()],
                "proof": [x.strip() for x in proof.splitlines() if x.strip()],
                "resume_text": profile.get("resume_text", ""),
            }
            save_profile(updated)
            st.success("Profile saved.")

    st.subheader("CV reader")
    cv_file = st.file_uploader("Upload a DOCX CV", type=["docx"])
    source = cv_file if cv_file else (DEFAULT_CV if DEFAULT_CV.exists() else None)
    if source and st.button("Read CV"):
        text = extract_docx_text(source)
        profile["resume_text"] = text
        save_profile(profile)
        st.success("CV text saved as the matching source for internet searches.")
        st.text_area("Extracted CV text", text, height=350)
        st.download_button("Download CV text", text.encode("utf-8"), "resume.txt")
    elif not source:
        st.info("Upload a DOCX CV to extract its text.")


apply_styles()
profile = load_profile()
st.sidebar.markdown("## Career Command")
st.sidebar.caption("Job intelligence and interview preparation")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Job Intelligence", "Interview Coach", "Career Profile"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.markdown("**Connected job search**")
st.sidebar.caption("Supported APIs provide live listings; SQLite stores your shortlist.")
if os.getenv("OPENAI_API_KEY"):
    st.sidebar.success("OpenAI coaching available")
else:
    st.sidebar.info("OpenAI is optional; rules-based coaching is active.")

if page == "Overview":
    overview_page(profile)
elif page == "Job Intelligence":
    jobs_page(profile)
elif page == "Interview Coach":
    interview_page(profile)
else:
    profile_page(profile)
