#!/usr/bin/env bash
# Switch the firmware between the health-test and streaming modes.
#
#   tools/mode.sh test      # 23-check suite, prints UNIT_RESULT
#   tools/mode.sh stream    # NDJSON feed for tools/web_panel.py
#   tools/mode.sh           # report the mode currently configured
#
# The mode lives in sdkconfig, which ESP-IDF regenerates from the defaults
# files. Because defaults are only applied when sdkconfig is generated,
# switching modes deletes it and rebuilds the configuration — the compiled
# objects survive, so this costs seconds, not a full rebuild.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT"

if ! command -v idf.py > /dev/null; then
    echo "idf.py not on PATH. Run first:" >&2
    echo "  . \$HOME/.espressif/v6.0.2/esp-idf/export.sh" >&2
    exit 1
fi

current() {
    if grep -q '^CONFIG_RUN_MODE_STREAM=y' sdkconfig 2>/dev/null; then
        echo stream
    else
        echo test
    fi
}

case "${1:-}" in
    "")
        echo "current mode: $(current)"
        exit 0
        ;;
    test)
        defaults="sdkconfig.defaults"
        ;;
    stream)
        defaults="sdkconfig.defaults;sdkconfig.stream"
        ;;
    *)
        echo "usage: $0 [test|stream]" >&2
        exit 2
        ;;
esac

before="$(current)"
rm -f sdkconfig
SDKCONFIG_DEFAULTS="$defaults" idf.py reconfigure > /dev/null

after="$(current)"
echo "mode: $before -> $after (defaults: $defaults)"
if [ "$before" != "$after" ]; then
    echo "rebuild and flash to apply, e.g.:"
    echo "  idf.py flash -p /dev/ttyACM0"
fi