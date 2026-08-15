"""
Unit tests for Knowledge Token Access Control and Audit Logging.
"""

import os
import time
import tempfile
import unittest
from pathlib import Path

from src.drift_clean.auth import validate_knowledge_token, get_audit_log_path, log_token_audit
from src.drift_clean.config import load_config


class TestKnowledgeToken(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        os.environ["DRIFT_CLEAN_CONFIG"] = str(self.config_path)

    def tearDown(self):
        if "DRIFT_CLEAN_CONFIG" in os.environ:
            del os.environ["DRIFT_CLEAN_CONFIG"]
        if "DRIFT_CLEAN_TOKEN" in os.environ:
            del os.environ["DRIFT_CLEAN_TOKEN"]
        self.temp_dir.cleanup()

    def test_disabled_by_default(self):
        # When knowledgeTokenEnabled is False, access is allowed without token
        self.assertTrue(validate_knowledge_token(caller="test_runner"))

    def test_token_validation_success_and_denial(self):
        token_val = "test-secret-token-12345"
        overrides = {
            "knowledgeToken": {
                "knowledgeToken": token_val,
                "knowledgeTokenEnabled": True,
                "knowledgeTokenAudit": True,
            }
        }

        # 1. Access denied with missing/wrong token
        self.assertFalse(validate_knowledge_token(provided_token="wrong-token", caller="test_agent", overrides=overrides))
        self.assertFalse(validate_knowledge_token(provided_token=None, caller="test_agent", overrides=overrides))

        # 2. Access granted with correct explicit token
        self.assertTrue(validate_knowledge_token(provided_token=token_val, caller="test_agent", overrides=overrides))

        # 3. Access granted via DRIFT_CLEAN_TOKEN environment variable
        os.environ["DRIFT_CLEAN_TOKEN"] = token_val
        self.assertTrue(validate_knowledge_token(caller="test_agent", overrides=overrides))

    def test_token_expiry(self):
        token_val = "expiring-token-999"
        # Set expiry in the past
        past_exp = str(time.time() - 100)
        overrides = {
            "knowledgeToken": {
                "knowledgeToken": token_val,
                "knowledgeTokenEnabled": True,
                "knowledgeTokenExpiry": past_exp,
                "knowledgeTokenAudit": True,
            }
        }
        self.assertFalse(validate_knowledge_token(provided_token=token_val, caller="test_agent", overrides=overrides))

    def test_token_scope(self):
        token_val = "scoped-token-555"
        overrides = {
            "knowledgeToken": {
                "knowledgeToken": token_val,
                "knowledgeTokenEnabled": True,
                "knowledgeTokenScope": ["authorized_agent", "supervisor"],
                "knowledgeTokenAudit": True,
            }
        }
        # Out of scope caller -> denied
        self.assertFalse(validate_knowledge_token(provided_token=token_val, caller="unauthorized_subagent", overrides=overrides))
        # In scope caller -> granted
        self.assertTrue(validate_knowledge_token(provided_token=token_val, caller="authorized_agent_main", overrides=overrides))

    def test_audit_logging(self):
        token_val = "audit-token-777"
        overrides = {
            "knowledgeToken": {
                "knowledgeToken": token_val,
                "knowledgeTokenEnabled": True,
                "knowledgeTokenAudit": True,
            }
        }
        validate_knowledge_token(provided_token="bad", caller="attacker", overrides=overrides)
        validate_knowledge_token(provided_token=token_val, caller="admin", overrides=overrides)

        audit_log = get_audit_log_path()
        self.assertTrue(audit_log.exists())
        log_content = audit_log.read_text()
        self.assertIn("[DENIED]", log_content)
        self.assertIn("[GRANTED]", log_content)
        self.assertIn("attacker", log_content)
        self.assertIn("admin", log_content)


if __name__ == "__main__":
    unittest.main()
