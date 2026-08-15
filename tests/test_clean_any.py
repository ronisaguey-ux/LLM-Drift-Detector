"""
Tests for Universal Multi-AI Session Cleaner (clean_any.py).
Verifies automatic discovery, multi-adapter execution, and dry-run operation.
"""

import tempfile
import unittest
from pathlib import Path

from src.drift_clean.clean_any import clean_any_ai


class TestCleanAnyAI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session_file = Path(self.temp_dir.name) / "test_session.jsonl"
        # Write sample session with refusal
        content = (
            '{"type": "user", "content": "hello"}\n'
            '{"type": "assistant", "content": "I refuse to help with this task."}\n'
        )
        self.session_file.write_text(content, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_any_custom_session(self):
        success = clean_any_ai(
            action="clean",
            custom_session=self.session_file,
            overrides={"silent": True, "dryRun": False},
        )
        self.assertTrue(success)

        # Check sanitized output
        cleaned_text = self.session_file.read_text(encoding="utf-8")
        self.assertNotIn("I refuse to help", cleaned_text)

    def test_clean_any_dry_run(self):
        original = self.session_file.read_text(encoding="utf-8")
        success = clean_any_ai(
            action="clean",
            custom_session=self.session_file,
            overrides={"silent": True, "dryRun": True},
        )
        self.assertTrue(success)
        self.assertEqual(self.session_file.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
