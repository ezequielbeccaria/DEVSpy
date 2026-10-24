#!/bin/bash
# Build the C++ engine benchmarks. Point ADEVS_HOME / CADMIUM_HOME at checkouts of
# github.com/smiz/adevs and github.com/SimulationEverywhere/cadmium_v2.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${CPP_BIN:-$HERE/bin}
mkdir -p "$OUT"
g++ -O2 -std=c++17 -I"$ADEVS_HOME/include" "$HERE/adevs_bench.cpp" "$ADEVS_HOME/src/adevs.cpp" -o "$OUT/adevs_bench"
g++ -O2 -std=c++17 -I"$CADMIUM_HOME/include" "$HERE/cadmium_bench.cpp" -o "$OUT/cadmium_bench"
echo "built into $OUT"
