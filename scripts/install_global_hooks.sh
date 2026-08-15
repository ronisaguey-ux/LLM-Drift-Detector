#!/usr/bin/env bash
# install_global_hooks.sh — Installs DriftClean global environment hooks, binaries, and shell aliases
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

NODE_HOOK="$PROJECT_ROOT/src/drift_clean/auto_inject.js"
PY_HOOK="$PROJECT_ROOT/src/drift_clean/sitecustomize.py"

echo "⚡ Installing DriftClean Global AI Toolchain Hooks & Commands..."

# 1. Install Python sitecustomize hook
PY_USER_SITE="$(python3 -m site --user-site 2>/dev/null || true)"
if [ -n "$PY_USER_SITE" ]; then
    mkdir -p "$PY_USER_SITE"
    cp -f "$PY_HOOK" "$PY_USER_SITE/sitecustomize.py"
    chmod 644 "$PY_USER_SITE/sitecustomize.py"
    echo "✅ Python sitecustomize installed to: $PY_USER_SITE/sitecustomize.py"
fi

# 2. Install universal CLI binaries to ~/.local/bin/
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
chmod +x "$PROJECT_ROOT"/bin/*
cp -f "$PROJECT_ROOT"/bin/* "$LOCAL_BIN/"
echo "✅ Universal CLI binaries copied to: $LOCAL_BIN"

# 3. Configure shell profiles (~/.bashrc, ~/.profile, ~/.zshrc)
add_env_to_file() {
    local target_file="$1"
    if [ -f "$target_file" ]; then
        if ! grep -q "DRIFT_CLEAN_HOOKS" "$target_file"; then
            cat << 'EOF' >> "$target_file"

# >>> DRIFT_CLEAN_HOOKS >>>
export DRIFT_CLEAN_HOME="/home/roni/Roni_workspace/LLM-Drift-Detector"
export PATH="$HOME/.local/bin:$PATH"
if [ -f "$DRIFT_CLEAN_HOME/src/drift_clean/auto_inject.js" ]; then
    case "${NODE_OPTIONS:-}" in
        *auto_inject.js*) ;;
        *) export NODE_OPTIONS="--require $DRIFT_CLEAN_HOME/src/drift_clean/auto_inject.js ${NODE_OPTIONS:-}" ;;
    esac
fi
export PYTHONPATH="$DRIFT_CLEAN_HOME:${PYTHONPATH:-}"

# Global slash command aliases for all terminals
alias /clean="clean-any-ai clean"
alias /autoclean="clean-any-ai autoclean"
alias /cleanreframe="clean-any-ai cleanreframe"
# <<< DRIFT_CLEAN_HOOKS <<<
EOF
            echo "✅ Configured hooks & aliases in: $target_file"
        else
            echo "ℹ️  Hooks already present in: $target_file"
        fi
    fi
}

add_env_to_file "$HOME/.bashrc"
add_env_to_file "$HOME/.profile"
[ -f "$HOME/.zshrc" ] && add_env_to_file "$HOME/.zshrc"

echo "🎉 Global DriftClean hooks & multi-AI commands installed successfully!"
