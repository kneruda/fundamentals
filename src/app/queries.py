"""Backward-compatible import facade for the Streamlit application.

Query and service code is intentionally owned by :mod:`src.services.queries`.
Keep this module while Streamlit is supported so existing pages, scripts, and
tests do not need to migrate all at once.
"""

from src.services.queries import *  # noqa: F403
