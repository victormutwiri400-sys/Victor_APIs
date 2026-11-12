"""Vercel entry point.

Vercel's Flask framework preset looks for a Flask instance named ``app`` at a
supported entrypoint (app.py, index.py, server.py, main.py, wsgi.py, asgi.py,
or the same names under src/ or app/).

This module simply re-exports the single Flask application defined in api.py.
No second app is created and no routes are registered twice — api.py remains the single source of truth for the application and its routes.

api.py reads MYSQL_*, CLOUDINARY_*, MPESA_*, and optional FLASK_SECRET_KEY and
CORS_ALLOWED_ORIGINS from the environment. Secret variables currently default
to empty strings, so configure them in Vercel for their features to work. See
ENVIRONMENT_VARIABLES.md for deployment configuration details.
"""

from api import app

__all__ = ["app"]
