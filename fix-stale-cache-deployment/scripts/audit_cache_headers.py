#!/usr/bin/env python3
"""Audit deployment-related HTTP caching with bounded, evidence-first checks.

The tool uses only the Python standard library. It never prints cookie values or
Authorization data, redacts query strings and fragments by default, bounds
response bodies, and blocks non-loopback private or special-use network targets
unless the operator explicitly allows them.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser

TOOL_VERSION = "2.1.0"
USER_AGENT = f"deployment-cache-auditor/{TOOL_VERSION}"
DEFAULT_MAX_BODY = 1_500_000
DEFAULT_MAX_ASSETS = 8
LONG_LIVED_SECONDS = 30 * 24 * 60 * 60
ONE_YEAR_SECONDS = 365 * 24 * 60 * 60

ASSET_EXTENSIONS = {
    ".js",
    ".mjs",
    ".cjs",
    ".css",
    ".wasm",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".avif",
    ".svg",
    ".ico",
}
SERVICE_WORKER_NAMES = {
    "sw.js",
    "sw.mjs",
    "service-worker.js",
    "service-worker.mjs",
    "serviceworker.js",
    "serviceworker.mjs",
}
MANIFEST_NAMES = {"manifest.json", "site.webmanifest", "manifest.webmanifest"}
HEX_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{8,64}$", re.I)
MIXED_FINGERPRINT_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9_-]{8,64}$"
)
URL_IN_TEXT_RE = re.compile(r"https?://[^\s'\"<>]+", re.I)

CDN_HEADER_NAMES = (
    "age",
    "x-cache",
    "x-cache-hits",
    "cf-cache-status",
    "x-vercel-cache",
    "cdn-cache-control",
    "cloudflare-cdn-cache-control",
    "surrogate-control",
    "x-served-by",
    "x-timer",
    "via",
)
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    severity: str
    code: str
    message: str


@dataclass
class FetchedResponse:
    status: int | None
    final_url: str
    headers: object
    body: bytes
    body_truncated: bool
    elapsed_ms: int
    redirects: list[str]


@dataclass
class ResponseAudit:
    requested_url: str
    final_url: str
    status: int | None
    elapsed_ms: int | None
    content_type: str | None
    classification: str
    asset_identity_classification: str | None
    asset_html_fallback: bool
    cache_control: str | None
    cache_directives: dict[str, str | bool]
    cache_directive_duplicates: dict[str, list[str]]
    validators: dict[str, str]
    vary: str | None
    expires: str | None
    set_cookie_present: bool
    cdn_headers: dict[str, str]
    redirect_count: int
    body_truncated: bool
    findings: list[Finding] = field(default_factory=list)
    discovered_assets: list[str] = field(default_factory=list)
    revalidation: dict[str, object] | None = None
    fetch_error: str | None = None
    raw_discovered_assets: list[str] = field(default_factory=list, repr=False)


class AssetHTMLParser(HTMLParser):
    """Extract only deploy-relevant scripts, styles, preloads, and fonts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        tag = tag.lower()
        if tag == "script" and values.get("src"):
            self.urls.append(values["src"])
            return
        if tag != "link" or not values.get("href"):
            return
        rel_tokens = {token.lower() for token in values.get("rel", "").split()}
        as_value = values.get("as", "").lower()
        if rel_tokens.intersection({"stylesheet", "modulepreload"}):
            self.urls.append(values["href"])
        elif "preload" in rel_tokens and as_value in {"script", "style", "font"}:
            self.urls.append(values["href"])


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect target before urllib follows it."""

    def __init__(self, allow_private: bool) -> None:
        super().__init__()
        self.allow_private = allow_private
        self.redirects: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        validate_url(absolute, self.allow_private)
        self.redirects.append(absolute)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit entry documents, frontend assets, and service-worker cache policies."
    )
    parser.add_argument("urls", nargs="+", help="One or more http(s) URLs to audit")
    parser.add_argument(
        "--discover-assets",
        action="store_true",
        help="Discover and audit a bounded sample of scripts, styles, and fonts linked by HTML",
    )
    parser.add_argument(
        "--include-cross-origin-assets",
        action="store_true",
        help="Include linked assets on other origins. Private-network safety checks still apply.",
    )
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Probe ETag or Last-Modified with a conditional request",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--timeout", type=float, default=12.0, help="Per-request timeout in seconds. Default: 12")
    parser.add_argument(
        "--max-assets",
        type=int,
        default=DEFAULT_MAX_ASSETS,
        help=f"Maximum discovered assets per HTML page. Default: {DEFAULT_MAX_ASSETS}",
    )
    parser.add_argument(
        "--max-body",
        type=int,
        default=DEFAULT_MAX_BODY,
        help=f"Maximum response body bytes to read. Default: {DEFAULT_MAX_BODY}",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "never"),
        default="error",
        help="Exit nonzero at this finding level. Default: error",
    )
    parser.add_argument(
        "--allow-private-network",
        action="store_true",
        help="Allow non-loopback private/link-local targets. Use only for trusted staging or local infrastructure.",
    )
    parser.add_argument(
        "--show-query",
        action="store_true",
        help="Show query strings in output. They are redacted by default. URL fragments are always omitted.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    return parser.parse_args(argv)


def display_url(url: str, show_query: bool) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = parsed.query if show_query else ("<redacted>" if parsed.query else "")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def sanitize_text(text: str, show_query: bool) -> str:
    return URL_IN_TEXT_RE.sub(lambda match: display_url(match.group(0), show_query), text)


def validate_url(url: str, allow_private: bool) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http and https URLs are supported")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if parsed.username or parsed.password:
        raise ValueError("credentials embedded in URLs are not allowed")

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError(f"invalid port: {exc}") from exc
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, port)}
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed: {exc}") from exc

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            continue
        if ip.is_loopback:
            continue
        if not ip.is_global and not allow_private:
            raise ValueError(
                f"target resolves to private or special-use address {ip}; "
                "pass --allow-private-network only for a trusted target"
            )


def header_values(headers: object, name: str) -> list[str]:
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = get_all(name) or []
        return [str(value).strip() for value in values if str(value).strip()]
    get = getattr(headers, "get", None)
    value = get(name) if callable(get) else None
    return [str(value).strip()] if value and str(value).strip() else []


def header_value(headers: object, name: str) -> str | None:
    values = header_values(headers, name)
    return ", ".join(values) if values else None


def split_http_list(value: str) -> list[str]:
    """Split an HTTP comma list without splitting commas inside quoted strings."""

    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and quoted:
            current.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            current.append(char)
            continue
        if char == "," and not quoted:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def parse_cache_control(
    value: str | None,
) -> tuple[dict[str, str | bool], dict[str, list[str]]]:
    directives: dict[str, str | bool] = {}
    all_values: dict[str, list[str]] = {}
    if not value:
        return directives, {}

    for part in split_http_list(value):
        if "=" in part:
            key, raw_value = part.split("=", 1)
            normalized: str | bool = raw_value.strip()
            if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
                normalized = normalized[1:-1]
                normalized = normalized.replace('\\"', '"').replace("\\\\", "\\")
        else:
            key = part
            normalized = True
        name = key.strip().lower()
        if not name:
            continue
        display = "true" if normalized is True else str(normalized)
        all_values.setdefault(name, []).append(display)
        directives.setdefault(name, normalized)

    duplicates = {
        name: values
        for name, values in all_values.items()
        if len(values) > 1
    }
    return directives, duplicates


def int_directive(directives: dict[str, str | bool], name: str) -> int | None:
    value = directives.get(name)
    if value is None or value is True:
        return None
    try:
        parsed = int(str(value), 10)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def path_extension(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.lower()
    slash = path.rfind("/")
    dot = path.rfind(".")
    return path[dot:] if dot > slash else ""


def basename(url: str) -> str:
    return urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1].lower()


def is_asset_url(url: str) -> bool:
    return (
        path_extension(url) in ASSET_EXTENSIONS
        or basename(url) in SERVICE_WORKER_NAMES
        or basename(url) in MANIFEST_NAMES
    )


def _looks_like_fingerprint_token(token: str, *, allow_mixed: bool) -> bool:
    if HEX_FINGERPRINT_RE.fullmatch(token):
        return True
    return bool(allow_mixed and MIXED_FINGERPRINT_RE.fullmatch(token))


def is_fingerprinted(url: str) -> bool:
    """Conservatively detect content-addressed identities in URL paths."""

    path = urllib.parse.urlsplit(url).path
    for segment in filter(None, path.split("/")):
        stem = segment.rsplit(".", 1)[0]
        if _looks_like_fingerprint_token(stem, allow_mixed=False):
            return True
        if "." not in segment and _looks_like_fingerprint_token(segment, allow_mixed=True):
            return True
        for match in re.finditer(r"[._-]([A-Za-z0-9_-]{8,64})(?=[._-]|$)", stem):
            if _looks_like_fingerprint_token(match.group(1), allow_mixed=True):
                return True
    return False


def body_is_html(content_type: str | None, body: bytes) -> bool:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    preview = body[:1024].lstrip().lower()
    return (
        media_type == "text/html"
        or preview.startswith(b"<!doctype html")
        or preview.startswith(b"<html")
    )


def classify_asset_identity(
    requested_url: str,
    final_url: str,
    content_type: str | None,
) -> str | None:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    identity_url = requested_url if is_asset_url(requested_url) else final_url
    name = basename(identity_url)
    extension = path_extension(identity_url)

    if name in SERVICE_WORKER_NAMES:
        return "service-worker"
    if name in MANIFEST_NAMES:
        return "manifest"
    if extension in ASSET_EXTENSIONS:
        return "fingerprinted-asset" if is_fingerprinted(identity_url) else "unfingerprinted-asset"
    if media_type in {"application/javascript", "text/javascript", "text/css", "application/wasm"}:
        return "fingerprinted-asset" if is_fingerprinted(final_url) else "unfingerprinted-asset"
    return None


def classify(requested_url: str, final_url: str, content_type: str | None, body: bytes) -> str:
    """Classify the response while preserving asset identity separately."""

    asset_identity = classify_asset_identity(requested_url, final_url, content_type)
    if asset_identity and body_is_html(content_type, body):
        return "asset-html-fallback"
    if asset_identity:
        return asset_identity
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if body_is_html(content_type, body):
        return "html"
    if media_type.startswith("application/json"):
        return "json"
    return "other"


def add(findings: list[Finding], severity: str, code: str, message: str) -> None:
    findings.append(Finding(severity, code, message))


def is_asset_class(classification: str) -> bool:
    return classification in {
        "fingerprinted-asset",
        "unfingerprinted-asset",
        "asset-html-fallback",
        "service-worker",
        "manifest",
    }


def evaluate(
    *,
    classification: str,
    asset_identity_classification: str | None,
    asset_html_fallback: bool,
    status: int | None,
    directives: dict[str, str | bool],
    duplicate_directives: dict[str, list[str]],
    cache_control: str | None,
    set_cookie_present: bool,
    vary: str | None,
) -> list[Finding]:
    findings: list[Finding] = []
    max_age = int_directive(directives, "max-age")
    s_maxage = int_directive(directives, "s-maxage")
    immutable = "immutable" in directives
    no_cache = "no-cache" in directives
    no_store = "no-store" in directives
    public = "public" in directives
    private = "private" in directives

    if status is not None and status >= 400:
        severity = "error" if status in {404, 410} and is_asset_class(classification) else "warning"
        add(findings, severity, "HTTP_STATUS", f"Response status is {status}.")

    for directive, values in sorted(duplicate_directives.items()):
        add(
            findings,
            "error",
            "DUPLICATE_CACHE_DIRECTIVE",
            f"Cache-Control repeats {directive} with values {values}; intermediaries may interpret the conflict differently.",
        )

    for directive in ("max-age", "s-maxage"):
        if directive in directives and int_directive(directives, directive) is None:
            add(findings, "warning", "INVALID_CACHE_TTL", f"{directive} is not a nonnegative integer.")

    if public and private:
        add(findings, "error", "CONFLICTING_VISIBILITY", "Cache-Control contains both public and private.")
    if private and s_maxage is not None and s_maxage > 0:
        add(findings, "error", "PRIVATE_SHARED_TTL", "private conflicts with a positive s-maxage shared-cache lifetime.")
    if no_store and (
        public
        or immutable
        or (max_age is not None and max_age > 0)
        or (s_maxage is not None and s_maxage > 0)
    ):
        add(findings, "error", "CONFLICTING_DIRECTIVES", "no-store conflicts with reusable or immutable directives.")
    if set_cookie_present and (public or (s_maxage is not None and s_maxage > 0)):
        add(
            findings,
            "error",
            "PUBLIC_SET_COOKIE",
            "A response that sets a cookie is explicitly shared-cacheable. Verify that no personalized data can leak.",
        )
    if vary and vary.strip() == "*":
        add(findings, "warning", "VARY_STAR", "Vary: * prevents normal cache reuse and often indicates a misconfiguration.")

    if asset_html_fallback:
        add(
            findings,
            "error",
            "ASSET_HTML_FALLBACK",
            "An asset URL returned HTML. This commonly causes 'Unexpected token <', MIME errors, or failed module imports after deployment.",
        )

    policy_classification = asset_identity_classification or classification

    if policy_classification == "html":
        if immutable:
            add(findings, "error", "HTML_IMMUTABLE", "HTML is marked immutable and can keep referencing obsolete assets.")
        if max_age is not None and max_age >= LONG_LIVED_SECONDS and not no_cache:
            add(findings, "error", "HTML_LONG_BROWSER_TTL", f"HTML has max-age={max_age} without mandatory validation.")
        if s_maxage is not None and s_maxage >= LONG_LIVED_SECONDS and not no_cache:
            add(
                findings,
                "warning",
                "HTML_LONG_SHARED_TTL",
                f"HTML has s-maxage={s_maxage}. Confirm intentional SSR/ISR behavior and coordinated invalidation.",
            )
        if not cache_control:
            add(findings, "warning", "HTML_MISSING_POLICY", "HTML has no explicit Cache-Control policy.")
        elif no_store:
            add(findings, "info", "HTML_NO_STORE", "HTML is not reusable. This favors freshness but disables validator-based reuse.")
        elif no_cache or max_age == 0:
            add(findings, "info", "HTML_REVALIDATES", "HTML requires validation before normal reuse.")
        elif s_maxage is not None:
            add(
                findings,
                "info",
                "HTML_SHARED_CACHE",
                "HTML is eligible for shared caching. Validate framework and CDN revalidation semantics.",
            )
        else:
            add(
                findings,
                "warning",
                "HTML_FRESHNESS_UNCLEAR",
                "HTML can be reused without an obvious validation or shared-cache strategy. Confirm the rendering model.",
            )

    elif policy_classification == "fingerprinted-asset":
        if no_store or no_cache:
            add(findings, "warning", "HASHED_ASSET_NOT_REUSED", "A fingerprinted asset is forced to revalidate or not be stored.")
        if max_age is None:
            add(findings, "warning", "HASHED_ASSET_MISSING_TTL", "A fingerprinted asset has no max-age.")
        elif max_age < LONG_LIVED_SECONDS:
            add(findings, "warning", "HASHED_ASSET_SHORT_TTL", f"A fingerprinted asset has max-age={max_age}, under 30 days.")
        if immutable and max_age is not None and max_age >= ONE_YEAR_SECONDS:
            add(findings, "info", "HASHED_ASSET_OPTIMAL", "A fingerprinted asset uses a one-year immutable policy.")
        elif not immutable:
            add(findings, "info", "HASHED_ASSET_NOT_IMMUTABLE", "Consider immutable only after confirming content-addressed naming.")

    elif policy_classification == "unfingerprinted-asset":
        if immutable:
            add(
                findings,
                "error",
                "UNHASHED_IMMUTABLE",
                "An unfingerprinted asset is marked immutable; a later release can reuse the URL with different bytes.",
            )
        if max_age is not None and max_age >= LONG_LIVED_SECONDS:
            add(
                findings,
                "warning",
                "UNHASHED_LONG_TTL",
                f"An unfingerprinted asset has max-age={max_age}. Confirm another guaranteed versioning mechanism.",
            )
        if not cache_control:
            add(findings, "warning", "ASSET_MISSING_POLICY", "An asset has no explicit Cache-Control policy.")

    elif policy_classification == "service-worker":
        if immutable:
            add(findings, "error", "SW_IMMUTABLE", "The service-worker script is immutable, which can delay update discovery.")
        if max_age is not None and max_age > 86_400 and not no_cache:
            add(findings, "warning", "SW_LONG_TTL", f"The service-worker script has max-age={max_age} without validation.")
        if not cache_control:
            add(findings, "warning", "SW_MISSING_POLICY", "The service-worker script has no explicit update-oriented cache policy.")

    elif policy_classification == "manifest":
        if immutable:
            add(findings, "warning", "MANIFEST_IMMUTABLE", "The web app manifest is immutable although its URL is not fingerprinted.")
        if max_age is not None and max_age >= LONG_LIVED_SECONDS:
            add(findings, "warning", "MANIFEST_LONG_TTL", f"The manifest has max-age={max_age}; app metadata updates may be delayed.")

    if not findings:
        add(findings, "info", "NO_HIGH_CONFIDENCE_ISSUE", "No high-confidence cache-policy hazard was detected for this response.")
    return findings


def open_url(
    url: str,
    timeout: float,
    max_body: int,
    headers: dict[str, str] | None = None,
    *,
    allow_private: bool = False,
) -> FetchedResponse:
    validate_url(url, allow_private)
    redirect_handler = SafeRedirectHandler(allow_private)
    opener = urllib.request.build_opener(redirect_handler)
    request_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    start = time.monotonic()
    response = None
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        elapsed_ms = int((time.monotonic() - start) * 1000)
        body = response.read(max_body + 1)
        truncated = len(body) > max_body
        if truncated:
            body = body[:max_body]
        return FetchedResponse(
            status=getattr(response, "status", None) or getattr(response, "code", None),
            final_url=response.geturl(),
            headers=response.headers,
            body=body,
            body_truncated=truncated,
            elapsed_ms=elapsed_ms,
            redirects=list(redirect_handler.redirects),
        )
    finally:
        if response is not None:
            response.close()


def discover_assets(
    html: bytes,
    base_url: str,
    max_assets: int,
    include_cross_origin: bool = False,
) -> list[str]:
    parser = AssetHTMLParser()
    try:
        parser.feed(html.decode("utf-8", errors="replace"))
    except Exception:
        return []
    base = urllib.parse.urlsplit(base_url)
    results: list[str] = []
    seen: set[str] = set()
    for raw_url in parser.urls:
        absolute = urllib.parse.urljoin(base_url, raw_url)
        parsed = urllib.parse.urlsplit(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if not include_cross_origin and (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
            continue
        normalized = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
        if len(results) >= max_assets:
            break
    return results


def audit_one(
    url: str,
    *,
    timeout: float,
    max_body: int,
    max_assets: int,
    discover: bool,
    include_cross_origin: bool,
    revalidate: bool,
    allow_private: bool,
    show_query: bool,
) -> ResponseAudit:
    requested_display = display_url(url, show_query)
    try:
        fetched = open_url(url, timeout, max_body, allow_private=allow_private)
        validate_url(fetched.final_url, allow_private)
        final_display = display_url(fetched.final_url, show_query)
        content_type = header_value(fetched.headers, "Content-Type")
        cache_control = header_value(fetched.headers, "Cache-Control")
        directives, directive_duplicates = parse_cache_control(cache_control)
        asset_identity_classification = classify_asset_identity(url, fetched.final_url, content_type)
        classification = classify(url, fetched.final_url, content_type, fetched.body)
        asset_html_fallback = (
            asset_identity_classification is not None
            and body_is_html(content_type, fetched.body)
        )
        validators = {
            name: value
            for name in ("etag", "last-modified")
            if (value := header_value(fetched.headers, name)) is not None
        }
        cdn_headers = {
            name: value
            for name in CDN_HEADER_NAMES
            if (value := header_value(fetched.headers, name)) is not None
        }
        vary = header_value(fetched.headers, "Vary")
        expires = header_value(fetched.headers, "Expires")
        set_cookie_present = bool(header_values(fetched.headers, "Set-Cookie"))
        findings = evaluate(
            classification=classification,
            asset_identity_classification=asset_identity_classification,
            asset_html_fallback=asset_html_fallback,
            status=fetched.status,
            directives=directives,
            duplicate_directives=directive_duplicates,
            cache_control=cache_control,
            set_cookie_present=set_cookie_present,
            vary=vary,
        )
        if urllib.parse.urlsplit(url).scheme == "https" and urllib.parse.urlsplit(fetched.final_url).scheme == "http":
            add(findings, "error", "HTTPS_DOWNGRADE", "The request redirected from HTTPS to HTTP.")
        if fetched.body_truncated and classification == "html":
            add(findings, "warning", "BODY_TRUNCATED", "HTML exceeded the read limit; asset discovery may be incomplete.")

        assets = (
            discover_assets(
                fetched.body,
                fetched.final_url,
                max_assets,
                include_cross_origin=include_cross_origin,
            )
            if discover and classification == "html"
            else []
        )

        revalidation_result: dict[str, object] | None = None
        if revalidate and validators:
            conditional_headers: dict[str, str] = {}
            if "etag" in validators:
                conditional_headers["If-None-Match"] = validators["etag"]
            if "last-modified" in validators:
                conditional_headers["If-Modified-Since"] = validators["last-modified"]
            try:
                second = open_url(
                    fetched.final_url,
                    timeout,
                    min(max_body, 64_000),
                    conditional_headers,
                    allow_private=allow_private,
                )
                revalidation_result = {
                    "status": second.status,
                    "elapsed_ms": second.elapsed_ms,
                    "body_bytes": len(second.body),
                    "body_truncated": second.body_truncated,
                    "redirect_count": len(second.redirects),
                    "etag": header_value(second.headers, "ETag"),
                    "last_modified": header_value(second.headers, "Last-Modified"),
                }
                if second.status == 304:
                    add(findings, "info", "VALIDATOR_304", "Conditional revalidation returned 304 Not Modified.")
                elif second.status == 200:
                    add(
                        findings,
                        "info",
                        "VALIDATOR_200",
                        "Conditional revalidation returned 200. This can be valid, but no 304 response was used.",
                    )
            except Exception as exc:
                message = sanitize_text(str(exc), show_query)
                revalidation_result = {"error": message}
                add(findings, "warning", "REVALIDATION_PROBE_FAILED", f"Conditional probe failed: {message}")

        return ResponseAudit(
            requested_url=requested_display,
            final_url=final_display,
            status=fetched.status,
            elapsed_ms=fetched.elapsed_ms,
            content_type=content_type,
            classification=classification,
            asset_identity_classification=asset_identity_classification,
            asset_html_fallback=asset_html_fallback,
            cache_control=cache_control,
            cache_directives=directives,
            cache_directive_duplicates=directive_duplicates,
            validators=validators,
            vary=vary,
            expires=expires,
            set_cookie_present=set_cookie_present,
            cdn_headers=cdn_headers,
            redirect_count=len(fetched.redirects),
            body_truncated=fetched.body_truncated,
            findings=findings,
            discovered_assets=[display_url(asset, show_query) for asset in assets],
            revalidation=revalidation_result,
            raw_discovered_assets=assets,
        )
    except Exception as exc:
        message = sanitize_text(str(exc), show_query)
        return ResponseAudit(
            requested_url=requested_display,
            final_url=requested_display,
            status=None,
            elapsed_ms=None,
            content_type=None,
            classification="unknown",
            asset_identity_classification=None,
            asset_html_fallback=False,
            cache_control=None,
            cache_directives={},
            cache_directive_duplicates={},
            validators={},
            vary=None,
            expires=None,
            set_cookie_present=False,
            cdn_headers={},
            redirect_count=0,
            body_truncated=False,
            findings=[Finding("error", "FETCH_FAILED", message)],
            fetch_error=message,
        )


def audit_with_assets(args: argparse.Namespace) -> list[ResponseAudit]:
    audits: list[ResponseAudit] = []
    queued: list[tuple[str, bool]] = [(url, args.discover_assets) for url in args.urls]
    seen: set[str] = set()
    while queued:
        url, discover = queued.pop(0)
        canonical = urllib.parse.urldefrag(url)[0]
        if canonical in seen:
            continue
        seen.add(canonical)
        audit = audit_one(
            canonical,
            timeout=args.timeout,
            max_body=args.max_body,
            max_assets=args.max_assets,
            discover=discover,
            include_cross_origin=args.include_cross_origin_assets,
            revalidate=args.revalidate,
            allow_private=args.allow_private_network,
            show_query=args.show_query,
        )
        audits.append(audit)
        if discover and not audit.fetch_error:
            queued.extend((asset, False) for asset in audit.raw_discovered_assets)
    return audits


def print_human(audits: list[ResponseAudit]) -> None:
    for index, audit in enumerate(audits):
        if index:
            print()
        print(audit.final_url)
        print(f"  status: {audit.status if audit.status is not None else 'n/a'}")
        print(f"  classification: {audit.classification}")
        print(f"  cache-control: {audit.cache_control or '(missing)'}")
        if audit.cache_directive_duplicates:
            print(f"  duplicate directives: {json.dumps(audit.cache_directive_duplicates, sort_keys=True)}")
        if audit.validators:
            print(f"  validators: {json.dumps(audit.validators, sort_keys=True)}")
        if audit.cdn_headers:
            print(f"  edge headers: {json.dumps(audit.cdn_headers, sort_keys=True)}")
        if audit.redirect_count:
            print(f"  redirects: {audit.redirect_count}")
        if audit.discovered_assets:
            print(f"  discovered assets: {len(audit.discovered_assets)}")
        if audit.revalidation:
            print(f"  revalidation: {json.dumps(audit.revalidation, sort_keys=True)}")
        for finding in audit.findings:
            print(f"  [{finding.severity.upper()}] {finding.code}: {finding.message}")


def serialize(audits: list[ResponseAudit]) -> list[dict]:
    output: list[dict] = []
    for audit in audits:
        item = asdict(audit)
        item.pop("raw_discovered_assets", None)
        output.append(item)
    return output


def exit_code(audits: list[ResponseAudit], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = SEVERITY_ORDER[fail_on]
    return 1 if any(SEVERITY_ORDER[f.severity] >= threshold for audit in audits for f in audit.findings) else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    if args.max_assets < 0 or args.max_body < 1:
        print("error: --max-assets must be nonnegative and --max-body must be positive", file=sys.stderr)
        return 2

    audits = audit_with_assets(args)
    if args.json:
        json.dump(serialize(audits), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_human(audits)
    return exit_code(audits, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
