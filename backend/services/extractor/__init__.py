"""OSINT extraction engine — split into submodules for maintainability.

Public API (backward-compatible with the old single-file extractor):
    ALL_CATEGORIES, extract_page_safe, finalize_accum, compute_highlights, extract_all
"""
from .finalize import ALL_CATEGORIES, extract_page_safe, finalize_accum, extract_all  # noqa: F401
from .highlights import compute_highlights  # noqa: F401

# Re-export patterns and helpers for tests and external consumers
from .patterns import (  # noqa: F401
    EMAIL_RE, PHONE_RE, TRACKER_PATTERNS, SOCIAL_PATTERNS,
    S3_RE, GCS_RE, AZURE_RE, DO_SPACES_RE,
    AWS_KEY_RE, GOOGLE_API_RE, STRIPE_RE, TWILIO_RE, SENDGRID_RE,
    SLACK_WEBHOOK_RE, GITHUB_TOKEN_RE,
    SCRIPT_TECH_PATTERNS,
)
from .helpers import (  # noqa: F401
    is_email_excluded as _is_email_excluded,
    strip_wayback_artifacts as _strip_wayback_artifacts,
)

__all__ = [
    "ALL_CATEGORIES",
    "extract_page_safe",
    "finalize_accum",
    "compute_highlights",
    "extract_all",
    # Patterns
    "EMAIL_RE", "PHONE_RE", "TRACKER_PATTERNS", "SOCIAL_PATTERNS",
    "S3_RE", "GCS_RE", "AZURE_RE", "DO_SPACES_RE",
    "AWS_KEY_RE", "GOOGLE_API_RE", "STRIPE_RE", "TWILIO_RE",
    "SENDGRID_RE", "SLACK_WEBHOOK_RE", "GITHUB_TOKEN_RE",
    "SCRIPT_TECH_PATTERNS",
    # Helpers (prefixed for backward compat)
    "_is_email_excluded", "_strip_wayback_artifacts",
]
