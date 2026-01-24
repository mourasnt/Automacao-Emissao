# Security & Secrets Handling

This project previously contained sensitive files under `dados/credentials.json` and `dados/auth.json` which have been removed from the repository and replaced with examples (`dados/credentials.json.example`, `dados/auth.json.example`).

Recommendations:

- Do not commit credentials or tokens to git. Add them to `.gitignore` (already added).
- Use environment variables or a secret manager for production secrets (e.g., Docker secrets, Vault, or cloud secret manager).
- If the sensitive files were already committed in earlier commits, rotate the keys immediately and consider rewriting git history (e.g., using `git filter-repo` or `git filter-branch`).
- For local development, copy `.env.example` to `.env` and populate it.
- For Docker deployment, prefer Docker secrets or bind a file at runtime (do not store secrets in images).

If you want, I can help generate steps to rotate keys and purge the secrets from git history.
