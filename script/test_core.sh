#!/usr/bin/env bash
# Run the tests, ruff and hassfest against a Home Assistant core checkout
# (default: ../core, set up with `script/setup` and python-socketio installed).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$(cd "${CORE:-$REPO/../core}" && pwd)"
PY="$CORE/.venv/bin/python"

# Map pytest-homeassistant-custom-component onto core's own test helpers.
SHIM="$(mktemp -d)"
trap 'rm -rf "$SHIM"' EXIT
PKG="$SHIM/pytest_homeassistant_custom_component"
mkdir -p "$PKG/test_util"
touch "$PKG/__init__.py" "$PKG/test_util/__init__.py"
echo "from tests.common import *  # noqa: F403" > "$PKG/common.py"
echo "from tests.common import MockConfigEntry, async_capture_events  # noqa: F401" >> "$PKG/common.py"
echo "from tests.test_util.aiohttp import AiohttpClientMocker  # noqa: F401" > "$PKG/test_util/aiohttp.py"

echo "Home Assistant $("$PY" -c 'from homeassistant.const import __version__; print(__version__)')"

cd "$REPO"
PYTHONPATH="$SHIM:$CORE:$REPO" "$PY" -m pytest -p tests.conftest -p no:cacheprovider "$@" tests
"$CORE/.venv/bin/ruff" check --config "$CORE/pyproject.toml" --extend-ignore INP001 custom_components tests
"$CORE/.venv/bin/ruff" format --check --config "$CORE/pyproject.toml" custom_components tests

cd "$CORE"
PATH="$CORE/.venv/bin:$PATH" "$PY" -m script.hassfest \
  --integration-path "$REPO/custom_components/voipcenter"
