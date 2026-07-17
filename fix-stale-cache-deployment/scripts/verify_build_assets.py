#!/usr/bin/env python3
"""Verify that generated entry documents reference files present in a build.

The verifier is deliberately framework-neutral. It checks local URLs found in
HTML, follows local CSS url() references, and optionally checks output paths from
selected JSON manifests. It never executes application code.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

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
    ".map",
    ".json",
    ".webmanifest",
}
HEX_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{8,64}$", re.I)
MIXED_FINGERPRINT_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9_-]{8,64}$")
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    severity: str
    code: str
    source: str
    reference: str
    message: str


@dataclass
class Report:
    root: str
    public_prefix: str
    html_files: list[str]
    manifests: list[str]
    references_checked: int
    existing_files: list[str] = field(default_factory=list)
    fingerprinted_files: list[str] = field(default_factory=list)
    unfingerprinted_assets: list[str] = field(default_factory=list)
    skipped_external: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


class ReferenceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        tag = tag.lower()
        if tag == "script" and values.get("src"):
            self.references.append(values["src"])
        elif tag == "link" and values.get("href"):
            rel_tokens = {token.lower() for token in values.get("rel", "").split()}
            if rel_tokens.intersection(
                {"stylesheet", "modulepreload", "preload", "icon", "manifest", "apple-touch-icon"}
            ):
                self.references.append(values["href"])
        elif tag in {"img", "audio", "video", "source", "track", "iframe", "embed"}:
            if values.get("src"):
                self.references.append(values["src"])
            if tag == "video" and values.get("poster"):
                self.references.append(values["poster"])
            if values.get("srcset"):
                self.references.extend(parse_srcset(values["srcset"]))
        elif tag == "object" and values.get("data"):
            self.references.append(values["data"])


def parse_srcset(value: str) -> list[str]:
    references: list[str] = []
    for item in value.split(","):
        candidate = item.strip().split(None, 1)[0] if item.strip() else ""
        if candidate:
            references.append(candidate)
    return references


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that generated HTML and selected manifests reference existing build files."
    )
    parser.add_argument("build_dir", help="Generated build or publish directory")
    parser.add_argument(
        "--entry",
        action="append",
        default=[],
        help="HTML entry path relative to the build directory. Repeatable. Default: all *.html files",
    )
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="JSON asset manifest relative to the build directory. Repeatable",
    )
    parser.add_argument(
        "--public-prefix",
        default="/",
        help="URL prefix mapped to the build root, such as /app/. Default: /",
    )
    parser.add_argument(
        "--no-css",
        action="store_true",
        help="Do not follow local url() references from discovered CSS files",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "never"),
        default="error",
        help="Exit nonzero at this finding level. Default: error",
    )
    return parser.parse_args(argv)


def normalize_public_prefix(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("--public-prefix must be a URL path, not a full URL")
    prefix = parsed.path or "/"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if not prefix.endswith("/"):
        prefix += "/"
    return prefix


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def looks_like_fingerprint_token(token: str, *, allow_mixed: bool) -> bool:
    if HEX_FINGERPRINT_RE.fullmatch(token):
        return True
    return bool(allow_mixed and MIXED_FINGERPRINT_RE.fullmatch(token))


def is_fingerprinted_path(path: str) -> bool:
    for segment in filter(None, Path(path).as_posix().split("/")):
        stem = segment.rsplit(".", 1)[0]
        if looks_like_fingerprint_token(stem, allow_mixed=False):
            return True
        if "." not in segment and looks_like_fingerprint_token(segment, allow_mixed=True):
            return True
        for match in re.finditer(r"[._-]([A-Za-z0-9_-]{8,64})(?=[._-]|$)", stem):
            if looks_like_fingerprint_token(match.group(1), allow_mixed=True):
                return True
    return False


def is_external_or_inline(reference: str) -> bool:
    lowered = reference.strip().lower()
    if not lowered:
        return True
    if lowered.startswith(("data:", "blob:", "javascript:", "mailto:", "tel:", "#")):
        return True
    parsed = urllib.parse.urlsplit(reference)
    return bool(parsed.scheme or parsed.netloc)


def resolve_reference(
    reference: str,
    *,
    source: Path,
    root: Path,
    public_prefix: str,
    relative_to_root: bool = False,
) -> tuple[Path | None, str | None]:
    parsed = urllib.parse.urlsplit(reference)
    decoded = urllib.parse.unquote(parsed.path)
    if "\x00" in decoded:
        return None, "reference contains a NUL byte"
    if not decoded:
        return None, "reference has no path"

    if decoded.startswith("/"):
        if public_prefix == "/":
            mapped = decoded.lstrip("/")
        elif decoded == public_prefix[:-1]:
            mapped = ""
        elif decoded.startswith(public_prefix):
            mapped = decoded[len(public_prefix) :]
        else:
            return None, f"root-relative URL is outside public prefix {public_prefix}"
        candidate = root / mapped
    else:
        candidate = (root if relative_to_root else source.parent) / decoded

    candidate = candidate.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None, "reference escapes the build directory"
    if decoded.endswith("/"):
        candidate = candidate / "index.html"
    return candidate, None


def read_html_references(path: Path) -> list[str]:
    parser = ReferenceHTMLParser()
    text = path.read_text(encoding="utf-8", errors="replace")
    parser.feed(text)
    return parser.references


def read_css_references(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [match.group(2).strip() for match in CSS_URL_RE.finditer(text) if match.group(2).strip()]


def collect_manifest_values(data: object, *, parent_key: str = "") -> Iterable[str]:
    if isinstance(data, dict):
        for key, value in data.items():
            lowered = str(key).lower()
            if lowered in {"file", "files", "css", "assets"}:
                yield from collect_strings(value)
            elif lowered == "src" and parent_key in {"icons", "screenshots"}:
                yield from collect_strings(value)
            else:
                yield from collect_manifest_values(value, parent_key=lowered)
    elif isinstance(data, list):
        for value in data:
            yield from collect_manifest_values(value, parent_key=parent_key)


def collect_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from collect_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from collect_strings(item)


def add_finding(
    report: Report,
    severity: str,
    code: str,
    source: str,
    reference: str,
    message: str,
) -> None:
    report.findings.append(Finding(severity, code, source, reference, message))


def record_existing(report: Report, path: Path, root: Path) -> None:
    value = relative(path, root)
    if value not in report.existing_files:
        report.existing_files.append(value)
    if path.suffix.lower() not in ASSET_EXTENSIONS:
        return
    if is_fingerprinted_path(value):
        if value not in report.fingerprinted_files:
            report.fingerprinted_files.append(value)
    elif value not in report.unfingerprinted_assets:
        report.unfingerprinted_assets.append(value)


def check_reference(
    report: Report,
    reference: str,
    *,
    source: Path,
    root: Path,
    public_prefix: str,
    relative_to_root: bool = False,
) -> Path | None:
    source_name = relative(source, root)
    report.references_checked += 1
    if is_external_or_inline(reference):
        if reference not in report.skipped_external:
            report.skipped_external.append(reference)
        return None
    target, error = resolve_reference(
        reference,
        source=source,
        root=root,
        public_prefix=public_prefix,
        relative_to_root=relative_to_root,
    )
    if error:
        add_finding(report, "error", "INVALID_REFERENCE", source_name, reference, error)
        return None
    assert target is not None
    if not target.is_file():
        add_finding(
            report,
            "error",
            "MISSING_BUILD_ASSET",
            source_name,
            reference,
            f"resolved path does not exist: {relative_or_display(target, root)}",
        )
        return None
    record_existing(report, target, root)
    return target


def relative_or_display(path: Path, root: Path) -> str:
    try:
        return relative(path, root)
    except ValueError:
        return str(path)


def discover_default_manifests(root: Path) -> list[Path]:
    candidates = [
        root / ".vite" / "manifest.json",
        root / "asset-manifest.json",
    ]
    return [path for path in candidates if path.is_file()]


def select_entries(root: Path, values: list[str]) -> list[Path]:
    if values:
        entries = [(root / value).resolve() for value in values]
    else:
        entries = sorted(path.resolve() for path in root.rglob("*.html") if path.is_file())
    for entry in entries:
        try:
            entry.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"entry escapes build directory: {entry}") from exc
        if not entry.is_file():
            raise ValueError(f"entry does not exist: {relative_or_display(entry, root)}")
    return entries


def select_manifests(root: Path, values: list[str]) -> list[Path]:
    manifests = [(root / value).resolve() for value in values] if values else discover_default_manifests(root)
    for manifest in manifests:
        try:
            manifest.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"manifest escapes build directory: {manifest}") from exc
        if not manifest.is_file():
            raise ValueError(f"manifest does not exist: {relative_or_display(manifest, root)}")
    return sorted(set(manifests))


def verify(root: Path, entries: list[Path], manifests: list[Path], public_prefix: str, scan_css: bool) -> Report:
    report = Report(
        root=str(root.resolve()),
        public_prefix=public_prefix,
        html_files=[relative(path, root) for path in entries],
        manifests=[relative(path, root) for path in manifests],
        references_checked=0,
    )
    css_queue: list[Path] = []
    css_seen: set[Path] = set()

    for entry in entries:
        record_existing(report, entry, root)
        try:
            references = read_html_references(entry)
        except OSError as exc:
            add_finding(report, "error", "READ_FAILED", relative(entry, root), "", str(exc))
            continue
        for reference in references:
            target = check_reference(
                report,
                reference,
                source=entry,
                root=root,
                public_prefix=public_prefix,
            )
            if scan_css and target and target.suffix.lower() == ".css":
                css_queue.append(target)

    for manifest in manifests:
        record_existing(report, manifest, root)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            add_finding(report, "error", "MANIFEST_PARSE_FAILED", relative(manifest, root), "", str(exc))
            continue
        for reference in collect_manifest_values(data):
            target = check_reference(
                report,
                reference,
                source=manifest,
                root=root,
                public_prefix=public_prefix,
                relative_to_root=True,
            )
            if scan_css and target and target.suffix.lower() == ".css":
                css_queue.append(target)

    while css_queue:
        stylesheet = css_queue.pop(0).resolve()
        if stylesheet in css_seen:
            continue
        css_seen.add(stylesheet)
        try:
            references = read_css_references(stylesheet)
        except OSError as exc:
            add_finding(report, "error", "READ_FAILED", relative(stylesheet, root), "", str(exc))
            continue
        for reference in references:
            target = check_reference(
                report,
                reference,
                source=stylesheet,
                root=root,
                public_prefix=public_prefix,
            )
            if target and target.suffix.lower() == ".css":
                css_queue.append(target)

    if not entries:
        add_finding(
            report,
            "warning",
            "NO_HTML_ENTRIES",
            "",
            "",
            "No HTML entry documents were found. Provide --entry for a nonstandard build.",
        )
    if not report.findings:
        add_finding(
            report,
            "info",
            "BUILD_REFERENCES_VALID",
            "",
            "",
            "Every checked local build reference exists.",
        )

    report.existing_files.sort()
    report.fingerprinted_files.sort()
    report.unfingerprinted_assets.sort()
    report.skipped_external.sort()
    return report


def print_human(report: Report) -> None:
    print(f"Build: {report.root}")
    print(f"Public prefix: {report.public_prefix}")
    print(f"HTML entries: {len(report.html_files)}")
    print(f"Manifests: {len(report.manifests)}")
    print(f"References checked: {report.references_checked}")
    print(f"Existing referenced files: {len(report.existing_files)}")
    print(f"Fingerprint-addressed files: {len(report.fingerprinted_files)}")
    print(f"Unfingerprinted asset files: {len(report.unfingerprinted_assets)}")
    for finding in report.findings:
        location = f" {finding.source}" if finding.source else ""
        reference = f" -> {finding.reference}" if finding.reference else ""
        print(f"[{finding.severity.upper()}] {finding.code}:{location}{reference}: {finding.message}")


def exit_code(report: Report, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = SEVERITY_ORDER[fail_on]
    highest = max((SEVERITY_ORDER[item.severity] for item in report.findings), default=0)
    return 1 if highest >= threshold else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.build_dir).expanduser().resolve()
    if not root.is_dir():
        print(f"error: build directory does not exist: {root}", file=sys.stderr)
        return 2
    try:
        public_prefix = normalize_public_prefix(args.public_prefix)
        entries = select_entries(root, args.entry)
        manifests = select_manifests(root, args.manifest)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = verify(root, entries, manifests, public_prefix, scan_css=not args.no_css)
    if args.json:
        json.dump(asdict(report), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_human(report)
    return exit_code(report, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
