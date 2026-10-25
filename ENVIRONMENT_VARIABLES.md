# Environment Variables & Configuration

The deployment also requires `MPESA_CALLBACK_URL` and accepts
`CORS_ALLOWED_ORIGINS` as a comma-separated frontend-origin allowlist. Keep
real values only in the hosting provider's environment settings.

This backend reads **all secrets from environment variables**. It never falls
back to hardcoded credentials, and it **fails fast** at startup if a required
variable is missing (the error message names the variable, never its value).

## Required variables (the API will not start without these)

| Variable | Used by | Required? |
|---|---|---|
| `MYSQL_PASSWORD` | Every `pymysql.connect(...)` | ✅ required (no default) |
| `MYSQL_HOST` | Every `pymysql.connect(...)` | default `mysql-victordesigner.alwaysdata.net` |
| `MYSQL_USER` | Every `pymysql.connect(...)` | default `victordesigner` |
| `MYSQL_DATABASE` | Every `pymysql.connect(...)` | default `victordesigner_fullstack` |
| `CLOUDINARY_CLOUD_NAME` | `cloudinary.config(...)` | ✅ required |
| `CLOUDINARY_API_KEY` | `cloudinary.config(...)` | ✅ required |
| `CLOUDINARY_API_SECRET` | `cloudinary.config(...)` | ✅ required |
| `MPESA_CONSUMER_KEY` | `/api/mpesa_payment` | ✅ required |
| `MPESA_CONSUMER_SECRET` | `/api/mpesa_payment` | ✅ required |
| `MPESA_PASSKEY` | `/api/mpesa_payment` | ✅ required |
| `FLASK_SECRET_KEY` | Flask session/token signing | optional (recommended) |

`cloud_name` is a public identifier, but it is still read from the environment
for consistency. `BusinessShortCode`, `AccountReference`, and M-Pesa callback
URLs are public configuration and remain ordinary constants in the code.

## Local development

The Flask app does **not** auto-load a `.env` file (production relies on the
hosting platform, not a local file). Two options for local runs:

**Option A — set the variables in your shell (PowerShell):**
```powershell
$env:MYSQL_PASSWORD=""
$env:CLOUDINARY_CLOUD_NAME="nxkypqxa"
$env:CLOUDINARY_API_KEY="134235845124775"
$env:CLOUDINARY_API_SECRET="ojDy41cD-Y0aRbbEqBC223CbLzs"
$env:MPESA_CONSUMER_KEY="GTWADFxIpUfDoNikNGqq1C3023evM6UH"
$env:MPESA_CONSUMER_SECRET="amFbAoUByPV2rM5A"
$env:MPESA_PASSKEY="bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
python api.py
```

**Option B — optional python-dotenv for development only** (not used by the
deployed app; install it only in your dev environment):
```powershell
pip install python-dotenv
```
and create a local `.env` from `.env.example`, then run with:
```
python -c "import os; os.chdir('.'); from dotenv import load_dotenv; load_dotenv(); import api; api.app.run(debug=True)"
```
`.env` is git-ignored.

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
