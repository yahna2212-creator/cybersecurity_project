# Vercel setup

Test this edition in a separate preview/project before changing your current site.

1. Extract and push the project contents to GitHub. Deploy the branch containing this edition.
2. Set Root Directory to the repository root, not `client/` or `server/`. `pyproject.toml` declares `app:app`; `vercel.json` builds the React frontend.
3. Use Flask preset, Python 3.12 and Node 24. Remove old build overrides such as standalone `vite build`; retain the command supplied in `vercel.json`.
4. Add `MONGODB_URI`, `MONGODB_DB`, a newly generated `SESSION_SECRET`, `PUBLIC_URL` and `ADMIN_EMAIL`. PUBLIC_URL is the HTTPS origin without a path. Use Config for public/non-sensitive settings and Secret for credentials. Branch-specific overrides belong to Preview, not Production.
5. For email set `MAIL_MODE=smtp`, `MAIL_DELIVERY=inline` and SMTP settings. If email is not configured, use `disabled`; messages remain pending. Do not use local outbox files on ephemeral hosting.
6. Locally load the same MongoDB settings, enter `server`, run `python manage.py init-db` and `python manage.py create-admin --email YOUR_ADMIN_EMAIL`. Vercel deliberately does not connect to MongoDB at import. Initialization is not a public endpoint.
7. Redeploy after saving variables. Verify registration, verification email, login, authorization, persistent alerts and actual email delivery before production use.

Inline delivery handles a small batch per request. For retries during inactivity, configure authenticated scheduled calls to `/api/jobs/mail` using private `CRON_SECRET`, or host the mail worker separately. No scheduler is provisioned by the ZIP. Never prefix secrets with `VITE_`.

A Ready build or `/health` response alone does not prove working database/email/sensor connections. If Flask detection fails, verify the deployed branch/commit and root directory; an old frontend-only commit cannot supply this backend.
