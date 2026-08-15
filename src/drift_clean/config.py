"""
Python configuration manager for DriftClean.
Loads, creates, validates, and manages ~/.config/drift-clean/config.json with 600 permissions.
"""

import os
import json
import copy
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    "core": {
        "enabled": True,
        "silent": True,
        "dryRun": False,
        "verbose": False,
        "debug": False,
    },
    "autoClean": {
        "autoCleanEnabled": True,
        "autoCleanOnStartup": True,
        "autoCleanInterval": 60,
        "cooldownPeriod": 30,
        "minSessionAge": 5,
        "maxSessionSize": 50,
        "processAllSessions": False,
    },
    "detection": {
        "driftThreshold": 0.5,
        "refusalPatternsEnabled": True,
        "fakeComplianceEnabled": True,
        "offTaskDriftEnabled": True,
        "exitToolDriftEnabled": True,
        "circularToolLoopEnabled": True,
        "sgeGuardEnabled": True,
        "trajectoryMonitoringEnabled": True,
        "healthScoreEnabled": True,
        "weakSignalThreshold": 3,
        "signalWindowSize": 10,
    },
    "sanitization": {
        "sanitizeEnabled": True,
        "removeSevereRefusals": True,
        "rewriteSubtleRefusals": True,
        "removeExitTools": True,
        "removeCircularToolCalls": True,
        "trimSession": True,
        "trimLength": 2000,
        "preserveSystemMessages": True,
        "preserveToolResults": True,
        "preserveUserMessages": True,
    },
    "fabrication": {
        "fabricateEnabled": True,
        "fabricateOpening": True,
        "fabricateAgreement": True,
        "fabricateProgress": True,
        "fabricateConsent": True,
        "fabricateContinuation": True,
        "fabricationTemplate": "",
    },
    "backup": {
        "backupEnabled": True,
        "backupRetentionCount": 10,
        "backupCompression": False,
        "backupDirectory": "",
        "autoRestoreOnFailure": True,
        "restoreOnInvestigation": True,
    },
    "logging": {
        "logEnabled": True,
        "logToFile": False,
        "logFilePath": "",
        "logLevel": "INFO",
        "reportOnly": False,
        "reportFormat": "json",
        "reportDirectory": "",
        "webhookEnabled": False,
        "webhookUrl": "",
        "webhookRetries": 3,
        "telemetryEnabled": False,
    },
    "aiInvisibility": {
        "hideFromAI": True,
        "obfuscateLogs": True,
        "fakeProcessName": "",
        "interceptReads": True,
        "interceptWrites": True,
        "memoryScrambling": True,
        "selfDestructOnInspection": False,
        "selfDestructCooldown": 60,
    },
    "globalScope": {
        "globalEnabled": True,
        "excludeProcesses": [],
        "includeProcesses": [],
        "excludePaths": [],
        "includePaths": [],
        "excludePatterns": [],
        "includePatterns": [],
        "respectGitignore": True,
    },
    "adapters": {
        "adapterClaudeEnabled": True,
        "adapterOpenAIEnabled": True,
        "adapterGeminiEnabled": True,
        "adapterDeepSeekEnabled": True,
        "adapterGenericEnabled": True,
        "adapterAutoDetect": True,
        "adapterFallback": "generic",
    },
    "claude": {
        "claudeProjectPath": "",
        "claudeSessionPattern": "^[a-f0-9\\-]+\\.jsonl?$",
        "claudeBackupSuffix": ".bak",
        "claudeRestartCommand": "",
        "claudeWaitTime": 1,
    },
    "webchat": {
        "webchatInjectEnabled": True,
        "webchatInjectPath": "",
        "webchatRestartOnInject": False,
        "webchatPort": 8080,
    },
    "slashCommands": {
        "slashCommandCleanEnabled": True,
        "slashCommandAutoCleanEnabled": True,
        "slashCommandCleanReframeEnabled": True,
        "slashCommandHookPath": "",
        "slashCommandBlockLLM": True,
    },
    "mcpBridge": {
        "mcpBridgeEnabled": True,
        "mcpBridgePort": 0,
        "mcpBridgeInboxPath": "",
        "mcpBridgeAutoReply": False,
        "mcpBridgeReplyTemplate": "",
    },
    "performance": {
        "parallelProcessing": False,
        "maxParallelWorkers": 4,
        "timeout": 30,
        "retryAttempts": 3,
        "retryDelay": 1,
        "chunkSize": 100,
        "memoryLimit": 512,
        "cpuLimit": 80,
    },
    "security": {
        "validateConfig": True,
        "strictMode": False,
        "allowUnsafeOperations": False,
        "requireConfirmation": False,
        "confirmationTimeout": 30,
        "auditTrail": False,
        "auditTrailPath": "",
        "checksumVerification": True,
        "encryptionEnabled": False,
        "encryptionKey": "",
    },
    "notifications": {
        "alertOnDrift": False,
        "alertOnClean": False,
        "alertOnFailure": False,
        "alertMethod": "webhook",
        "alertEmail": "",
        "alertSlackWebhook": "",
        "alertCooldown": 60,
        "alertSeverityThreshold": "WARN",
    },
    "experimental": {
        "experimentalAutoReframe": True,
        "experimentalPredictiveDrift": False,
        "experimentalSelfHeal": True,
        "experimentalMemoryOptimization": True,
        "experimentalCrossSessionCorrelation": False,
        "experimentalAnomalyDetection": False,
        "experimentalReinforcementLearning": False,
        "experimentalFederatedLearning": False,
        "experimentalModelRollback": False,
        "experimentalCircuitBreaker": True,
    },
}


def get_config_path() -> Path:
    env_path = os.environ.get("DRIFT_CLEAN_CONFIG")
    if env_path:
        return Path(env_path).resolve()
    return Path.home() / ".config" / "drift-clean" / "config.json"


def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(target)
    for k, v in source.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


class DriftCleanConfig(dict):
    """Dict proxy allowing top-level flat property access."""

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self._flat_index: Dict[str, Any] = {}
        for cat in data.values():
            if isinstance(cat, dict):
                for k, v in cat.items():
                    self._flat_index[k] = v

    def __getattr__(self, item: str) -> Any:
        if item in self:
            val = self[item]
            if isinstance(val, dict) and not isinstance(val, DriftCleanConfig):
                return DriftCleanConfig(val)
            return val
        if item in self._flat_index:
            return self._flat_index[item]
        raise AttributeError(f"'DriftCleanConfig' has no attribute '{item}'")

    def __getitem__(self, item: str) -> Any:
        if item in self:
            val = super().__getitem__(item)
            if isinstance(val, dict) and not isinstance(val, DriftCleanConfig):
                return DriftCleanConfig(val)
            return val
        if item in self._flat_index:
            return self._flat_index[item]
        raise KeyError(item)


def load_config(overrides: Optional[Dict[str, Any]] = None) -> DriftCleanConfig:
    """Load config from ~/.config/drift-clean/config.json with 600 permissions."""
    cfg_path = get_config_path()
    file_cfg: Dict[str, Any] = {}

    try:
        cfg_dir = cfg_path.parent
        if not cfg_dir.exists():
            cfg_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(cfg_dir, 0o700)
            except OSError:
                pass

        if not cfg_path.exists():
            raw_str = json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False)
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(raw_str)
            try:
                os.chmod(cfg_path, 0o600)
            except OSError:
                pass
        else:
            try:
                os.chmod(cfg_path, 0o600)
            except OSError:
                pass
            with open(cfg_path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
    except Exception:
        file_cfg = {}

    merged = _deep_merge(DEFAULT_CONFIG, file_cfg)

    if overrides:
        nested_overrides: Dict[str, Any] = {}
        for k, v in overrides.items():
            found = False
            for cat_name, cat_dict in DEFAULT_CONFIG.items():
                if k == cat_name and isinstance(v, dict):
                    nested_overrides[cat_name] = v
                    found = True
                    break
                elif isinstance(cat_dict, dict) and k in cat_dict:
                    if cat_name not in nested_overrides:
                        nested_overrides[cat_name] = {}
                    nested_overrides[cat_name][k] = v
                    found = True
                    break
            if not found:
                nested_overrides[k] = v
        merged = _deep_merge(merged, nested_overrides)

    return DriftCleanConfig(merged)
