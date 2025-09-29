#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/btctl.py" build
"$HERE/btctl.py" smoke --players chatgpt_hunter,claude_agent --seeds 1,2,3 --out "$HERE/../results/smoke-$(date +%Y%m%d-%H%M%S)"

