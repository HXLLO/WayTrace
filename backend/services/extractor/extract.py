"""Per-page extraction logic."""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

from .helpers import (
    ts_to_month,
    update_entity,
    is_email_excluded,
    normalize_phone,
    strip_wayback_artifacts,
)
from .patterns import (
    EMAIL_RE,
    PHONE_RE,
    TRACKER_PATTERNS,
    SOCIAL_PATTERNS,
    CLOUD_BUCKET_PATTERNS,
    API_KEY_PATTERNS,
    SCRIPT_TECH_PATTERNS,
    TECH_COMMENT_RE,
    CMS_CLASS_INDICATORS,
)


# Subdomain regex cache (per-domain, lazy)
_subdomain_re_cache: dict[str, re.Pattern] = {}


def _get_subdomain_re(domain: str) -> re.Pattern:
    pat = _subdomain_re_cache.get(domain)
    if pat is None:
        pat = re.compile(
            rf"([a-zA-Z0-9]([a-zA-Z0-9\-]{{0,61}}[a-zA-Z0-9])?\.{re.escape(domain)})"
        )
        _subdomain_re_cache[domain] = pat
    return pat


def extract_page(
    html: str, page_url: str, timestamp: str, domain: str, accum: dict,
    categories: set[str] | None = None,
) -> None:
    month = ts_to_month(timestamp)

    def _want(cat: str) -> bool:
        return categories is None or cat in categories

    html = strip_wayback_artifacts(html)
    tree = HTMLParser(html)

    # --- Links + Form Actions → Endpoints ---
    if _want("endpoints"):
        _extract_links(tree, domain, month, accum)
        _extract_form_endpoints(tree, month, accum)

    raw_text = html
    visible_text = tree.text(separator=" ")

    # --- Emails ---
    if _want("emails"):
        for match in EMAIL_RE.finditer(raw_text):
            email = match.group().lower()
            if not is_email_excluded(email):
                update_entity(accum["emails"], email, month, {"value": email})

    # --- Phones ---
    if _want("phones"):
        for match in PHONE_RE.finditer(visible_text):
            raw = match.group().strip()
            normalized = normalize_phone(raw)
            digits_only = re.sub(r"[^\d]", "", normalized)
            if len(digits_only) < 7 or len(digits_only) > 15:
                continue
            if re.match(r"^\d{4}[-/.]\d{2}[-/.]\d{2}$", raw.strip()):
                continue
            if re.match(r"^(19|20)\d{6}$", digits_only):
                continue
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}", raw.strip()):
                continue
            if re.match(r"^\d+\.\d+\.\d+", raw.strip()):
                continue
            update_entity(
                accum["phones"], digits_only, month,
                {"raw": raw, "normalized": normalized},
            )
        _extract_tel_phones(tree, month, accum)

    # --- Subdomains ---
    if _want("subdomains"):
        subdomain_re = _get_subdomain_re(domain)
        _extract_subdomains(raw_text, subdomain_re, domain, month, accum)

    # --- Trackers ---
    if _want("analytics_trackers"):
        for tracker_type, pattern in TRACKER_PATTERNS.items():
            for match in pattern.finditer(raw_text):
                tid = match.group(1) if match.lastindex else match.group()
                key = f"{tracker_type}:{tid}"
                update_entity(
                    accum["analytics_trackers"], key, month,
                    {"type": tracker_type, "id": tid},
                )

    # --- Social profiles ---
    if _want("social_profiles"):
        _extract_social(raw_text, month, accum)

    # --- Persons ---
    if _want("persons"):
        _extract_persons(tree, raw_text, month, accum)

    # --- Technologies ---
    if _want("technologies"):
        _extract_technologies(tree, raw_text, month, accum)


    # --- Cloud Buckets ---
    if _want("cloud_buckets"):
        for pattern in CLOUD_BUCKET_PATTERNS:
            for match in pattern.finditer(raw_text):
                bucket = match.group(0).lower()
                update_entity(accum["cloud_buckets"], bucket, month, {"value": bucket})

    # --- API Keys / Secrets ---
    if _want("api_keys"):
        for key_type, pattern in API_KEY_PATTERNS.items():
            for match in pattern.finditer(raw_text):
                secret = match.group(0)
                update_entity(
                    accum["api_keys"], secret, month,
                    {"type": key_type, "value": secret},
                )



# ---------------------------------------------------------------------------
# Sub-extractors
# ---------------------------------------------------------------------------


def _extract_links(
    tree: HTMLParser, domain: str, month: str, accum: dict,
) -> None:
    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            parsed = urlparse(href)
        except ValueError:
            continue
        link_domain = parsed.hostname or ""
        path = (parsed.path or "/").rstrip("/") or "/"
        if link_domain == "web.archive.org" or path.startswith("/web/"):
            continue
        if not link_domain or link_domain.endswith(domain):
            update_entity(accum["endpoints"], path, month, {"path": path})


def _extract_form_endpoints(
    tree: HTMLParser, month: str, accum: dict,
) -> None:
    """Extract internal paths from <form action> into endpoints."""
    for node in tree.css("form[action]"):
        action = node.attributes.get("action", "").strip()
        if not action or action == "#":
            continue
        if action.startswith("/"):
            path = action.rstrip("/") or "/"
            update_entity(accum["endpoints"], path, month, {"path": path})


def _extract_tel_phones(tree: HTMLParser, month: str, accum: dict) -> None:
    """Extract phone numbers from tel: href links."""
    for node in tree.css('a[href^="tel:"]'):
        href = node.attributes.get("href", "")
        raw = href[4:].strip()
        normalized = normalize_phone(raw)
        digits_only = re.sub(r"[^\d]", "", normalized)
        if 7 <= len(digits_only) <= 15:
            update_entity(accum["phones"], digits_only, month,
                          {"raw": raw, "normalized": normalized})


def _extract_subdomains(
    raw_text: str, subdomain_re: re.Pattern, domain: str, month: str, accum: dict
) -> None:
    for match in subdomain_re.finditer(raw_text):
        sub = match.group(0).lower()
        if sub == domain or sub == f"www.{domain}":
            continue
        idx = match.start()
        if idx >= 2 and raw_text[idx - 2] == "%" and raw_text[idx - 1:idx].isalnum():
            continue
        if re.match(r"^[0-9a-f]{1,2}[a-z]", sub):
            clean = re.sub(r"^[0-9a-f]{1,2}", "", sub)
            if clean and clean[0] != ".":
                sub = clean
            else:
                continue
        update_entity(accum["subdomains"], sub, month, {"value": sub})


def _extract_social(raw_text: str, month: str, accum: dict) -> None:
    for platform, pattern in SOCIAL_PATTERNS.items():
        for match in pattern.finditer(raw_text):
            handle = match.group(1).rstrip("/")
            if not handle:
                continue
            key = f"{platform}:{handle.lower()}"
            url_map = {
                "twitter": f"https://twitter.com/{handle}",
                "x": f"https://x.com/{handle}",
                "facebook": f"https://facebook.com/{handle}",
                "instagram": f"https://instagram.com/{handle}",
                "telegram": f"https://t.me/{handle}",
                "youtube": f"https://youtube.com/{handle}",
                "github": f"https://github.com/{handle}",
                "tiktok": f"https://tiktok.com/@{handle}",
                "snapchat": f"https://snapchat.com/add/{handle}",
            }
            if platform == "linkedin":
                segment = "company" if "/company/" in match.group(0) else "in"
                url = f"https://linkedin.com/{segment}/{handle}"
            else:
                url = url_map.get(platform, "")
            update_entity(
                accum["social_profiles"], key, month,
                {"platform": platform, "handle": handle, "url": url},
            )


def _extract_persons(
    tree: HTMLParser, raw_text: str, month: str, accum: dict
) -> None:
    for selector in ['meta[name="author"]', 'meta[property="article:author"]']:
        for node in tree.css(selector):
            name = node.attributes.get("content", "").strip()
            if name:
                update_entity(
                    accum["persons"], name.lower(), month,
                    {"name": name, "context": "meta:author"},
                )

    for node in tree.css("[class*=author], [class*=byline], [class*=writer]"):
        text = node.text(strip=True)
        if text and 2 < len(text) < 80:
            update_entity(
                accum["persons"], text.lower(), month,
                {"name": text, "context": "html:class"},
            )

    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
            _walk_jsonld_authors(data, month, accum)
        except (json.JSONDecodeError, TypeError):
            pass


def _walk_jsonld_authors(data, month: str, accum: dict) -> None:
    if isinstance(data, dict):
        if data.get("@type") == "Person" or "author" in data:
            author = data.get("author", data)
            if isinstance(author, dict):
                name = author.get("name", "").strip()
                if name:
                    update_entity(
                        accum["persons"], name.lower(), month,
                        {"name": name, "context": "json-ld"},
                    )
            elif isinstance(author, str) and author.strip():
                update_entity(
                    accum["persons"], author.strip().lower(), month,
                    {"name": author.strip(), "context": "json-ld"},
                )
        for v in data.values():
            _walk_jsonld_authors(v, month, accum)
    elif isinstance(data, list):
        for item in data:
            _walk_jsonld_authors(item, month, accum)


def _extract_technologies(
    tree: HTMLParser, raw_text: str, month: str, accum: dict
) -> None:
    for node in tree.css('meta[name="generator"], meta[name="powered-by"]'):
        content = node.attributes.get("content", "").strip()
        if content:
            parts = content.split()
            tech = parts[0]
            version = parts[1] if len(parts) > 1 else None
            update_entity(
                accum["technologies"], tech.lower(), month,
                {"technology": tech, "version": version},
            )

    for match in TECH_COMMENT_RE.finditer(raw_text):
        tech = match.group(1)
        update_entity(
            accum["technologies"], tech.lower(), month,
            {"technology": tech, "version": None},
        )

    for indicator, tech in CMS_CLASS_INDICATORS.items():
        if indicator in raw_text.lower():
            update_entity(
                accum["technologies"], tech.lower(), month,
                {"technology": tech, "version": None},
            )

    seen_techs: set[str] = set()
    for node in tree.css("script[src], link[href]"):
        src = node.attributes.get("src", "") or node.attributes.get("href", "")
        if not src:
            continue
        for tech_name, pattern in SCRIPT_TECH_PATTERNS.items():
            if tech_name.lower() in seen_techs:
                continue
            if pattern.search(src):
                seen_techs.add(tech_name.lower())
                update_entity(
                    accum["technologies"], tech_name.lower(), month,
                    {"technology": tech_name, "version": None},
                )


