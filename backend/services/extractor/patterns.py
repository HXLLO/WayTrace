"""All regex patterns and constants used by the extractor."""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Core patterns
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

PHONE_RE = re.compile(
    r"(?<![.\d/@])"
    r"(?:"
    # Branch 1: international + prefix, e.g. +33 1 42 68 53 00, +1-800-555-1234
    r"\+\d{1,3}[\s\-.]?\(?\d{1,4}\)?(?:[\s\-.]?\d{2,5}){1,4}"
    r"|"
    # Branch 2: parens area code, e.g. (800) 555-1234
    r"\(\d{2,4}\)[\s\-.]?\d{2,4}(?:[\s\-.]?\d{2,4})+"
    r"|"
    # Branch 3: separated groups (≥2 separators), e.g. 01 42 68 53 00
    r"\d{2,4}[\s\-.]\d{2,4}(?:[\s\-.]?\d{2,4})+"
    r")"
    r"(?![\d.])"
)

TRACKER_PATTERNS = {
    "GA_Universal": re.compile(r"UA-\d{4,10}-\d{1,2}"),
    "GA4": re.compile(r"G-[A-Z0-9]{8,12}"),
    "GTM": re.compile(r"GTM-[A-Z0-9]{5,8}"),
    "Google_Ads": re.compile(r"AW-\d{9,12}"),
    "Meta_Pixel": re.compile(r"fbq\([^)]*[\"'](\d{14,16})[\"']"),
    "Hotjar": re.compile(r"hjid[:\s]*[\"']?(\d{5,10})[\"']?"),
    "Mixpanel": re.compile(r"mixpanel\.init\([\"']([a-f0-9]{32})[\"']"),
}

SOCIAL_PATTERNS = {
    "twitter": re.compile(r"twitter\.com/(?!share|intent)([A-Za-z0-9_]{1,50})"),
    "x": re.compile(r"(?<![a-zA-Z])x\.com/(?!share|intent)([A-Za-z0-9_]{1,50})"),
    "linkedin": re.compile(
        r"linkedin\.com/(?:in|company)/([A-Za-z0-9_\-]{1,100})"
    ),
    "facebook": re.compile(
        r"facebook\.com/(?!sharer|share|dialog)([A-Za-z0-9_.]{1,100})"
    ),
    "instagram": re.compile(r"instagram\.com/([A-Za-z0-9_.]{1,100})"),
    "telegram": re.compile(r"t\.me/([A-Za-z0-9_]{3,50})"),
    "youtube": re.compile(
        r"youtube\.com/(?:channel/|@|user/)([A-Za-z0-9_\-]{1,100})"
    ),
    "github": re.compile(r"github\.com/([A-Za-z0-9_\-]{1,100})"),
    "tiktok": re.compile(r"tiktok\.com/@([A-Za-z0-9_.]{1,50})"),
    "snapchat": re.compile(r"snapchat\.com/add/([A-Za-z0-9_.]{1,50})"),
}

# --- Cloud Buckets ---

S3_RE = re.compile(r"[a-z0-9.\-]+\.s3[.\-][^\s\"'<>]+", re.IGNORECASE)
GCS_RE = re.compile(r"storage\.googleapis\.com/[a-z0-9._\-]+", re.IGNORECASE)
AZURE_RE = re.compile(r"[a-z0-9]+\.blob\.core\.windows\.net[^\s\"'<>]*", re.IGNORECASE)
DO_SPACES_RE = re.compile(r"[a-z0-9.\-]+\.digitaloceanspaces\.com[^\s\"'<>]*", re.IGNORECASE)

CLOUD_BUCKET_PATTERNS = (S3_RE, GCS_RE, AZURE_RE, DO_SPACES_RE)

# --- API Keys / Secrets ---

AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
GOOGLE_API_RE = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
STRIPE_RE = re.compile(r"(?:sk|pk)_(?:test|live)_[0-9a-zA-Z]{24,}")
MAILGUN_RE = re.compile(r"key-[0-9a-zA-Z]{32}")
TWILIO_RE = re.compile(r"SK[0-9a-fA-F]{32}")
SENDGRID_RE = re.compile(r"SG\.[0-9A-Za-z_\-]{22}\.[0-9A-Za-z_\-]{43}")
SLACK_WEBHOOK_RE = re.compile(r"hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[a-zA-Z0-9]+")
GITHUB_TOKEN_RE = re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")

API_KEY_PATTERNS = {
    "AWS": AWS_KEY_RE,
    "Google_API": GOOGLE_API_RE,
    "Stripe": STRIPE_RE,
    "Mailgun": MAILGUN_RE,
    "Twilio": TWILIO_RE,
    "SendGrid": SENDGRID_RE,
    "Slack_Webhook": SLACK_WEBHOOK_RE,
    "GitHub": GITHUB_TOKEN_RE,
}

# --- Constants ---

EMAIL_EXCLUDE = {"noreply", "no-reply", "example"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

# --- Technology detection from script/link URLs ---

SCRIPT_TECH_PATTERNS = {
    "jQuery": re.compile(r"jquery[.\-/]", re.IGNORECASE),
    "React": re.compile(r"react(?:\.min)?\.js|react-dom", re.IGNORECASE),
    "Angular": re.compile(r"angular(?:\.min)?\.js|angular\.io", re.IGNORECASE),
    "Vue.js": re.compile(r"vue(?:\.min)?\.js|vuejs\.org", re.IGNORECASE),
    "Bootstrap": re.compile(r"bootstrap(?:\.min)?\.(?:js|css)", re.IGNORECASE),
    "Tailwind": re.compile(r"tailwindcss|tailwind\.min\.css", re.IGNORECASE),
    "Next.js": re.compile(r"_next/static|__next", re.IGNORECASE),
    "Nuxt": re.compile(r"_nuxt/", re.IGNORECASE),
    "Svelte": re.compile(r"svelte", re.IGNORECASE),
    "Lodash": re.compile(r"lodash(?:\.min)?\.js", re.IGNORECASE),
    "D3.js": re.compile(r"d3(?:\.min)?\.js|d3js\.org", re.IGNORECASE),
    "Moment.js": re.compile(r"moment(?:\.min)?\.js", re.IGNORECASE),
    "Font Awesome": re.compile(r"font-awesome|fontawesome", re.IGNORECASE),
    "Google Fonts": re.compile(r"fonts\.googleapis\.com", re.IGNORECASE),
    "Cloudflare": re.compile(r"cdnjs\.cloudflare\.com", re.IGNORECASE),
    "Unpkg": re.compile(r"unpkg\.com", re.IGNORECASE),
    "jsDelivr": re.compile(r"cdn\.jsdelivr\.net", re.IGNORECASE),
}

TECH_COMMENT_RE = re.compile(
    r"<!--\s*(WordPress|Joomla|Drupal|Typo3|Magento)[\s\d.]*-->", re.IGNORECASE
)

# --- Wayback artifact patterns ---

WAYBACK_TOOLBAR_RE = re.compile(
    r"<!-- BEGIN WAYBACK TOOLBAR INSERT -->.*?<!-- END WAYBACK TOOLBAR INSERT -->",
    re.DOTALL,
)
WAYBACK_SCRIPT_RE = re.compile(
    r'<script[^>]+src="/_static/[^"]*"[^>]*>.*?</script>',
    re.DOTALL | re.IGNORECASE,
)
WAYBACK_DIV_RE = re.compile(
    r'<div\s+id="wm-ipp-base"[^>]*>.*?</div>\s*</div>\s*</div>',
    re.DOTALL | re.IGNORECASE,
)

# --- CMS class indicators ---

CMS_CLASS_INDICATORS = {
    "wp-content": "WordPress",
    "wp-includes": "WordPress",
    "drupal": "Drupal",
    "joomla": "Joomla",
}
