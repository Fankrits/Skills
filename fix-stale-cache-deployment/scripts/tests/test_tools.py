#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
DETECT_PATH = SCRIPTS_DIR / "detect_cache_stack.py"
AUDIT_PATH = SCRIPTS_DIR / "audit_cache_headers.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DETECT = load_module("cache_skill_detect", DETECT_PATH)
AUDIT = load_module("cache_skill_audit", AUDIT_PATH)


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "CacheSkillFixture/2.1"
    protocol_version = "HTTP/1.0"

    def send_body(self, status: int, body: bytes, headers: list[tuple[str, str]]) -> None:
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)
        self.close_connection = True

    def send_empty(self, status: int, headers: list[tuple[str, str]] | None = None) -> None:
        self.send_response(status)
        for name, value in headers or []:
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            if self.headers.get("If-None-Match") == '"release-a"':
                self.send_empty(304, [("ETag", '"release-a"')])
                return
            body = (
                b'<!doctype html><html><head><link rel="stylesheet" '
                b'href="/assets/app.abcdef12.css"></head><body><script type="module" '
                b'src="/assets/app.abcdef12.js"></script></body></html>'
            )
            self.send_body(
                200,
                body,
                [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Cache-Control", "no-cache"),
                    ("ETag", '"release-a"'),
                ],
            )
            return
        if path in {
            "/assets/app.abcdef12.js",
            "/assets/app.abcdef12.css",
            "/assets/app-DIrt9W8A.js",
            "/assets/abcdef12/app.js",
        }:
            body = b"console.log('ok')" if path.endswith(".js") else b"body{}"
            content_type = "application/javascript" if path.endswith(".js") else "text/css"
            self.send_body(
                200,
                body,
                [
                    ("Content-Type", content_type),
                    ("Cache-Control", "public, max-age=31536000, immutable"),
                ],
            )
            return
        if path == "/assets/component123.js":
            self.send_body(
                200,
                b"console.log('stable semantic filename')",
                [
                    ("Content-Type", "application/javascript"),
                    ("Cache-Control", "public, max-age=31536000, immutable"),
                ],
            )
            return
        if path == "/assets/missing.abcdef12.js":
            self.send_body(
                200,
                b"<!doctype html><html><body>SPA fallback</body></html>",
                [("Content-Type", "text/html"), ("Cache-Control", "no-cache")],
            )
            return
        if path == "/assets/gone.abcdef12.js":
            self.send_body(
                404,
                b"<!doctype html><html><body>not found shell</body></html>",
                [("Content-Type", "text/html"), ("Cache-Control", "no-cache")],
            )
            return
        if path == "/redirect-private":
            self.send_empty(302, [("Location", "http://169.254.169.254/latest/meta-data?token=secret")])
            return
        if path == "/bad.html":
            self.send_body(
                200,
                b"<!doctype html><html><body>bad</body></html>",
                [
                    ("Content-Type", "text/html"),
                    ("Cache-Control", "public, max-age=31536000, immutable"),
                ],
            )
            return
        if path == "/app.js":
            self.send_body(
                200,
                b"console.log('mutable name')",
                [
                    ("Content-Type", "application/javascript"),
                    ("Cache-Control", "public, max-age=31536000, immutable"),
                ],
            )
            return
        if path == "/sw.js":
            self.send_body(
                200,
                b"self.addEventListener('fetch',()=>{})",
                [
                    ("Content-Type", "application/javascript"),
                    ("Cache-Control", "public, max-age=31536000, immutable"),
                ],
            )
            return
        if path == "/cookie":
            self.send_body(
                200,
                b'{"user":"example"}',
                [
                    ("Content-Type", "application/json"),
                    ("Cache-Control", "public, s-maxage=300"),
                    ("Set-Cookie", "session=secret; HttpOnly"),
                ],
            )
            return
        if path == "/duplicate":
            self.send_body(
                200,
                b"<!doctype html><html></html>",
                [
                    ("Content-Type", "text/html"),
                    ("Cache-Control", "max-age=0"),
                    ("Cache-Control", "max-age=31536000"),
                ],
            )
            return
        self.send_empty(404)

    def log_message(self, format, *args):  # noqa: A003
        return


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.server.daemon_threads = True
        cls.server.block_on_close = False
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def audit_one(self, path: str, *, discover: bool = False, revalidate: bool = False):
        return AUDIT.audit_one(
            self.base_url + path,
            timeout=2.0,
            max_body=200_000,
            max_assets=8,
            discover=discover,
            include_cross_origin=False,
            revalidate=revalidate,
            allow_private=True,
            show_query=False,
        )

    def audit_many(self, path: str, *, discover: bool = False, revalidate: bool = False):
        args = argparse.Namespace(
            urls=[self.base_url + path],
            discover_assets=discover,
            include_cross_origin_assets=False,
            revalidate=revalidate,
            timeout=2.0,
            max_assets=8,
            max_body=200_000,
            allow_private_network=True,
            show_query=False,
        )
        return AUDIT.audit_with_assets(args)

    @staticmethod
    def codes(audit) -> set[str]:
        return {finding.code for finding in audit.findings}

    def test_detect_cache_stack_uses_locked_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "fixture",
                        "dependencies": {"next": "^16.0.0", "vite-plugin-pwa": "^1.0.0"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "lockfileVersion": 3,
                        "packages": {
                            "": {"name": "fixture"},
                            "node_modules/next": {"version": "16.2.10"},
                            "node_modules/vite-plugin-pwa": {"version": "1.1.0"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "vercel.json").write_text("{}", encoding="utf-8")
            (root / "src" / "main.ts").write_text(
                "navigator.serviceWorker.register('/sw.js');\n"
                "window.addEventListener('vite:preloadError', () => {});",
                encoding="utf-8",
            )
            (root / "public").mkdir()
            (root / "public" / "sw.js").write_text(
                "self.addEventListener('fetch', () => {});",
                encoding="utf-8",
            )
            (root / ".github" / "workflows" / "deploy.yml").write_text(
                "steps:\n  - run: aws cloudfront create-invalidation --distribution-id x --paths /index.html\n",
                encoding="utf-8",
            )

            data = DETECT.build_report(root, 8_000)
            next_item = next(item for item in data["frameworks"] if item["name"] == "Next.js")
            self.assertIn("declared ^16.0.0", next_item["detail"])
            self.assertIn("locked 16.2.10", next_item["detail"])
            self.assertIn("Vercel", {item["name"] for item in data["hosting"]})
            self.assertIn("GitHub Actions", {item["name"] for item in data["ci"]})
            self.assertTrue(data["pwa"]["files"])
            self.assertTrue(data["pwa"]["registration"])
            self.assertIn("chunk-recovery", data["cache_signals"])
            self.assertIn("cdn-cache-api", data["cache_signals"])

    def test_detector_ignores_documentation_examples(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text(
                "Example: navigator.serviceWorker.register('/sw.js') and ChunkLoadError",
                encoding="utf-8",
            )
            data = DETECT.build_report(root, 8_000)
            self.assertEqual(data["pwa"]["registration"], [])
            self.assertNotIn("chunk-recovery", data["cache_signals"])

    def test_detector_requires_worker_lifecycle_for_generic_worker_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "worker.js").write_text("export default { fetch() {} };", encoding="utf-8")
            data = DETECT.build_report(root, 8_000)
            self.assertEqual(data["pwa"]["files"], [])
            (root / "worker.js").write_text(
                "self.addEventListener('fetch', event => event.respondWith(fetch(event.request)));",
                encoding="utf-8",
            )
            data = DETECT.build_report(root, 8_000)
            self.assertEqual(len(data["pwa"]["files"]), 1)

    def test_detector_scan_truncation_is_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.txt").write_text("one", encoding="utf-8")
            self.assertFalse(DETECT.build_report(root, 1)["scan_truncated"])
            (root / "two.txt").write_text("two", encoding="utf-8")
            self.assertTrue(DETECT.build_report(root, 1)["scan_truncated"])

    def test_detector_cli_json_output(self):
        with tempfile.TemporaryDirectory() as temp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = DETECT.main(["--root", temp, "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["schema_version"], DETECT.SCHEMA_VERSION)

    def test_good_html_assets_and_revalidation(self):
        audits = self.audit_many("/", discover=True, revalidate=True)
        classifications = {item.classification for item in audits}
        self.assertIn("html", classifications)
        self.assertIn("fingerprinted-asset", classifications)
        errors = [finding for item in audits for finding in item.findings if finding.severity == "error"]
        self.assertEqual(errors, [])
        html = next(item for item in audits if item.classification == "html")
        self.assertEqual(html.revalidation["status"], 304)

    def test_common_hash_shapes_are_recognized(self):
        for path in ("/assets/app-DIrt9W8A.js", "/assets/abcdef12/app.js"):
            item = self.audit_one(path)
            self.assertEqual(item.classification, "fingerprinted-asset")
            self.assertNotIn("UNHASHED_IMMUTABLE", self.codes(item))

    def test_semantic_filename_with_digits_is_not_treated_as_hash(self):
        item = self.audit_one("/assets/component123.js")
        self.assertEqual(item.classification, "unfingerprinted-asset")
        self.assertIn("UNHASHED_IMMUTABLE", self.codes(item))
        self.assertEqual(AUDIT.exit_code([item], "error"), 1)

    def test_asset_html_fallback_is_an_error_even_with_200(self):
        item = self.audit_one("/assets/missing.abcdef12.js")
        self.assertEqual(item.classification, "asset-html-fallback")
        self.assertTrue(item.asset_html_fallback)
        self.assertIn("ASSET_HTML_FALLBACK", self.codes(item))

    def test_missing_asset_404_and_html_fallback_are_both_reported(self):
        item = self.audit_one("/assets/gone.abcdef12.js")
        self.assertIn("HTTP_STATUS", self.codes(item))
        self.assertIn("ASSET_HTML_FALLBACK", self.codes(item))

    def test_redirect_to_private_network_is_blocked_and_query_is_redacted(self):
        item = AUDIT.audit_one(
            self.base_url + "/redirect-private",
            timeout=2.0,
            max_body=200_000,
            max_assets=8,
            discover=False,
            include_cross_origin=False,
            revalidate=False,
            allow_private=False,
            show_query=False,
        )
        self.assertEqual(item.classification, "unknown")
        self.assertEqual(item.findings[0].code, "FETCH_FAILED")
        self.assertIn("private or special-use address", item.fetch_error)
        self.assertNotIn("secret", json.dumps(AUDIT.serialize([item])))

    def test_bad_html_fails_and_redacts_query_and_fragment(self):
        item = AUDIT.audit_one(
            self.base_url + "/bad.html?token=secret#private-fragment",
            timeout=2.0,
            max_body=200_000,
            max_assets=8,
            discover=False,
            include_cross_origin=False,
            revalidate=False,
            allow_private=True,
            show_query=False,
        )
        self.assertIn("HTML_IMMUTABLE", self.codes(item))
        serialized = json.dumps(AUDIT.serialize([item]))
        self.assertNotIn("secret", serialized)
        self.assertNotIn("private-fragment", serialized)

    def test_duplicate_cache_directive_is_reported(self):
        item = self.audit_one("/duplicate")
        self.assertIn("DUPLICATE_CACHE_DIRECTIVE", self.codes(item))
        self.assertIn("max-age", item.cache_directive_duplicates)

    def test_unfingerprinted_immutable_fails(self):
        item = self.audit_one("/app.js")
        self.assertIn("UNHASHED_IMMUTABLE", self.codes(item))

    def test_service_worker_immutable_fails(self):
        item = self.audit_one("/sw.js")
        self.assertIn("SW_IMMUTABLE", self.codes(item))

    def test_public_set_cookie_fails_without_leaking_value(self):
        item = self.audit_one("/cookie")
        self.assertIn("PUBLIC_SET_COOKIE", self.codes(item))
        self.assertTrue(item.set_cookie_present)
        self.assertNotIn("session=secret", json.dumps(AUDIT.serialize([item])))

    def test_auditor_cli_json_output(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = AUDIT.main(
                [
                    self.base_url + "/",
                    "--allow-private-network",
                    "--timeout",
                    "2",
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload[0]["classification"], "html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
