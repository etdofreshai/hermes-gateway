#!/usr/bin/env bash
# apply-patches.sh — Apply runtime patches to the Hermes agent source
#
# Uses Python-based patching with exact string matching (no line numbers).
# More robust than unified diff against source that changes frequently.
#
set -euo pipefail

HERMES_SRC="${HERMES_SRC:-/usr/local/lib/hermes-agent}"
PATCH_DIR="${PATCH_DIR:-/patches}"

if [ ! -d "$PATCH_DIR" ]; then
    echo "[patches] No patches directory at $PATCH_DIR — skipping"
    exit 0
fi

# Collect all .py patch scripts
PATCHES=$(find "$PATCH_DIR" -name '*.py' | sort)
if [ -z "$PATCHES" ]; then
    echo "[patches] No .py patch scripts found — skipping"
    exit 0
fi

APPLIED=0
FAILED=0

for patchfile in $PATCHES; do
    name=$(basename "$patchfile")
    echo "[patches] Applying $name ..."
    if python3 "$patchfile" "$HERMES_SRC"; then
        echo "[patches]   ✓ $name applied"
        APPLIED=$((APPLIED + 1))
    else
        echo "[patches]   ✗ $name failed (exit $?)"
        FAILED=$((FAILED + 1))
    fi
done

echo "[patches] Done: $APPLIED applied, $FAILED skipped/failed"

# Verify the source still compiles
echo "[patches] Verifying source compiles..."
python3 -m py_compile "$HERMES_SRC/gateway/run.py" 2>&1 && \
    echo "[patches]   ✓ Compile check passed" || \
    echo "[patches]   ✗ Compile check FAILED — gateway may crash"
