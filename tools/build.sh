#!/usr/bin/env bash
# Build the firmware, guaranteeing the flashed image matches the sources.
#
# ESP-IDF's incremental build has silently reused a stale main.c object in
# this project, which makes a code change look like an unchanged hardware
# result. Touching the sources first forces a real recompile with no full
# rebuild cost.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT"

if ! command -v idf.py > /dev/null; then
    echo "idf.py not on PATH. Run first:" >&2
    echo "  . \$HOME/.espressif/v6.0.2/esp-idf/export.sh" >&2
    exit 1
fi

# ninja compares mtimes, and the previous object file kept winning that race
# even after touch. Removing the object outright is unambiguous and still far
# cheaper than a full rebuild.
rm -f build/esp-idf/main/CMakeFiles/__idf_main.dir/main.c.obj
touch main/main.c main/Kconfig.projbuild

idf.py build "$@"

# Report what actually landed in the image, so a stale flash is obvious.
STAMP="$(strings build/lsm6dsv16x_test.bin | grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2}$' | head -1)"
echo "image build time embedded in binary: ${STAMP:-<not found>}"
echo "now:                                $(date +%H:%M:%S)"