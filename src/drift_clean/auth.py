"""
Knowledge Token Access Control and Audit Logging for DriftClean.
Guarantees AI processes cannot inspect or modify drift-clean settings without a valid knowledge token.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from .config import load_config, get_config_path


def get_audit_log_path() -> Path:
    config_path = get_config_path()
    return config_path.parent / "audit.log"


def log_token_audit(event_type: str, success: bool, caller: Optional[str] = None, details: Optional[str] = None):
    """Append a token access or denial event to the audit log."""
    try:
        audit_path = get_audit_log_path()
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status = "GRANTED" if success else "DENIED"
        caller_str = caller or "unknown_process"
        detail_str = f" - {details}" if details else ""
        entry = f"[{ts}] [{status}] Event: {event_type} | Caller: {caller_str}{detail_str}\n"

        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(entry)
        try:
            os.chmod(audit_path, 0o600)
        except OSError:
            pass
    except Exception:
        pass


def get_provided_token(explicit_token: Optional[str] = None) -> Optional[str]:
    """Retrieve token from argument, environment variable, or token file."""
    if explicit_token:
        return explicit_token.strip()

    env_tok = os.environ.get("DRIFT_CLEAN_TOKEN")
    if env_tok:
        return env_tok.strip()

    token_file = get_config_path().parent / "token"
    if token_file.exists():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return None


def validate_knowledge_token(
    provided_token: Optional[str] = None,
    caller: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Validate whether the caller possesses the knowledge token to access/modify drift-clean.
    If knowledgeTokenEnabled is False, access is permitted by default.
    """
    config = load_config(overrides)
    kt_cfg = config.get("knowledgeToken", {})

    is_enabled = kt_cfg.get("knowledgeTokenEnabled", False)
    if not is_enabled:
        return True

    expected_token = kt_cfg.get("knowledgeToken", "")
    audit_enabled = kt_cfg.get("knowledgeTokenAudit", True)
    actual_token = get_provided_token(provided_token)

    # 1. Check token presence and match
    if not actual_token or actual_token != expected_token:
        if audit_enabled:
            log_token_audit("TOKEN_VALIDATION", success=False, caller=caller, details="Invalid or missing token")
        return False

    # 2. Check expiry if configured
    expiry_str = kt_cfg.get("knowledgeTokenExpiry", "")
    if expiry_str:
        try:
            exp_ts = float(expiry_str)
            if time.time() > exp_ts:
                if audit_enabled:
                    log_token_audit("TOKEN_VALIDATION", success=False, caller=caller, details="Token expired")
                return False
        except ValueError:
            pass

    # 3. Check scope if configured
    scope_list: List[str] = kt_cfg.get("knowledgeTokenScope", [])
    if scope_list and caller:
        if not any(s in caller for s in scope_list):
            if audit_enabled:
                log_token_audit("TOKEN_VALIDATION", success=False, caller=caller, details=f"Caller outside scope: {caller}")
            return False

    if audit_enabled:
        log_token_audit("TOKEN_VALIDATION", success=True, caller=caller, details="Access granted")
    return True
