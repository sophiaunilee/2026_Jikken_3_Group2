#!/bin/bash

cd "$(dirname "$0")/.." || exit 1

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

rec -q -r 48000 -c 1 -b 16 "$tmpdir/input48.wav" \
    silence 1 0.1 2% 1 0.8 2% pad 0.3 0.3 trim 0 10

sox "$tmpdir/input48.wav" -r 16000 -c 1 -b 16 "$tmpdir/input.wav" || exit 1

echo "$tmpdir/input.wav" > "$tmpdir/list.txt"
julius -C asr/grammar.jconf -filelist "$tmpdir/list.txt" 2>/dev/null | ./scripts/asr-output.pl
