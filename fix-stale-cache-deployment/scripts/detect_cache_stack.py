#!/usr/bin/env python3
"""Detect deployment-cache evidence without executing project code.

The detector uses only the Python standard library. Every detection includes the
file that caused it, and ambiguous files remain explicitly ambiguous rather than
being assigned to a hosting vendor by guesswork.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

TOOL_VERSION = "2.0.0"
SCHEMA_VERSION = 1

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".output",
    ".svelte-kit",
    ".turbo",
    ".vercel",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "target",
    "out",
    "tmp",
    "temp",
    "__pycache__",
}

TEXT_SUFFIXES = {
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".json",
    ".jsonc",
    ".toml",
    ".yaml",
    ".yml",
    ".conf",
    ".config",
    ".html",
    ".htm",
    ".md",
    ".txt",
    ".sh",
    ".ps1",
    ".xml",
    ".properties",
}
SIGNAL_TEXT_SUFFIXES = TEXT_SUFFIXES - {".md", ".txt"}

SPECIAL_TEXT_NAMES = {
    "Dockerfile",
    "Caddyfile",
    "Procfile",
    ".htaccess",
    ".headers",
    "_headers",
    "_redirects",
    ".env.example",
}

MAX_FILE_BYTES = 1_000_000
MAX_SCANNED_FILES = 8_000
MAX_MATCHES_PER_SIGNAL = 20


@dataclass(frozen=True)
class Evidence:
    name: str
    path: str
    detail: str = ""


FRAMEWORK_PACKAGES: dict[str, tuple[str, ...]] = {
    "Next.js": ("next",),
    "Vite": ("vite",),
    "Create React App": ("react-scripts",),
    "Webpack": ("webpack",),
    "SvelteKit": ("@sveltejs/kit",),
    "Nuxt": ("nuxt",),
    "Astro": ("astro",),
    "Remix": ("@remix-run/dev", "@remix-run/react"),
    "React Router": ("react-router", "react-router-dom"),
    "Qwik City": ("@builder.io/qwik-city",),
    "TanStack Start": ("@tanstack/start", "@tanstack/react-start", "@tanstack/solid-start"),
    "SolidStart": ("@solidjs/start", "solid-start"),
}

PWA_PACKAGES = (
    "vite-plugin-pwa",
    "workbox-build",
    "workbox-window",
    "workbox-webpack-plugin",
    "next-pwa",
    "@serwist/next",
    "serwist",
)

LOCKFILE_FILES: dict[str, tuple[str, ...]] = {
    "npm": ("package-lock.json", "npm-shrinkwrap.json"),
    "pnpm": ("pnpm-lock.yaml",),
    "Yarn": ("yarn.lock",),
    "Bun": ("bun.lock", "bun.lockb"),
}

HOST_FILES: dict[str, tuple[str, ...]] = {
    "Vercel": ("vercel.json",),
    "Netlify": ("netlify.toml",),
    "Static host (_headers; verify Netlify or Cloudflare Pages)": ("_headers",),
    "Cloudflare": ("wrangler.toml", "wrangler.json", "wrangler.jsonc", "_routes.json"),
    "Firebase Hosting": ("firebase.json", ".firebaserc"),
    "Azure Static Web Apps": ("staticwebapp.config.json",),
    "Nginx": ("nginx.conf",),
    "Apache": (".htaccess", "httpd.conf", "apache2.conf"),
    "Caddy": ("Caddyfile",),
    "Fly.io": ("fly.toml",),
    "Railway": ("railway.json", "railway.toml"),
    "Render": ("render.yaml", "render.yml"),
    "AWS Amplify": ("amplify.yml",),
    "Docker": ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"),
}

CI_FILES: dict[str, tuple[str, ...]] = {
    "GitHub Actions": (".github/workflows/*.yml", ".github/workflows/*.yaml"),
    "GitLab CI": (".gitlab-ci.yml",),
    "Bitbucket Pipelines": ("bitbucket-pipelines.yml",),
    "Azure Pipelines": ("azure-pipelines.yml", "azure-pipelines.yaml"),
    "CircleCI": (".circleci/config.yml",),
}

SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "service-worker-registration": re.compile(
        r"navigator\.serviceWorker|serviceWorker\.register|registerSW\s*\(|VitePWA\s*\(", re.I
    ),
    "cache-control-config": re.compile(r"Cache-Control|CDN-Cache-Control|Surrogate-Control", re.I),
    "next-revalidation": re.compile(
        r"revalidatePath\s*\(|revalidateTag\s*\(|updateTag\s*\(|export\s+const\s+revalidate\b|cacheLife\s*\(|cacheTag\s*\(",
        re.I,
    ),
    "next-cache-handler": re.compile(r"cacheHandler\b|cacheMaxMemorySize\b", re.I),
    "dynamic-rendering": re.compile(r"force-dynamic|no-store|unstable_noStore|connection\s*\(", re.I),
    "cdn-cache-api": re.compile(r"caches\.default|cacheTtl|cf\.cache|purge_cache|create-invalidation", re.I),
    "chunk-recovery": re.compile(
        r"vite:preloadError|ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module", re.I
    ),
    "cache-versioning": re.compile(r"CACHE_NAME|precacheAndRoute|cleanupOutdatedCaches|skipWaiting", re.I),
}

SERVICE_WORKER_EXACT_NAMES = {
    "sw.js",
    "sw.mjs",
    "sw.ts",
    "service-worker.js",
    "service-worker.mjs",
    "service-worker.ts",
    "serviceworker.js",
    "serviceworker.mjs",
    "serviceworker.ts",
}
WORKBOX_CONFIG_NAMES = {
    "workbox-config.js",
    "workbox-config.cjs",
    "workbox-config.mjs",
    "workbox-config.ts",
}
WORKER_LIFECYCLE_PATTERN = re.compile(
    r"self\.addEventListener\s*\(\s*['\"](?:install|activate|fetch|message)['\"]|"
    r"precacheAndRoute\s*\(|skipWaiting\s*\(|clients\.claim\s*\(",
    re.I,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect framework, host, PWA, cache, and CI evidence without executing project code."
    )
    parser.add_argument("--root", default=".", help="Project root to scan. Default: current directory")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--max-files",
        type=int,
        default=MAX_SCANNED_FILES,
        help=f"Maximum text files to inspect. Default: {MAX_SCANNED_FILES}",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    return parser.parse_args(argv)


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_scannable_text(path: Path) -> bool:
    return path.name in SPECIAL_TEXT_NAMES or path.suffix.lower() in TEXT_SUFFIXES


def is_signal_text(path: Path) -> bool:
    return path.name in SPECIAL_TEXT_NAMES or path.suffix.lower() in SIGNAL_TEXT_SUFFIXES


def iter_files(root: Path, limit: int) -> Iterator[Path]:
    """Yield at most limit+1 relevant text files so truncation is detectable."""

    yielded = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            directory
            for directory in dirnames
            if directory not in IGNORED_DIRS and not (Path(current) / directory).is_symlink()
        )
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.is_symlink() or not is_scannable_text(path):
                continue
            yield path
            yielded += 1
            if yielded > limit:
                return


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8", errors="replace")
    except UnicodeError:
        return None


def load_package_manifests(root: Path, files: Iterable[Path]) -> tuple[list[dict], list[str]]:
    manifests: list[dict] = []
    warnings: list[str] = []
    for path in files:
        if path.name != "package.json":
            continue
        text = read_text(path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            warnings.append(f"Could not parse {rel(path, root)}: {exc}")
            continue
        dependencies: dict[str, str] = {}
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            values = data.get(field, {})
            if isinstance(values, dict):
                dependencies.update({str(key): str(value) for key, value in values.items()})
        manifests.append(
            {
                "path": rel(path, root),
                "name": data.get("name"),
                "private": data.get("private"),
                "dependencies": dependencies,
            }
        )
    return manifests, warnings


def load_npm_lock_versions(
    root: Path,
    files: Iterable[Path],
) -> tuple[dict[str, list[Evidence]], list[str]]:
    versions: dict[str, list[Evidence]] = {}
    warnings: list[str] = []
    for path in files:
        if path.name not in {"package-lock.json", "npm-shrinkwrap.json"}:
            continue
        text = read_text(path)
        if text is None:
            warnings.append(f"Skipped large or unreadable lockfile: {rel(path, root)}")
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            warnings.append(f"Could not parse {rel(path, root)}: {exc}")
            continue

        packages = data.get("packages")
        if isinstance(packages, dict):
            for key, metadata in packages.items():
                if not isinstance(key, str) or "node_modules/" not in key or not isinstance(metadata, dict):
                    continue
                package = key.rsplit("node_modules/", 1)[-1]
                version = metadata.get("version")
                if isinstance(version, str):
                    versions.setdefault(package, []).append(Evidence(package, rel(path, root), version))
        else:
            def walk_dependencies(node: object) -> None:
                if not isinstance(node, dict):
                    return
                for package, metadata in node.items():
                    if not isinstance(metadata, dict):
                        continue
                    version = metadata.get("version")
                    if isinstance(version, str):
                        versions.setdefault(str(package), []).append(
                            Evidence(str(package), rel(path, root), version)
                        )
                    walk_dependencies(metadata.get("dependencies"))

            walk_dependencies(data.get("dependencies"))

    for package, entries in list(versions.items()):
        unique = {(item.path, item.detail): item for item in entries}
        versions[package] = sorted(unique.values(), key=lambda item: (item.path, item.detail))
    return versions, warnings


def nearest_locked_version(
    manifest_path: str,
    package: str,
    versions: dict[str, list[Evidence]],
) -> Evidence | None:
    candidates = versions.get(package, [])
    if not candidates:
        return None
    manifest_dir = Path(manifest_path).parent

    def score(item: Evidence) -> tuple[int, int, str]:
        lock_dir = Path(item.path).parent
        try:
            relative = manifest_dir.relative_to(lock_dir)
            return (0, len(relative.parts), item.path)
        except ValueError:
            return (1, len(lock_dir.parts), item.path)

    return min(candidates, key=score)


def detect_frameworks(
    manifests: list[dict],
    locked_versions: dict[str, list[Evidence]],
) -> list[Evidence]:
    found: dict[tuple[str, str], Evidence] = {}
    for manifest in manifests:
        dependencies: dict[str, str] = manifest["dependencies"]
        for framework, packages in FRAMEWORK_PACKAGES.items():
            for package in packages:
                if package in dependencies:
                    detail = f"{package} declared {dependencies[package]}"
                    locked = nearest_locked_version(manifest["path"], package, locked_versions)
                    if locked:
                        detail += f"; locked {locked.detail} in {locked.path}"
                    found[(framework, manifest["path"])] = Evidence(
                        framework,
                        manifest["path"],
                        detail,
                    )
                    break
    return sorted(found.values(), key=lambda item: (item.name.lower(), item.path))


def detect_pwa_packages(
    manifests: list[dict],
    locked_versions: dict[str, list[Evidence]],
) -> list[Evidence]:
    results: list[Evidence] = []
    for manifest in manifests:
        dependencies: dict[str, str] = manifest["dependencies"]
        for package in PWA_PACKAGES:
            if package in dependencies:
                detail = f"declared {dependencies[package]}"
                locked = nearest_locked_version(manifest["path"], package, locked_versions)
                if locked:
                    detail += f"; locked {locked.detail} in {locked.path}"
                results.append(Evidence(package, manifest["path"], detail))
    return sorted(results, key=lambda item: (item.name.lower(), item.path))


def match_named_files(root: Path, files: Iterable[Path], mapping: dict[str, tuple[str, ...]]) -> list[Evidence]:
    file_list = list(files)
    results: list[Evidence] = []
    for label, patterns in mapping.items():
        seen: set[str] = set()
        for path in file_list:
            relative = rel(path, root)
            for pattern in patterns:
                if fnmatch.fnmatch(relative, pattern) or ("/" not in pattern and path.name == pattern):
                    if relative not in seen:
                        seen.add(relative)
                        results.append(Evidence(label, relative, pattern))
                    break
    return sorted(results, key=lambda item: (item.name.lower(), item.path))


def detect_service_worker_files(
    root: Path,
    files: Iterable[Path],
) -> tuple[list[Evidence], list[Evidence]]:
    workers: list[Evidence] = []
    configs: list[Evidence] = []
    for path in files:
        name = path.name.lower()
        relative = rel(path, root)
        if name in WORKBOX_CONFIG_NAMES:
            configs.append(Evidence("workbox-config", relative, name))
            continue
        obvious = (
            name in SERVICE_WORKER_EXACT_NAMES
            or "service-worker" in name
            or "serviceworker" in name
        )
        if obvious:
            workers.append(Evidence("service-worker-file", relative, name))
            continue
        if name in {"worker.js", "worker.mjs", "worker.ts"}:
            text = read_text(path)
            if text and WORKER_LIFECYCLE_PATTERN.search(text):
                workers.append(Evidence("service-worker-file", relative, "generic worker filename with service-worker lifecycle code"))
    return (
        sorted(workers, key=lambda item: item.path),
        sorted(configs, key=lambda item: item.path),
    )


def scan_signals(root: Path, files: Iterable[Path]) -> dict[str, list[Evidence]]:
    matches: dict[str, list[Evidence]] = {name: [] for name in SIGNAL_PATTERNS}
    for path in files:
        if not is_signal_text(path):
            continue
        text = read_text(path)
        if text is None:
            continue
        relative = rel(path, root)
        for name, pattern in SIGNAL_PATTERNS.items():
            bucket = matches[name]
            if len(bucket) >= MAX_MATCHES_PER_SIGNAL:
                continue
            match = pattern.search(text)
            if match:
                line_number = text.count("\n", 0, match.start()) + 1
                excerpt = " ".join(match.group(0).split())[:120]
                bucket.append(Evidence(name, relative, f"line {line_number}: {excerpt}"))
    return {name: values for name, values in matches.items() if values}


def summarize_warnings(
    frameworks: list[Evidence],
    hosts: list[Evidence],
    pwa_files: list[Evidence],
    pwa_configs: list[Evidence],
    pwa_packages: list[Evidence],
    signals: dict[str, list[Evidence]],
    lockfiles: list[Evidence],
) -> list[str]:
    warnings: list[str] = []
    framework_names = {item.name for item in frameworks}
    host_names = {item.name for item in hosts}
    if not frameworks:
        warnings.append(
            "No supported framework package was detected; the project may be static, non-JavaScript, or a monorepo with generated manifests omitted."
        )
    if len(framework_names) > 2:
        warnings.append("Multiple framework families were detected. Treat this as a monorepo and diagnose the deployed application only.")
    if frameworks and not lockfiles:
        warnings.append(
            "Framework versions come from package.json ranges only. Inspect a lockfile or runtime build metadata before applying version-sensitive guidance."
        )
    if frameworks and lockfiles and any("; locked " not in item.detail for item in frameworks):
        warnings.append(
            "At least one framework could not be resolved to an exact npm lockfile version. Verify its installed version manually."
        )
    if not hosts:
        warnings.append("No deployment-host configuration was detected. Determine the actual host and any external CDN before writing platform-specific config.")
    if len(host_names) > 2:
        warnings.append("Multiple host or server configurations were detected. Confirm which path serves production traffic.")
    if any(item.name.startswith("Static host (_headers") for item in hosts):
        warnings.append("An _headers file is present, but that syntax is shared by multiple static hosts. Confirm the active platform before assuming rule precedence.")
    pwa_evidence = pwa_files or pwa_configs or pwa_packages or signals.get("service-worker-registration")
    if pwa_evidence and not pwa_files:
        warnings.append("PWA or service-worker configuration evidence exists, but no obvious worker file was found. It may be generated during build.")
    if pwa_files and not (pwa_packages or signals.get("service-worker-registration")):
        warnings.append("A possible service-worker file exists, but no registration code or PWA package was detected. Confirm whether it is deployed and controlling clients.")
    if signals.get("chunk-recovery"):
        warnings.append("Existing chunk-recovery code was detected. Verify it has a one-shot guard and cannot create a reload loop.")
    return warnings


def build_report(root: Path, max_files: int) -> dict:
    collected = list(iter_files(root, max_files))
    scan_truncated = len(collected) > max_files
    files = collected[:max_files]
    manifests, parse_warnings = load_package_manifests(root, files)
    lockfiles = match_named_files(root, files, LOCKFILE_FILES)
    locked_versions, lock_warnings = load_npm_lock_versions(root, files)
    frameworks = detect_frameworks(manifests, locked_versions)
    pwa_packages = detect_pwa_packages(manifests, locked_versions)
    hosts = match_named_files(root, files, HOST_FILES)
    ci = match_named_files(root, files, CI_FILES)
    pwa_files, pwa_configs = detect_service_worker_files(root, files)
    signals = scan_signals(root, files)
    warnings = parse_warnings + lock_warnings + summarize_warnings(
        frameworks,
        hosts,
        pwa_files,
        pwa_configs,
        pwa_packages,
        signals,
        lockfiles,
    )
    if scan_truncated:
        warnings.append(f"Scan stopped after {max_files} text files. Narrow --root or increase --max-files before treating absence as evidence.")

    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "root": str(root.resolve()),
        "files_considered": len(files),
        "scan_truncated": scan_truncated,
        "lockfiles": [asdict(item) for item in lockfiles],
        "package_manifests": [
            {"path": item["path"], "name": item["name"], "private": item["private"]}
            for item in manifests
        ],
        "frameworks": [asdict(item) for item in frameworks],
        "hosting": [asdict(item) for item in hosts],
        "ci": [asdict(item) for item in ci],
        "pwa": {
            "packages": [asdict(item) for item in pwa_packages],
            "files": [asdict(item) for item in pwa_files],
            "config_files": [asdict(item) for item in pwa_configs],
            "registration": [asdict(item) for item in signals.get("service-worker-registration", [])],
        },
        "cache_signals": {
            name: [asdict(item) for item in values]
            for name, values in sorted(signals.items())
            if name != "service-worker-registration"
        },
        "warnings": warnings,
    }


def print_human(report: dict) -> None:
    print(f"Project: {report['root']}")
    print(f"Detector: {report['tool_version']} (schema {report['schema_version']})")
    print(f"Files considered: {report['files_considered']}" + (" (truncated)" if report["scan_truncated"] else ""))

    def section(title: str, entries: list[dict]) -> None:
        print(f"\n{title}:")
        if not entries:
            print("  - none detected")
            return
        for item in entries:
            detail = f" - {item['detail']}" if item.get("detail") else ""
            print(f"  - {item['name']}: {item['path']}{detail}")

    section("Package-manager lockfiles", report["lockfiles"])
    section("Frameworks", report["frameworks"])
    section("Hosting and servers", report["hosting"])
    section("CI/CD", report["ci"])
    section("PWA packages", report["pwa"]["packages"])
    section("PWA configuration", report["pwa"]["config_files"])
    section("Service-worker files", report["pwa"]["files"])
    section("Service-worker registration", report["pwa"]["registration"])

    print("\nCache signals:")
    if not report["cache_signals"]:
        print("  - none detected")
    else:
        for name, entries in report["cache_signals"].items():
            print(f"  {name}:")
            for item in entries:
                print(f"    - {item['path']} - {item['detail']}")

    print("\nWarnings:")
    if not report["warnings"]:
        print("  - none")
    else:
        for warning in report["warnings"]:
            print(f"  - {warning}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: project root is not a directory: {root}", file=sys.stderr)
        return 2
    if args.max_files < 1:
        print("error: --max-files must be at least 1", file=sys.stderr)
        return 2

    report = build_report(root, args.max_files)
    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
