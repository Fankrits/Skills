#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"


class SkillStructureTests(unittest.TestCase):
    def test_required_files_exist(self):
        self.assertTrue(SKILL_MD.is_file())
        self.assertTrue((SKILL_DIR / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_DIR / "scripts" / "audit_cache_headers.py").is_file())
        self.assertTrue((SKILL_DIR / "scripts" / "detect_cache_stack.py").is_file())
        self.assertTrue((SKILL_DIR / "scripts" / "verify_build_assets.py").is_file())

    def test_frontmatter_has_only_name_and_description(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must begin with YAML frontmatter")
        keys = []
        for line in match.group(1).splitlines():
            if line and not line.startswith((" ", "\t", "-")) and ":" in line:
                keys.append(line.split(":", 1)[0].strip())
        self.assertEqual(keys, ["name", "description"])
        self.assertIn("name: fix-stale-cache-deployment", match.group(1))

    def test_all_local_markdown_references_exist(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        paths = sorted(set(re.findall(r"`((?:references|scripts)/[^`]+)`", text)))
        self.assertGreater(len(paths), 5)
        missing = [path for path in paths if not (SKILL_DIR / path).exists()]
        self.assertEqual(missing, [])

    def test_no_placeholders(self):
        forbidden = ("TO" + "DO", "T" + "BD", "PLACE" + "HOLDER")
        for path in SKILL_DIR.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".md", ".py", ".yaml", ".yml"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                for token in forbidden:
                    self.assertNotIn(token, text, f"{token} found in {path}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
