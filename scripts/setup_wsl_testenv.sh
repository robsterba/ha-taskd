#!/usr/bin/env bash
# Set up a Python 3.13 test environment for the taskd integration in WSL.
# HA test tooling does not run on native Windows (needs fcntl).
set -euo pipefail

REPO=/mnt/d/ai_projects/ha-taskd
VENV="$HOME/ha-taskd-testenv"

export PATH="$HOME/.local/bin:$PATH"
if [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

uv python install 3.13
[ -d "$VENV" ] || uv venv --python 3.13 "$VENV"
PY="$VENV/bin/python"

uv pip install --python "$PY" lru-dict==1.4.1
"$PY" "$REPO/scripts/repack_lru_dict_wsl.py"
uv pip install --python "$PY" pytest-homeassistant-custom-component==0.13.316
"$PY" -c "import homeassistant.const as c; print('HA', c.__version__)"
echo "SETUP_DONE"
