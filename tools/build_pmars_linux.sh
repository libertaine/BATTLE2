#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_VERSION="0.9.5"
readonly EXPECTED_COPYING_SHA256="58530d09b6fcb91ae27071be0081af90e6c2d7fdf991d34a29e234a2a5e75455"
readonly EXPECTED_CHANGELOG_SHA256="f1bf0086bf0fefb1aeba01e51aea0065e194f9106488f1020cf937a5425a9b0b"
readonly EXPECTED_PMARS_C_SHA256="49f5f49b73d7f237e213949cd4367a441e333860790d3ab8c0f33c0d4e376c6b"
readonly EXPECTED_MAKEFILE_SHA256="136e8ddf4c9be0d118a30aa442ed8ada393bd5c70179376d43efa779b30b25b1"
readonly CONSOLE_CFLAGS="-O2 -DEXT94 -DPERMUTATE -DRWLIMIT"

usage() {
    echo "Usage: $0 SOURCE_DIR [OUTPUT_DIR]" >&2
    echo "Builds verified pMARS ${EXPECTED_VERSION} source without a graphical display." >&2
}

die() {
    echo "build_pmars_linux.sh: $*" >&2
    exit 2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

verify_file() {
    local expected="$1"
    local path="$2"
    local actual
    actual="$(sha256sum "$path" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || die "source verification failed for $path"
}

[[ $# -ge 1 && $# -le 2 ]] || {
    usage
    exit 2
}

for command_name in awk cp file gcc head install ldd make mkdir mktemp rm sed sha256sum strip; do
    require_command "$command_name"
done

source_dir="$(cd "$1" 2>/dev/null && pwd -P)" || die "source directory not found: $1"
output_dir="${2:-build/pmars-linux}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd -P)"

for required_file in COPYING ChangeLog README src/Makefile src/pmars.c; do
    [[ -f "$source_dir/$required_file" ]] || die "missing source file: $required_file"
done

verify_file "$EXPECTED_COPYING_SHA256" "$source_dir/COPYING"
verify_file "$EXPECTED_CHANGELOG_SHA256" "$source_dir/ChangeLog"
verify_file "$EXPECTED_PMARS_C_SHA256" "$source_dir/src/pmars.c"
verify_file "$EXPECTED_MAKEFILE_SHA256" "$source_dir/src/Makefile"

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/battle2-pmars-build.XXXXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT
cp -a "$source_dir/." "$build_dir/source"

export LC_ALL=C
export TZ=UTC
export SOURCE_DATE_EPOCH=1768129200

echo "pMARS source release: $EXPECTED_VERSION"
echo "Source directory: $source_dir"
echo "Compiler: $(gcc --version | head -n 1)"
echo "Build flags: $CONSOLE_CFLAGS"
echo "Graphical definitions: none (XWINGRAPHX, GRAPHX, and CURSESGRAPHX omitted)"

make -C "$build_dir/source/src" clean
make -C "$build_dir/source/src" \
    CC=gcc \
    CFLAGS="$CONSOLE_CFLAGS" \
    LDFLAGS="-Wl,--build-id=sha1" \
    LIB=""

install -m 0755 "$build_dir/source/src/pmars" "$output_dir/pmars"

echo "Output: $output_dir/pmars"
file "$output_dir/pmars"
ldd "$output_dir/pmars"
echo "Executable SHA-256: $(sha256sum "$output_dir/pmars" | awk '{print $1}')"
echo "Version/help banner:"
"$output_dir/pmars" -h 2>&1 | sed -n '1,4p' || true
