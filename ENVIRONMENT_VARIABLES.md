# Environment Variables & Configuration

The deployment also requires `MPESA_CALLBACK_URL` and accepts
`CORS_ALLOWED_ORIGINS` as a comma-separated frontend-origin allowlist. Keep
real values only in the hosting provider's environment settings.

This backend reads **all secrets from environment variables** and has no
hardcoded secret values. Secret variables currently default to empty strings,
so importing the Flask app does not fail when they are absent; database,
Cloudinary, and M-Pesa features still require valid values in the deployment
environment.

## Runtime configuration

| Variable | Used by | Required? |
|---|---|---|
| `MYSQL_PASSWORD` | Every `pymysql.connect(...)` | required for database access |
| `MYSQL_HOST` | Every `pymysql.connect(...)` | default `mysql-victordesigner.alwaysdata.net` |
| `MYSQL_USER` | Every `pymysql.connect(...)` | default `victordesigner` |
| `MYSQL_DATABASE` | Every `pymysql.connect(...)` | default `victordesigner_fullstack` |
| `CLOUDINARY_CLOUD_NAME` | `cloudinary.config(...)` | required for image uploads |
| `CLOUDINARY_API_KEY` | `cloudinary.config(...)` | required for image uploads |
| `CLOUDINARY_API_SECRET` | `cloudinary.config(...)` | required for image uploads |
| `MPESA_CONSUMER_KEY` | `/api/mpesa_payment` | required for M-Pesa payments |
| `MPESA_CONSUMER_SECRET` | `/api/mpesa_payment` | required for M-Pesa payments |
| `MPESA_PASSKEY` | `/api/mpesa_payment` | required for M-Pesa payments |
| `MPESA_CALLBACK_URL` | `/api/mpesa_payment` | required for M-Pesa payments |
| `FLASK_SECRET_KEY` | Flask session/token signing | optional (recommended) |

`cloud_name` is a public identifier, but it is still read from the environment
for consistency. `BusinessShortCode`, `AccountReference`, and M-Pesa callback
URLs are public configuration and remain ordinary constants in the code.

## Local development

Credentials must be entered only in private shell/environment settings.
`.env` files remain git-ignored and are not used in production.

## Vercel

- `vercel.json` builds `api.py` with `@vercel/python` and routes `/api/*` to that Flask function.
- `app.py` re-exports the `app` from `api.py`; there is one Flask app and the existing API routes remain registered there.
- Configure the MySQL, Cloudinary, and M-Pesa variables listed in the table in Vercel Project Settings → Environment Variables, for each deployment environment that needs them. Configure a stable random `FLASK_SECRET_KEY` if sessions/signing are used.
- The backend always allows `http://localhost:3000`, `http://127.0.0.1:3000`, and `https://fullstack-nu-umber.vercel.app`; `CORS_ALLOWED_ORIGINS` may add further trusted origins. `OPTIONS` is enabled for `/api/*`, with `Content-Type` and `Authorization` allowed.
- The canonical backend deployment URL is `https://victor-ap-is-rosy.vercel.app`; the source change takes effect there only after a successful Vercel deployment.

## AlwaysData (production)

1. In the AlwaysData Admin, open **Sites → your site → Edit**.
2. In the **Environment variables** section, add each variable above with its
   real value (same names — no `REACT_APP_` prefix; these are backend-only).
3. Save, then restart the site so Passenger reloads `api.py`.

No `.env` file is needed on production, and none is committed. If you ever test
a local `.env`, keep it out of Git (it is ignored) and delete it before
deploying.

## Migration script (migrate_images.py)

Reads from the same environment variables (MySQL + Cloudinary) or from a
git-ignored `.env.migration` file (template: `.env.migration.example`). The
migration script is independent of the Flask app's configuration and keeps its
explicit `--execute` guard. See `migrate_images.py --help`.

## Rules

- Never hardcode a secret in source code.
- Never commit `.env`, `.env.migration`, `*.sql` dumps, or logs.
- Never print secrets to logs, error responses, or the frontend.
- Reusing a compromised value is not made safe by *removing it from code* —
  rotate exposed credentials first (see the security review checklist).
