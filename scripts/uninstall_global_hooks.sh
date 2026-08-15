#!/usr/bin/env bash
# uninstall_global_hooks.sh — Removes DriftClean global environment hooks
set -euo pipefail

echo "🗑️ Removing DriftClean Global AI Toolchain Hooks..."

PY_USER_SITE="$(python3 -m site --user-site 2>/dev/null || true)"
if [ -n "$PY_USER_SITE" ] && [ -f "$PY_USER_SITE/sitecustomize.py" ]; then
    rm -f "$PY_USER_SITE/sitecustomize.py"
    echo "✅ Removed: $PY_USER_SITE/sitecustomize.py"
fi

remove_from_file() {
    local target_file="$1"
    if [ -f "$target_file" ] && grep -q "DRIFT_CLEAN_HOOKS" "$target_file"; then
        sed -i '/# >>> DRIFT_CLEAN_HOOKS >>>/,/# <<< DRIFT_CLEAN_HOOKS <<</d' "$target_file"
        echo "✅ Cleaned: $target_file"
    fi
}

remove_from_file "$HOME/.bashrc"
remove_from_file "$HOME/.profile"
[ -f "$HOME/.zshrc" ] && remove_from_file "$HOME/.zshrc"

echo "🎉 DriftClean global hooks uninstalled."
