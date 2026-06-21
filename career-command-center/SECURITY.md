# Security Policy

## Reporting a vulnerability

Please open a GitHub issue containing only non-sensitive details. Do not include credentials, personal data, exploit payloads, or private job-search information. For sensitive reports, contact the repository owner privately through their GitHub profile.

## Secret handling

- Keep credentials in environment variables or an untracked `.streamlit/secrets.toml` file.
- Never commit `profile.json`, `settings.json`, `career_command.db`, CVs, exports, or interview history.
- Rotate any credential immediately if it is exposed in a commit, log, screenshot, or issue.
- Review dependency updates before deployment and put authentication in front of any internet-accessible instance.
