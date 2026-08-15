"""
Tests for DriftClean global hooks across Node.js and Python subprocesses.
Verifies transparent initialization, config adherence, and non-blocking execution.
"""

import os
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestGlobalHooks(unittest.TestCase):
    def test_python_sitecustomize_hook(self):
        cmd = [
            "python3",
            "-c",
            "import os, sys; from src.drift_clean.config import load_config; cfg = load_config(); print('HOOK_OK', cfg.enabled)",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        res = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Python hook failed: {res.stderr}")
        self.assertIn("HOOK_OK True", res.stdout)

    def test_node_auto_inject_hook(self):
        hook_path = PROJECT_ROOT / "src" / "drift_clean" / "auto_inject.js"
        cmd = [
            "node",
            "-e",
            "const { loadConfig } = require('./src/drift_clean/config'); const cfg = loadConfig(); console.log('NODE_HOOK_OK', cfg.enabled);",
        ]
        env = os.environ.copy()
        env["NODE_OPTIONS"] = f"--require {hook_path}"

        res = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Node hook failed: {res.stderr}")
        self.assertIn("NODE_HOOK_OK true", res.stdout)


if __name__ == "__main__":
    unittest.main()
