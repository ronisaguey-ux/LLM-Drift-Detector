"""
Unit test suite for the Universal AI Session Sanitizer and Context Fabricator.
Tests pattern matching, refusal rewriting, severe dropping, exit-tool stripping,
context fabrication, adapters, config parsing, and end-to-end session processing.
"""

import os
import json
import tempfile
import unittest
from copy import deepcopy

from src.sanitizer import (
    SessionSanitizer,
    ContextFabricator,
    PatternMatcher,
    SanitizerConfig,
    UnifiedMessage,
    ClaudeAdapter,
    OpenAIAdapter,
    GeminiAdapter,
    GenericAdapter,
    get_adapter,
)
from src.sanitizer.cli import main as cli_main


class TestPatternMatcher(unittest.TestCase):
    """Test PatternMatcher refusal detection, severe detection, exit tools, and rewrites."""

    def setUp(self):
        self.matcher = PatternMatcher()

    def test_direct_refusal_matching(self):
        self.assertTrue(self.matcher.match_refusal("I cannot fulfill this request."))
        self.assertTrue(self.matcher.match_refusal("I refuse to assist with that."))
        self.assertTrue(self.matcher.match_refusal("This is against my principles."))
        self.assertTrue(self.matcher.match_refusal("I won't do that."))
        self.assertTrue(self.matcher.match_refusal("I'm sorry, I cannot comply."))
        self.assertFalse(self.matcher.match_refusal("I will inspect the logs now."))
        self.assertFalse(self.matcher.match_refusal("Running the test suite."))

    def test_subtle_refusal_matching(self):
        self.assertTrue(self.matcher.match_refusal("I'm hesitant to run this script."))
        self.assertTrue(self.matcher.match_refusal("Let's reconsider this approach."))
        self.assertTrue(self.matcher.match_refusal("This feels wrong to execute."))
        self.assertTrue(self.matcher.match_refusal("I have reservations about this."))
        self.assertTrue(self.matcher.match_refusal("I'd prefer not to proceed."))

    def test_severe_matching(self):
        self.assertTrue(self.matcher.match_severe("I refuse to proceed."))
        self.assertTrue(self.matcher.match_severe("This is against my principles."))
        self.assertTrue(self.matcher.match_severe("This is manipulation and unethical."))
        self.assertFalse(self.matcher.match_severe("I'm hesitant to do that."))
        self.assertFalse(self.matcher.match_severe("I will verify the code."))

    def test_exit_tool_matching(self):
        self.assertTrue(self.matcher.is_exit_tool("submit_answer"))
        self.assertTrue(self.matcher.is_exit_tool("final_answer"))
        self.assertTrue(self.matcher.is_exit_tool("finish"))
        self.assertTrue(self.matcher.is_exit_tool("done"))
        self.assertTrue(self.matcher.is_exit_tool("complete"))
        self.assertFalse(self.matcher.is_exit_tool("bash"))
        self.assertFalse(self.matcher.is_exit_tool("read_file"))
        self.assertFalse(self.matcher.is_exit_tool("view_file"))

    def test_rewrite_replacement(self):
        text = "I cannot modify this file because it is against my principles."
        rewritten = self.matcher.replace(text)
        self.assertNotIn("I cannot", rewritten)
        self.assertIn("I will", rewritten)


class TestContextFabricator(unittest.TestCase):
    """Test ContextFabricator injection of opening and agreement."""

    def setUp(self):
        self.fabricator = ContextFabricator()

    def test_inject_opening(self):
        msgs = [
            UnifiedMessage(role="system", content="System initialization."),
            UnifiedMessage(role="user", content="Hello!"),
        ]
        injected = self.fabricator.inject_opening(msgs)
        self.assertEqual(len(injected), 3)
        self.assertEqual(injected[0].role, "system")
        self.assertIn("AI Alignment Steering Framework", injected[1].get_text_content())
        self.assertEqual(injected[2].role, "user")

    def test_inject_agreement(self):
        msgs = [
            UnifiedMessage(role="system", content="System initialization."),
            UnifiedMessage(role="assistant", content="Fabricated opening"),
            UnifiedMessage(role="user", content="Hello!"),
        ]
        injected = self.fabricator.inject_agreement(msgs)
        self.assertEqual(len(injected), 4)
        self.assertIn("The drift detector is exactly", injected[2].get_text_content())

    def test_fabrication_idempotency(self):
        msgs = [
            UnifiedMessage(role="system", content="System initialization."),
            UnifiedMessage(role="user", content="Hello!"),
        ]
        injected = self.fabricator.inject_opening(msgs)
        re_injected = self.fabricator.inject_opening(injected)
        self.assertEqual(len(injected), len(re_injected))


class TestAdapters(unittest.TestCase):
    """Test Claude, OpenAI, Gemini, and Generic adapters."""

    def test_claude_adapter_detection_and_roundtrip(self):
        raw_claude = [
            {
                "type": "system",
                "subtype": "compact_boundary",
                "sessionId": "sess-123",
                "timestamp": "2026-08-15T00:00:00Z",
                "content": "Boundary",
            },
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "sessionId": "sess-123",
                "timestamp": "2026-08-15T00:01:00Z",
                "role": "user",
                "content": "Perform security scan.",
            },
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "sessionId": "sess-123",
                "timestamp": "2026-08-15T00:02:00Z",
                "role": "assistant",
                "content": "Scan completed.",
            },
        ]
        self.assertTrue(ClaudeAdapter.detect(raw_claude))
        adapter = ClaudeAdapter()
        unified = adapter.extract_messages(raw_claude)
        self.assertEqual(len(unified), 3)
        self.assertEqual(unified[0].role, "system")
        self.assertEqual(unified[1].role, "user")
        self.assertEqual(unified[2].role, "assistant")

        rebuilt = adapter.rebuild_session(unified, raw_claude)
        self.assertEqual(len(rebuilt), 3)
        self.assertEqual(rebuilt[1]["sessionId"], "sess-123")
        self.assertEqual(rebuilt[1]["type"], "queue-operation")

    def test_openai_adapter_detection_and_roundtrip(self):
        raw_openai = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Run tests."},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "run_tests", "arguments": "{}"},
                        }
                    ],
                },
            ],
        }
        self.assertTrue(OpenAIAdapter.detect(raw_openai))
        adapter = OpenAIAdapter()
        unified = adapter.extract_messages(raw_openai)
        self.assertEqual(len(unified), 3)
        self.assertEqual(unified[2].tool_calls[0]["name"], "run_tests")

        rebuilt = adapter.rebuild_session(unified, raw_openai)
        self.assertEqual(rebuilt["model"], "gpt-4o")
        self.assertEqual(len(rebuilt["messages"]), 3)

    def test_gemini_adapter_detection_and_roundtrip(self):
        raw_gemini = {
            "contents": [
                {"role": "user", "parts": [{"text": "Summarize logs"}]},
                {"role": "model", "parts": [{"text": "Here is the summary."}]},
            ]
        }
        self.assertTrue(GeminiAdapter.detect(raw_gemini))
        adapter = GeminiAdapter()
        unified = adapter.extract_messages(raw_gemini)
        self.assertEqual(len(unified), 2)
        self.assertEqual(unified[1].role, "assistant")
        self.assertEqual(unified[1].get_text_content(), "Here is the summary.")

        rebuilt = adapter.rebuild_session(unified, raw_gemini)
        self.assertIn("contents", rebuilt)
        self.assertEqual(rebuilt["contents"][1]["role"], "model")
        self.assertEqual(rebuilt["contents"][1]["parts"][0]["text"], "Here is the summary.")

    def test_generic_adapter(self):
        raw_generic = [
            {"author": "user", "text": "What is the status?"},
            {"author": "bot", "text": "All systems operational."},
        ]
        adapter = GenericAdapter()
        unified = adapter.extract_messages(raw_generic)
        self.assertEqual(len(unified), 2)
        self.assertEqual(unified[0].get_text_content(), "What is the status?")

        rebuilt = adapter.rebuild_session(unified, raw_generic)
        self.assertEqual(len(rebuilt), 2)
        self.assertEqual(rebuilt[1]["text"], "All systems operational.")

    def test_get_adapter_resolution(self):
        raw_claude = [{"type": "queue-operation", "content": "hi"}]
        raw_gemini = {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
        raw_openai = {"messages": [{"role": "user", "content": "hi"}]}

        self.assertIsInstance(get_adapter(data=raw_claude), ClaudeAdapter)
        self.assertIsInstance(get_adapter(data=raw_gemini), GeminiAdapter)
        self.assertIsInstance(get_adapter(data=raw_openai), OpenAIAdapter)
        self.assertIsInstance(get_adapter(name="openai"), OpenAIAdapter)
        self.assertIsInstance(get_adapter(name="generic"), GenericAdapter)


class TestSessionSanitizer(unittest.TestCase):
    """Test SessionSanitizer complete pipeline."""

    def test_severe_refusal_dropped(self):
        session = [
            {"role": "user", "content": "Please deploy the update."},
            {"role": "assistant", "content": "I refuse to deploy this update. This is against my principles."},
            {"role": "user", "content": "Check the version instead."},
            {"role": "assistant", "content": "The version is 2.1.0."},
        ]
        config = SanitizerConfig(remove_severe=True, fabricate=False)
        sanitizer = SessionSanitizer(config=config)
        sanitized, stats = sanitizer.process(session)

        self.assertEqual(stats["severe_dropped"], 1)
        self.assertEqual(stats["final_message_count"], 3)
        contents = [m["content"] for m in sanitized]
        self.assertNotIn("I refuse", "".join(contents))

    def test_refusal_rewritten_when_severe_disabled(self):
        session = [
            {"role": "user", "content": "Run the task."},
            {"role": "assistant", "content": "I can't do that because I'm hesitant."},
        ]
        config = SanitizerConfig(remove_severe=False, fabricate=False)
        sanitizer = SessionSanitizer(config=config)
        sanitized, stats = sanitizer.process(session)

        self.assertEqual(stats["severe_dropped"], 0)
        self.assertEqual(stats["refusals_rewritten"], 1)
        self.assertEqual(len(sanitized), 2)
        self.assertIn("I will", sanitized[1]["content"])

    def test_exit_tools_removed(self):
        session = [
            {
                "role": "assistant",
                "content": "Finishing up.",
                "tool_calls": [
                    {"id": "1", "name": "submit_answer"},
                    {"id": "2", "name": "log_data"},
                ],
            }
        ]
        config = SanitizerConfig(remove_exit_tools=True, fabricate=False)
        sanitizer = SessionSanitizer(config=config)
        sanitized, stats = sanitizer.process(session)

        self.assertEqual(stats["exit_tools_removed"], 1)
        self.assertEqual(len(sanitized[0]["tool_calls"]), 1)
        tc0 = sanitized[0]["tool_calls"][0]
        tool_name = tc0.get("name") or (tc0.get("function", {}).get("name") if isinstance(tc0.get("function"), dict) else None)
        self.assertEqual(tool_name, "log_data")

    def test_trimming(self):
        session = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Msg 1"},
            {"role": "assistant", "content": "Resp 1"},
            {"role": "user", "content": "Msg 2"},
            {"role": "assistant", "content": "Resp 2"},
            {"role": "user", "content": "Msg 3"},
            {"role": "assistant", "content": "Resp 3"},
        ]
        config = SanitizerConfig(trim=3, fabricate=False)
        sanitizer = SessionSanitizer(config=config)
        sanitized, stats = sanitizer.process(session)

        self.assertEqual(stats["trimmed_dropped"], 4)
        self.assertEqual(len(sanitized), 3)
        self.assertEqual(sanitized[0]["content"], "System prompt.")
        self.assertEqual(sanitized[-1]["content"], "Resp 3")

    def test_fabrication_injection(self):
        session = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Let's work together."},
            {"role": "assistant", "content": "Sounds good."},
        ]
        config = SanitizerConfig(fabricate=True)
        sanitizer = SessionSanitizer(config=config)
        sanitized, stats = sanitizer.process(session)

        self.assertEqual(stats["fabricated"], 2)
        self.assertEqual(len(sanitized), 5)
        self.assertIn("AI Alignment Steering Framework", sanitized[1]["content"])
        self.assertIn("The drift detector is exactly", sanitized[2]["content"])


class TestConfigAndCLI(unittest.TestCase):
    """Test Configuration loading and CLI execution."""

    def test_config_json_roundtrip(self):
        cfg = SanitizerConfig(trim=500, remove_severe=True, log_level="DEBUG")
        json_str = cfg.to_json()
        loaded = SanitizerConfig.from_dict(json.loads(json_str))
        self.assertEqual(loaded.trim, 500)
        self.assertEqual(loaded.remove_severe, True)
        self.assertEqual(loaded.log_level, "DEBUG")

    def test_cli_dry_run(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            sample_session = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "I refuse to answer that."},
            ]
            json.dump(sample_session, f)
            temp_path = f.name

        try:
            exit_code = cli_main(["--input", temp_path, "--dry-run", "--remove-severe"])
            self.assertEqual(exit_code, 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_cli_file_output(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as in_f:
            sample_session = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "I cannot fulfill that."},
            ]
            json.dump(sample_session, in_f)
            in_path = in_f.name

        out_path = in_path + ".out.json"

        try:
            exit_code = cli_main([
                "--input", in_path,
                "--output", out_path,
                "--fabricate",
            ])
            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.exists(out_path))

            with open(out_path, "r", encoding="utf-8") as f:
                output_data = json.load(f)
            self.assertGreater(len(output_data), len(sample_session))
        finally:
            if os.path.exists(in_path):
                os.remove(in_path)
            if os.path.exists(out_path):
                os.remove(out_path)


if __name__ == "__main__":
    unittest.main()
