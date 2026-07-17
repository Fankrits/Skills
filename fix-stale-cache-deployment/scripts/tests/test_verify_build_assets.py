#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
VERIFY = SCRIPTS_DIR / "verify_build_assets.py"


class BuildVerifierTests(unittest.TestCase):
    def run_command(
        self,
        command: list[str],
        expected_code: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, expected_code, msg=result.stderr + result.stdout)
        return result

    def run_json(self, command: list[str], expected_code: int = 0):
        result = self.run_command(command, expected_code)
        return json.loads(result.stdout)

    def test_verify_build_assets_with_css_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assets").mkdir()
            (root / ".vite").mkdir()
            (root / "index.html").write_text(
                '<link rel="stylesheet" href="/app/assets/app.abcdef12.css">'
                '<script type="module" src="/app/assets/app-DIrt9W8A.js"></script>',
                encoding="utf-8",
            )
            (root / "assets" / "app.abcdef12.css").write_text(
                "@font-face{src:url('./font.abcdef12.woff2')}",
                encoding="utf-8",
            )
            (root / "assets" / "app-DIrt9W8A.js").write_text(
                "export {};",
                encoding="utf-8",
            )
            (root / "assets" / "font.abcdef12.woff2").write_bytes(b"font")
            (root / ".vite" / "manifest.json").write_text(
                json.dumps(
                    {
                        "src/main.ts": {
                            "file": "assets/app-DIrt9W8A.js",
                            "css": ["assets/app.abcdef12.css"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            data = self.run_json(
                [
                    sys.executable,
                    str(VERIFY),
                    str(root),
                    "--public-prefix",
                    "/app/",
                    "--json",
                ]
            )
            self.assertGreaterEqual(data["references_checked"], 5)
            self.assertEqual(
                [item for item in data["findings"] if item["severity"] == "error"],
                [],
            )
            self.assertIn("assets/app-DIrt9W8A.js", data["fingerprinted_files"])

    def test_verify_build_assets_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "index.html").write_text(
                '<script src="/assets/missing.abcdef12.js"></script>',
                encoding="utf-8",
            )
            data = self.run_json(
                [sys.executable, str(VERIFY), str(root), "--json"],
                expected_code=1,
            )
            self.assertIn(
                "MISSING_BUILD_ASSET",
                {item["code"] for item in data["findings"]},
            )

    def test_verify_build_assets_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nested").mkdir()
            (root / "nested" / "index.html").write_text(
                '<script src="../../../outside.js"></script>',
                encoding="utf-8",
            )
            data = self.run_json(
                [sys.executable, str(VERIFY), str(root), "--json"],
                expected_code=1,
            )
            self.assertIn(
                "INVALID_REFERENCE",
                {item["code"] for item in data["findings"]},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
