# Career Command Center

A privacy-conscious Streamlit application for discovering, evaluating, and tracking job opportunities and preparing for interviews.

## Features

- Imports roles from supported job APIs, official career pages, and pasted alerts.
- Normalizes, deduplicates, and scores opportunities against an editable profile.
- Adds credibility checks and explains fit, risks, and suggested next actions.
- Tracks the application pipeline in a local SQLite database.
- Generates role-specific interview questions and scores mock answers.
- Uses optional OpenAI coaching while retaining a rules-based offline path.

## Architecture

```text
CV + profile -> provider search -> normalize -> deduplicate
             -> credibility and fit scoring -> pipeline
             -> interview preparation -> feedback history
```

The UI is in `app.py`, provider and scoring logic is in `services.py`, and persistence is isolated in `database.py`.

## Run locally

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, `start-app.cmd` performs the dependency check and starts the app. You may optionally place a CV at `resume.docx`; the file is ignored by Git.

## Optional configuration

The application works without paid API credentials. For wider job coverage or AI coaching, set environment variables:

```powershell
$env:ADZUNA_APP_ID="your-app-id"
$env:ADZUNA_APP_KEY="your-app-key"
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-5-mini"
```

For Streamlit, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in local values. Never commit that file.

## Docker

```powershell
docker build -t career-command-center .
docker run --rm -p 8501:8501 career-command-center
```

Open <http://127.0.0.1:8501>.

## Privacy and safety

Local profiles, credentials, CVs, job history, exports, and interview answers are excluded through `.gitignore` and `.dockerignore`. The app does not submit applications automatically and intentionally avoids automated LinkedIn scraping. Verify job listings on the employer's official website before applying.

## License

MIT
