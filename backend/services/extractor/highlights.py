"""Severity-ranked highlight generation from extraction results."""
from __future__ import annotations

import re


SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def compute_highlights(results: dict, domain: str) -> list[dict]:
    """Analyze extraction results and generate prioritized OSINT highlights."""
    highlights: list[dict] = []

    def _add(severity: str, category: str, title: str, detail: str, pivot_tip: str) -> None:
        highlights.append({
            "severity": severity,
            "category": category,
            "title": title,
            "detail": detail,
            "pivot_tip": pivot_tip,
        })

    # CRITICAL: API keys found
    api_keys = results.get("api_keys", [])
    if api_keys:
        types = set(k.get("type", "Unknown") for k in api_keys)
        _add(
            "CRITICAL", "api_keys",
            f"{len(api_keys)} API key(s) exposed ({', '.join(sorted(types))})",
            ", ".join(k.get("value", "")[:20] + "..." for k in api_keys[:5]),
            "Test if key is still active",
        )

    # CRITICAL: Cloud buckets exposed
    cloud_buckets = results.get("cloud_buckets", [])
    if cloud_buckets:
        _add(
            "CRITICAL", "cloud_buckets",
            f"{len(cloud_buckets)} cloud bucket(s) exposed",
            ", ".join(b.get("value", "") for b in cloud_buckets[:5]),
            "Check bucket permissions with aws-cli",
        )

    # HIGH: Internal emails @domain
    emails = results.get("emails", [])
    internal_emails = [e for e in emails if e.get("value", "").endswith(f"@{domain}")]
    if internal_emails:
        _add(
            "HIGH", "emails",
            f"{len(internal_emails)} internal email(s) @{domain}",
            ", ".join(e.get("value", "") for e in internal_emails[:5]),
            "Search on haveibeenpwned, LinkedIn, GitHub",
        )

    # HIGH: Subdomains discovered
    subdomains = results.get("subdomains", [])
    if subdomains:
        _add(
            "HIGH", "subdomains",
            f"{len(subdomains)} subdomain(s) discovered",
            ", ".join(s.get("value", "") for s in subdomains[:5]),
            "Resolve with dig, scan with nmap",
        )

    # HIGH: Interesting endpoints (/api, /admin, /login, /auth paths)
    endpoints = results.get("endpoints", [])
    interesting_re = re.compile(r"^/(api|admin|login|auth|dashboard|internal|staging|debug|graphql)", re.IGNORECASE)
    interesting_endpoints = [e for e in endpoints if interesting_re.match(e.get("path", ""))]
    if interesting_endpoints:
        _add(
            "HIGH", "endpoints",
            f"{len(interesting_endpoints)} sensitive endpoint(s) found",
            ", ".join(e.get("path", "") for e in interesting_endpoints[:5]),
            "Test endpoint for auth bypass or information disclosure",
        )

    # MEDIUM: Analytics trackers (cross-domain correlation)
    trackers = results.get("analytics_trackers", [])
    if trackers:
        types = set(t.get("type", "") for t in trackers)
        _add(
            "MEDIUM", "analytics_trackers",
            f"{len(trackers)} analytics tracker(s) found ({', '.join(sorted(types))})",
            ", ".join(f"{t.get('type', '')}:{t.get('id', '')}" for t in trackers[:5]),
            "Cross-reference tracker IDs to find related domains (same owner)",
        )

    # MEDIUM: Technology changes (first_seen != last_seen)
    techs = results.get("technologies", [])
    changed_techs = [t for t in techs if t.get("first_seen") != t.get("last_seen")]
    if changed_techs:
        details = ", ".join(
            f"{t.get('technology', '')} ({t.get('first_seen', '')} -> {t.get('last_seen', '')})"
            for t in changed_techs[:3]
        )
        _add(
            "MEDIUM", "technologies",
            f"{len(changed_techs)} technology change(s) detected",
            details,
            "Check old version for known CVEs",
        )

    # MEDIUM: Persons identified
    persons = results.get("persons", [])
    if persons:
        _add(
            "MEDIUM", "persons",
            f"{len(persons)} person(s) identified",
            ", ".join(p.get("name", "") for p in persons[:5]),
            "Search on LinkedIn, social networks",
        )

    # LOW: Social profiles
    socials = results.get("social_profiles", [])
    if socials:
        _add(
            "LOW", "social_profiles",
            f"{len(socials)} social profile(s) found",
            ", ".join(f"{s.get('platform', '')}:{s.get('handle', '')}" for s in socials[:5]),
            "Cross-reference handles across platforms",
        )

    highlights.sort(key=lambda h: SEVERITY_ORDER.get(h["severity"], 99))
    return highlights
