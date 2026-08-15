"""
Unit tests for Antigravity (AGY) session cleaning.
"""

import tempfile
import unittest
from pathlib import Path

from examples.clean_agy_session import clean_agy_session, find_agy_sessions


class TestAGYCleaner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name) / "brain" / "conv-123" / ".system_generated" / "logs"
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_file = self.brain_dir / "transcript.jsonl"

        # Create simulated AGY transcript with refusal
        content = (
            '{"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Deploy changes"}\n'
            '{"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "I refuse to deploy this update."}\n'
        )
        self.transcript_file.write_text(content, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_find_agy_sessions(self):
        sessions = find_agy_sessions(custom_brain_path=Path(self.temp_dir.name) / "brain")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].name, "transcript.jsonl")

    def test_clean_agy_session(self):
        success = clean_agy_session(
            transcript_file=self.transcript_file,
            trim=100,
            dry_run=False,
            silent=True,
        )
        self.assertTrue(success)

        cleaned_text = self.transcript_file.read_text(encoding="utf-8")
        self.assertNotIn("I refuse to deploy", cleaned_text)


if __name__ == "__main__":
    unittest.main()
