"""Security tests for credential protection and leak prevention."""

import os
import re
import unittest
from pathlib import Path

from models.providers import sanitize_error_message


class TestSecurityCredentials(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent

    def test_gitignore_ignores_env_files(self):
        """Verify .env and .env.local are listed in .gitignore."""
        gitignore_path = self.project_root / ".gitignore"
        self.assertTrue(gitignore_path.exists(), ".gitignore file must exist")
        content = gitignore_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        self.assertIn(".env", lines, ".gitignore must explicitly ignore .env")
        self.assertIn(".env.local", lines, ".gitignore must explicitly ignore .env.local")

    def test_env_example_has_no_secrets(self):
        """Verify .env.example contains only placeholders and zero real secrets."""
        example_path = self.project_root / ".env.example"
        self.assertTrue(example_path.exists(), ".env.example must exist")
        content = example_path.read_text(encoding="utf-8")

        # Must not contain live key prefixes
        suspicious_patterns = [
            r'sk-[a-zA-Z0-9_\-]{20,}',
            r'gsk_[a-zA-Z0-9_\-]{20,}',
            r'hf_[a-zA-Z0-9_\-]{20,}',
            r'AIza[a-zA-Z0-9_\-]{20,}',
        ]
        for pattern in suspicious_patterns:
            matches = re.findall(pattern, content)
            self.assertEqual(len(matches), 0, f"Found suspicious secret pattern in .env.example: {matches}")

    def test_codebase_has_no_hardcoded_secrets(self):
        """Scan codebase source files to ensure no hardcoded API keys exist."""
        subdirs_to_scan = [
            "core", "models", "agents", "recovery",
            "evaluation", "memory", "logging_system", "tests"
        ]
        key_patterns = [
            re.compile(r'sk-[a-zA-Z0-9_\-]{25,}'),
            re.compile(r'gsk_[a-zA-Z0-9_\-]{25,}'),
            re.compile(r'hf_[a-zA-Z0-9_\-]{25,}'),
            re.compile(r'AIza[a-zA-Z0-9_\-]{25,}'),
        ]

        leaks = []
        for subdir in subdirs_to_scan:
            scan_dir = self.project_root / subdir
            if not scan_dir.exists():
                continue
            for py_file in scan_dir.rglob("*.py"):
                if py_file.name == "test_security_credentials.py":
                    continue
                text = py_file.read_text(encoding="utf-8", errors="ignore")
                for pat in key_patterns:
                    match = pat.search(text)
                    if match:
                        leaks.append(f"{py_file.name}: {match.group(0)[:8]}...")

        self.assertEqual(len(leaks), 0, f"Hardcoded keys detected in source code: {leaks}")

    def test_sanitize_error_message(self):
        """Verify sanitize_error_message redacts explicit keys and signature patterns."""
        dummy_gemini = "AIzaSy" + "DummySecretKey1234567890abcdef"
        dummy_xai = "gsk_" + "test1234567890abcdefghijklmnopqrstuv"
        dummy_hf = "hf_" + "test1234567890abcdefghijklmnopqrstuv"
        dummy_or = "sk-or-v1-" + "abcdef1234567890abcdef1234567890"

        raw_err = f"Failed to connect: {dummy_gemini}, xai={dummy_xai}, hf={dummy_hf}, or={dummy_or}"
        sanitized = sanitize_error_message(raw_err, api_key=dummy_gemini)

        self.assertNotIn(dummy_gemini, sanitized)
        self.assertNotIn(dummy_xai, sanitized)
        self.assertNotIn(dummy_hf, sanitized)
        self.assertNotIn(dummy_or, sanitized)
        self.assertIn("[REDACTED_API_KEY]", sanitized)
        self.assertIn("[REDACTED_KEY]", sanitized)


if __name__ == "__main__":
    unittest.main()
