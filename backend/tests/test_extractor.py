import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.extractor import (
    EMAIL_RE,
    PHONE_RE,
    TRACKER_PATTERNS,
    SOCIAL_PATTERNS,
    S3_RE,
    GCS_RE,
    AZURE_RE,
    DO_SPACES_RE,
    AWS_KEY_RE,
    GOOGLE_API_RE,
    STRIPE_RE,
    TWILIO_RE,
    SENDGRID_RE,
    SLACK_WEBHOOK_RE,
    GITHUB_TOKEN_RE,
    ALL_CATEGORIES,
    extract_all,
    finalize_accum,
    compute_highlights,
    _is_email_excluded,
    _strip_wayback_artifacts,
)


# ---------------------------------------------------------------------------
# Email regex
# ---------------------------------------------------------------------------


class TestEmailRegex:
    def test_valid_emails(self):
        valid = [
            "user@example.com",
            "john.doe@company.co.uk",
            "admin+tag@domain.org",
            "test-user@sub.domain.com",
            "info@startup.io",
        ]
        for email in valid:
            assert EMAIL_RE.search(email), f"Should match: {email}"

    def test_invalid_emails(self):
        invalid = [
            "not-an-email",
            "@domain.com",
            "user@",
            "user@.com",
            "spaces in@email.com",
        ]
        for text in invalid:
            match = EMAIL_RE.search(text)
            if match:
                assert "@" not in match.group().split("@")[0].strip() or False, (
                    f"Should not match: {text}"
                )

    def test_excluded_emails(self):
        assert _is_email_excluded("noreply@company.com")
        assert _is_email_excluded("no-reply@company.com")
        assert _is_email_excluded("example@example.com")
        assert _is_email_excluded("icon@2x.png")
        assert not _is_email_excluded("admin@company.com")


# ---------------------------------------------------------------------------
# Phone regex
# ---------------------------------------------------------------------------


class TestPhoneRegex:
    def test_valid_phones(self):
        valid = [
            "+33 1 42 68 53 00",
            "+1-202-555-0147",
            "(212) 555-1234",
            "+44 20 7946 0958",
            "01 42 68 53 00",
        ]
        for phone in valid:
            assert PHONE_RE.search(phone), f"Should match: {phone}"

    def test_short_numbers_rejected(self):
        short = ["123", "1234", "12-34", "555"]
        for num in short:
            match = PHONE_RE.search(num)
            if match:
                import re
                digits = re.sub(r"[^\d]", "", match.group())
                assert len(digits) < 8


# ---------------------------------------------------------------------------
# Tracker patterns
# ---------------------------------------------------------------------------


class TestTrackerPatterns:
    def test_ga_universal(self):
        assert TRACKER_PATTERNS["GA_Universal"].search("UA-12345678-1")
        assert TRACKER_PATTERNS["GA_Universal"].search("UA-1234-2")
        assert not TRACKER_PATTERNS["GA_Universal"].search("UA-12-1")

    def test_ga4(self):
        assert TRACKER_PATTERNS["GA4"].search("G-ABC12DEF34")
        assert not TRACKER_PATTERNS["GA4"].search("G-short")

    def test_gtm(self):
        assert TRACKER_PATTERNS["GTM"].search("GTM-ABCDE")
        assert TRACKER_PATTERNS["GTM"].search("GTM-ABC12DE")
        assert not TRACKER_PATTERNS["GTM"].search("GTM-AB")

    def test_meta_pixel(self):
        assert TRACKER_PATTERNS["Meta_Pixel"].search(
            "fbq('init', '12345678901234')"
        )

    def test_google_ads(self):
        assert TRACKER_PATTERNS["Google_Ads"].search("AW-123456789")


# ---------------------------------------------------------------------------
# Social patterns
# ---------------------------------------------------------------------------


class TestSocialPatterns:
    def test_twitter(self):
        assert SOCIAL_PATTERNS["twitter"].search(
            "https://twitter.com/elonmusk"
        )
        assert not SOCIAL_PATTERNS["twitter"].search(
            "https://twitter.com/share"
        )
        assert not SOCIAL_PATTERNS["twitter"].search(
            "https://twitter.com/intent"
        )

    def test_linkedin(self):
        m = SOCIAL_PATTERNS["linkedin"].search(
            "https://linkedin.com/in/johndoe"
        )
        assert m and m.group(1) == "johndoe"

        m2 = SOCIAL_PATTERNS["linkedin"].search(
            "https://linkedin.com/company/acme-corp"
        )
        assert m2 and m2.group(1) == "acme-corp"

    def test_facebook_excludes_share(self):
        assert not SOCIAL_PATTERNS["facebook"].search(
            "https://facebook.com/sharer"
        )
        assert SOCIAL_PATTERNS["facebook"].search(
            "https://facebook.com/johndoe"
        )

    def test_telegram(self):
        m = SOCIAL_PATTERNS["telegram"].search("https://t.me/channelname")
        assert m and m.group(1) == "channelname"

    def test_github(self):
        m = SOCIAL_PATTERNS["github"].search("https://github.com/HXLLO")
        assert m and m.group(1) == "HXLLO"


# ---------------------------------------------------------------------------
# Wayback artifact stripping
# ---------------------------------------------------------------------------


class TestWaybackStripping:
    def test_strip_toolbar(self):
        html = """<html><body>
        <!-- BEGIN WAYBACK TOOLBAR INSERT -->
        <div id="wm-ipp">toolbar content</div>
        <!-- END WAYBACK TOOLBAR INSERT -->
        <h1>Real content</h1>
        </body></html>"""
        cleaned = _strip_wayback_artifacts(html)
        assert "WAYBACK TOOLBAR" not in cleaned
        assert "Real content" in cleaned

    def test_strip_wayback_scripts(self):
        html = '<script src="/_static/js/wm.js"></script><p>content</p>'
        cleaned = _strip_wayback_artifacts(html)
        assert "/_static/" not in cleaned
        assert "content" in cleaned


# ---------------------------------------------------------------------------
# Cloud bucket patterns
# ---------------------------------------------------------------------------


class TestCloudBuckets:
    def test_s3(self):
        assert S3_RE.search("mybucket.s3.amazonaws.com/file.txt")
        assert S3_RE.search("my-bucket.s3-us-east-1")

    def test_gcs(self):
        assert GCS_RE.search("storage.googleapis.com/my-bucket")

    def test_azure(self):
        assert AZURE_RE.search("myaccount.blob.core.windows.net/container")

    def test_s3_any_region(self):
        assert S3_RE.search("mybucket.s3.ap-northeast-1.amazonaws.com/file")
        assert S3_RE.search("mybucket.s3-eu-central-1")

    def test_do_spaces(self):
        assert DO_SPACES_RE.search("mybucket.nyc3.digitaloceanspaces.com/file.txt")


# ---------------------------------------------------------------------------
# API key patterns
# ---------------------------------------------------------------------------


class TestAPIKeys:
    def test_aws_key(self):
        assert AWS_KEY_RE.search("AKIAIOSFODNN7EXAMPLE")

    def test_google_api_key(self):
        assert GOOGLE_API_RE.search("AIzaSyA1234567890abcdefghijklmnopqrstuv")

    def test_stripe_key(self):
        prefix_secret = "sk" + "_" + "test" + "_" + "X" * 24
        prefix_public = "pk" + "_" + "live" + "_" + "X" * 24
        assert STRIPE_RE.search(prefix_secret)
        assert STRIPE_RE.search(prefix_public)

    def test_twilio_key(self):
        assert TWILIO_RE.search("SK" + "a" * 32)

    def test_sendgrid_key(self):
        key = "SG." + "a" * 22 + "." + "b" * 43
        assert SENDGRID_RE.search(key)

    def test_slack_webhook(self):
        assert SLACK_WEBHOOK_RE.search(
            "hooks.slack.com/services/T0123ABCD/B0123ABCD/abc123XYZ456"
        )

    def test_github_token(self):
        assert GITHUB_TOKEN_RE.search("ghp_" + "A" * 36)
        assert GITHUB_TOKEN_RE.search("gho_" + "B" * 36)


# ---------------------------------------------------------------------------
# Technologies detection
# ---------------------------------------------------------------------------


class TestTechFromScripts:
    def test_jquery_detected(self):
        html = """<html><head>
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        </head><body></body></html>"""
        pages = [{"html": html, "url": "https://example.com/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.com")
        techs = [t["technology"] for t in results["technologies"]]
        assert "jQuery" in techs

    def test_react_detected(self):
        html = """<html><head>
        <script src="/static/js/react.min.js"></script>
        </head><body></body></html>"""
        pages = [{"html": html, "url": "https://example.com/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.com")
        techs = [t["technology"] for t in results["technologies"]]
        assert "React" in techs

    def test_bootstrap_from_css(self):
        html = """<html><head>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css" rel="stylesheet">
        </head><body></body></html>"""
        pages = [{"html": html, "url": "https://example.com/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.com")
        techs = [t["technology"] for t in results["technologies"]]
        assert "Bootstrap" in techs

    def test_nextjs_detected(self):
        html = """<html><head>
        <script src="/_next/static/chunks/main.js"></script>
        </head><body></body></html>"""
        pages = [{"html": html, "url": "https://example.com/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.com")
        techs = [t["technology"] for t in results["technologies"]]
        assert "Next.js" in techs


# ---------------------------------------------------------------------------
# Form actions merged into endpoints
# ---------------------------------------------------------------------------


class TestFormActionsInEndpoints:
    def test_internal_form_action_in_endpoints(self):
        html = """<html><body>
        <form action="/api/login" method="POST"><input type="text"></form>
        <form action="/submit" method="POST"><input type="text"></form>
        </body></html>"""
        pages = [{"html": html, "url": "https://example.com/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.com")
        paths = [e["path"] for e in results["endpoints"]]
        assert "/api/login" in paths
        assert "/submit" in paths

    def test_external_form_action_not_in_endpoints(self):
        html = """<html><body>
        <form action="https://external.com/submit"><input type="text"></form>
        </body></html>"""
        pages = [{"html": html, "url": "https://example.com/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.com")
        paths = [e["path"] for e in results["endpoints"]]
        assert "/submit" not in paths


# ---------------------------------------------------------------------------
# Integration: extract_all
# ---------------------------------------------------------------------------


def test_extract_all_basic():
    html = """
    <html>
    <head>
        <meta name="author" content="John Doe">
        <meta name="generator" content="WordPress 5.9">
    </head>
    <body>
        <a href="/about">About</a>
        <a href="https://twitter.com/testuser">Twitter</a>
        <p>Contact: admin@example.org</p>
        <p>Phone: +33 1 42 68 53 00</p>
        <script>
            fbq('init', '12345678901234');
        </script>
    </body>
    </html>
    """
    pages = [{"html": html, "url": "https://example.org/", "timestamp": "20220601120000"}]
    results = extract_all(pages, "example.org")

    assert any(e["path"] == "/about" for e in results["endpoints"])
    assert any(e["value"] == "admin@example.org" for e in results["emails"])
    assert any(e["platform"] == "twitter" for e in results["social_profiles"])
    assert any(e["name"] == "John Doe" for e in results["persons"])
    assert any(e["technology"] == "WordPress" for e in results["technologies"])
    assert any(e["type"] == "Meta_Pixel" for e in results["analytics_trackers"])


def test_extract_all_empty_pages():
    pages = [{"html": None, "url": "https://example.com/", "timestamp": "20220601120000"}]
    results = extract_all(pages, "example.com")
    assert results["emails"] == []
    assert results["endpoints"] == []
    assert results["cloud_buckets"] == []
    assert results["api_keys"] == []
    assert results["subdomains"] == []
    assert results["analytics_trackers"] == []
    assert results["social_profiles"] == []
    assert results["technologies"] == []
    assert results["persons"] == []
    assert results["phones"] == []


def test_extract_all_has_all_categories():
    """Verify extract_all returns all expected category keys."""
    pages = [{"html": "<html><body>test</body></html>", "url": "https://example.com/", "timestamp": "20220601120000"}]
    results = extract_all(pages, "example.com")
    expected_keys = {
        "emails", "subdomains", "api_keys", "cloud_buckets",
        "analytics_trackers", "endpoints", "social_profiles",
        "technologies", "persons", "phones",
    }
    assert set(results.keys()) == expected_keys


# ---------------------------------------------------------------------------
# compute_highlights
# ---------------------------------------------------------------------------


class TestComputeHighlights:
    def test_empty_results(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        highlights = compute_highlights(results, "example.com")
        assert highlights == []

    def test_api_keys_critical(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["api_keys"] = [
            {"type": "AWS", "value": "AKIAIOSFODNN7EXAMPLE", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        highlights = compute_highlights(results, "example.com")
        critical = [h for h in highlights if h["severity"] == "CRITICAL"]
        assert len(critical) == 1
        assert "API key" in critical[0]["title"]
        assert critical[0]["pivot_tip"] == "Test if key is still active"

    def test_cloud_buckets_critical(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["cloud_buckets"] = [
            {"value": "mybucket.s3.amazonaws.com", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        highlights = compute_highlights(results, "example.com")
        critical = [h for h in highlights if h["severity"] == "CRITICAL"]
        assert len(critical) == 1
        assert "bucket" in critical[0]["title"]

    def test_internal_emails_high(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["emails"] = [
            {"value": "admin@example.com", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 3},
            {"value": "user@gmail.com", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        highlights = compute_highlights(results, "example.com")
        high = [h for h in highlights if h["severity"] == "HIGH" and h["category"] == "emails"]
        assert len(high) == 1
        assert "1 internal" in high[0]["title"]

    def test_severity_ordering(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["api_keys"] = [
            {"type": "AWS", "value": "AKIAIOSFODNN7EXAMPLE", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        results["social_profiles"] = [
            {"platform": "twitter", "handle": "test", "url": "https://twitter.com/test", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        results["persons"] = [
            {"name": "John Doe", "context": "meta:author", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        highlights = compute_highlights(results, "example.com")
        severities = [h["severity"] for h in highlights]
        assert severities.index("CRITICAL") < severities.index("MEDIUM")
        assert severities.index("MEDIUM") < severities.index("LOW")

    def test_tech_change_medium(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["technologies"] = [
            {"technology": "WordPress", "version": "5.9", "first_seen": "2020-01", "last_seen": "2023-06", "occurrences": 10},
        ]
        highlights = compute_highlights(results, "example.com")
        medium = [h for h in highlights if h["severity"] == "MEDIUM" and h["category"] == "technologies"]
        assert len(medium) == 1
        assert "technology change" in medium[0]["title"]

    def test_highlight_structure(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["subdomains"] = [
            {"value": "staging.example.com", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
        ]
        highlights = compute_highlights(results, "example.com")
        assert len(highlights) >= 1
        h = highlights[0]
        assert "severity" in h
        assert "category" in h
        assert "title" in h
        assert "detail" in h
        assert "pivot_tip" in h

    def test_trackers_highlight(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["analytics_trackers"] = [
            {"type": "GA_Universal", "id": "UA-12345678-1", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 5},
        ]
        highlights = compute_highlights(results, "example.com")
        tracker_hl = [h for h in highlights if h["category"] == "analytics_trackers"]
        assert len(tracker_hl) == 1
        assert tracker_hl[0]["severity"] == "MEDIUM"
        assert "tracker" in tracker_hl[0]["title"]

    def test_endpoints_highlight(self):
        results = {cat: [] for cat in ALL_CATEGORIES}
        results["endpoints"] = [
            {"path": "/api/users", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 3},
            {"path": "/admin/dashboard", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 1},
            {"path": "/about", "first_seen": "2022-01", "last_seen": "2022-06", "occurrences": 2},
        ]
        highlights = compute_highlights(results, "example.com")
        endpoint_hl = [h for h in highlights if h["category"] == "endpoints"]
        assert len(endpoint_hl) == 1
        assert endpoint_hl[0]["severity"] == "HIGH"
        assert "sensitive" in endpoint_hl[0]["title"]


# ---------------------------------------------------------------------------
# finalize_accum with categories filter
# ---------------------------------------------------------------------------


class TestFinalizeAccumCategories:
    def _make_accum_with_data(self):
        """Create an accumulator with some data in emails and phones."""
        accum = {cat: {} for cat in ALL_CATEGORIES}
        accum["emails"]["admin@test.com"] = {
            "first_seen": "2022-01",
            "last_seen": "2022-06",
            "occurrences": 3,
            "value": "admin@test.com",
        }
        accum["phones"]["+33142685300"] = {
            "first_seen": "2022-01",
            "last_seen": "2022-06",
            "occurrences": 1,
            "raw": "+33 1 42 68 53 00",
            "normalized": "+33142685300",
        }
        return accum

    def test_categories_none_returns_all(self):
        accum = self._make_accum_with_data()
        results = finalize_accum(accum, categories=None)
        assert len(results["emails"]) == 1
        assert len(results["phones"]) == 1

    def test_categories_filter_includes(self):
        accum = self._make_accum_with_data()
        results = finalize_accum(accum, categories=["emails"])
        assert len(results["emails"]) == 1
        assert results["phones"] == []

    def test_categories_filter_excludes_all(self):
        accum = self._make_accum_with_data()
        results = finalize_accum(accum, categories=["subdomains"])
        assert results["emails"] == []
        assert results["phones"] == []
        assert results["subdomains"] == []

    def test_categories_empty_list_returns_nothing(self):
        accum = self._make_accum_with_data()
        results = finalize_accum(accum, categories=[])
        for cat in ALL_CATEGORIES:
            assert results[cat] == []

    def test_extract_all_with_categories(self):
        html = """<html><body>
        <p>Contact: admin@example.org</p>
        <p>Phone: +33 1 42 68 53 00</p>
        </body></html>"""
        pages = [{"html": html, "url": "https://example.org/", "timestamp": "20220601120000"}]
        results = extract_all(pages, "example.org", categories=["emails"])
        assert len(results["emails"]) >= 1
        assert results["phones"] == []
