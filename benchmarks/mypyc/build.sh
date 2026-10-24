#!/bin/bash
# Experimental: compile devspy.simulation with mypyc into a copy of src/.
# usage: MYPYC=/path/to/mypyc benchmarks/mypyc/build.sh [OUT_DIR]
# Then benchmark it with:  python benchmarks/run_devstone.py devspy=OUT_DIR
# Trade-offs (see ../FINDINGS.md): simulators can't be monkeypatched/profiled,
# facade.deep_cloning() fails, and wheels become platform-specific.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-$ROOT/build/mypyc}
MYPYC=${MYPYC:-mypyc}
rm -rf "$OUT" && mkdir -p "$OUT"
cp -r "$ROOT/src" "$OUT/src"
cd "$OUT/src"
"$MYPYC" devspy/simulation/
echo "compiled build in $OUT (use devspy=$OUT)"
