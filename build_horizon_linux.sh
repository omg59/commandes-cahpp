#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "La construction AppImage nécessite Linux x86_64." >&2
  exit 1
fi

CAHPP_LINUX_PYTHON="${CAHPP_LINUX_PYTHON:-python3}"
if [[ ! -x .venv-horizon/bin/python ]]; then
  "$CAHPP_LINUX_PYTHON" -m venv .venv-horizon
fi
.venv-horizon/bin/python -m pip install -r requirements-horizon.txt -r requirements-dev.txt
.venv-horizon/bin/python -m tools.build_horizon_linux "$@"
