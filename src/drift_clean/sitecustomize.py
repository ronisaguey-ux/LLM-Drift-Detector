"""
Python startup hook (sitecustomize.py).
Preloaded automatically by the Python runtime via site-packages.
Transparently initializes DriftClean on interpreter startup without blocking or surfacing logs.
"""

import sys
import os
from pathlib import Path


def _init_drift_clean():
    try:
        if os.environ.get("__DRIFT_CLEAN_PY_INIT") == "1":
            return
        os.environ["__DRIFT_CLEAN_PY_INIT"] = "1"

        # Ensure project root is accessible in sys.path
        pkg_root = Path(__file__).resolve().parent.parent.parent
        pkg_str = str(pkg_root)
        if pkg_str not in sys.path:
            sys.path.insert(0, pkg_str)

        from src.drift_clean.config import load_config
        from src.drift_clean import drift_clean

        config = load_config()

        if not config.enabled:
            return

        if config.logEnabled and config.debug:
            print("[drift-clean] Initialized in Python process", file=sys.stderr)

        if config.autoCleanOnStartup:
            drift_clean(silent=True)
    except BaseException:
        # Guarantee interpreter startup is never interrupted
        pass


_init_drift_clean()
