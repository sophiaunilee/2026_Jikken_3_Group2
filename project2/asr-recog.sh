#!/bin/bash

cd "$(dirname "$0")"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

# 48kHzで録音
rec -q -r 48000 -c 1 -b 16 "$tmpdir/input48.wav" trim 0 5

# 16kHzに変換
sox "$tmpdir/input48.wav" -r 16000 -c 1 -b 16 "$tmpdir/input.wav" || exit 1

# cp "$tmpdir/input.wav" /tmp/asr-test.wav
# play /tmp/asr-test.wav

# Juliusで音声認識
echo "$tmpdir/input.wav" > "$tmpdir/list.txt"
julius -C asr/grammar.jconf -filelist "$tmpdir/list.txt" | ./asr-output.pl
