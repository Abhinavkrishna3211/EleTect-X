#!/bin/sh
# Compile panns_logmel.cpp - the file that actually ships - against the real
# Edge Impulse type definitions, without needing a Studio export on disk.
#
# Worth having: the first version of this port compiled its own core cleanly
# and would still have failed at an integrator's build, because the EIDSP_*
# status enumerators live in namespace ei and had not been imported. That is
# exactly the class of error a reviewer skims past.
#
# The two real headers are downloaded, not vendored - they are copyright Edge
# Impulse and carry their Terms of Service. Everything else comes from stubs/,
# which is ours. See stubs/README.md.
#
# Usage:  ./syntax_check.sh [g++-or-clang++]
set -eu

CXX="${1:-g++}"
STD="${STD:-c++14}"   # what example-standalone-inferencing-linux builds with
RAW="https://raw.githubusercontent.com/edgeimpulse/inferencing-sdk-cpp/master"

# On Windows this script runs across two toolchains that do not share a
# filesystem view. MSYS mounts /tmp at the user's AppData temp directory;
# busybox-w32 - which lands on PATH ahead of MSYS the moment a w64devkit
# compiler does - reads /tmp literally, as C:\tmp. So "/tmp/x" names two
# different directories depending on which mktemp answered and which cp
# acts on it, and the failure is silent: the copy succeeds, somewhere else.
#
# A drive-letter path is the one spelling all three of busybox, MSYS and a
# native compiler resolve the same way, so everything below is kept in that
# form rather than converted at each use. On anything other than Windows
# there is no cygpath and no ambiguity, and the path passes through.
winpath() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$1"
    else
        printf '%s' "$1"
    fi
}

here="$(winpath "$(cd "$(dirname "$0")" && pwd)")"
tree="$(winpath "$(mktemp -d)")"
trap 'rm -rf "$tree"' EXIT

cp -r "$here/stubs/." "$tree/"

# The copy is the step that fails quietly when the spellings disagree, and
# its symptom - a stub that is not there - reads exactly like a missing
# SDK. Say which one it actually is.
if [ ! -f "$tree/edge-impulse-sdk/classifier/ei_model_types.h" ]; then
    echo "stubs did not copy into $tree - path handling, not a missing SDK" >&2
    exit 1
fi

# The repository root IS the edge-impulse-sdk directory, so the paths carry no
# edge-impulse-sdk/ prefix - adding one returns a 404 page that then fails to
# compile with a misleading error.
for f in dsp/numpy_types.h dsp/returntypes.hpp; do
    out="$tree/edge-impulse-sdk/$f"
    mkdir -p "$(dirname "$out")"
    if ! curl -fsSL "$RAW/$f" -o "$out"; then
        echo "could not fetch $RAW/$f" >&2
        exit 1
    fi
    # A 404 body is a valid file but not a valid header; catch it here rather
    # than as a wall of syntax errors.
    if [ "$(wc -c < "$out")" -lt 1000 ]; then
        echo "$f looks like an error page, not a header" >&2
        exit 1
    fi
done

echo "compiling panns_logmel.cpp with $CXX -std=$STD"
# -I is kept separate from its argument: a bare path is the one form every
# shell between here and the compiler passes through intact.
"$CXX" -c -O2 -std="$STD" -Wall -Wextra \
    -I "$tree" -I "$here" \
    "$here/panns_logmel.cpp" -o "$tree/panns_logmel.o"
echo "OK"
