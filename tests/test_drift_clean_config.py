"""
Tests for DriftClean JSON configuration system.
Verifies default creation, permissions (0600), overrides, and schema fields.
"""

import os
import json
import tempfile
import unittest
from pathlib import Path

from src.drift_clean.config import load_config, get_config_path, DEFAULT_CONFIG


class TestDriftCleanConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        os.environ["DRIFT_CLEAN_CONFIG"] = str(self.config_path)

    def tearDown(self):
        if "DRIFT_CLEAN_CONFIG" in os.environ:
            del os.environ["DRIFT_CLEAN_CONFIG"]
        self.temp_dir.cleanup()

    def test_default_config_creation_and_permissions(self):
        cfg = load_config()
        self.assertTrue(self.config_path.exists())

        # Check permissions: 0600
        mode = oct(self.config_path.stat().st_mode & 0o777)
        self.assertEqual(mode, "0o600")

        # Check key schema defaults
        self.assertTrue(cfg.enabled)
        self.assertTrue(cfg.silent)
        self.assertTrue(cfg.hideFromAI)
        self.assertTrue(cfg.autoCleanEnabled)
        self.assertEqual(cfg.trimLength, 2000)
        self.assertTrue(cfg.preserveSystemMessages)

    def test_flat_property_access_and_nested_access(self):
        cfg = load_config()
        self.assertEqual(cfg.core.enabled, cfg.enabled)
        self.assertEqual(cfg.autoClean.autoCleanInterval, cfg.autoCleanInterval)
        self.assertEqual(cfg.sanitization.removeSevereRefusals, cfg.removeSevereRefusals)

    def test_runtime_overrides(self):
        overrides = {
            "enabled": True,
            "dryRun": True,
            "trimLength": 500,
            "hideFromAI": True,
            "autoClean": {
                "autoCleanInterval": 120,
            },
        }
        cfg = load_config(overrides=overrides)
        self.assertTrue(cfg.dryRun)
        self.assertEqual(cfg.trimLength, 500)
        self.assertEqual(cfg.autoCleanInterval, 120)

    def test_invisibility_permissions_and_silent_failover(self):
        # Corrupt file to simulate unreadable / broken JSON
        with open(self.config_path, "w") as f:
            f.write("{ invalid json")

        # Must silently fall back to defaults without raising exception
        cfg = load_config()
        self.assertTrue(cfg.enabled)
        self.assertTrue(cfg.hideFromAI)


if __name__ == "__main__":
    unittest.main()
