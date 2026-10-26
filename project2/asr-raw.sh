#!/bin/bash
# 5秒録音 → 16kHzに変換 → Juliusで認識。結果はそのまま標準出力に出す。
# （授業のスクリプトから「| ./asr-output.pl」を外したもの。app_web.py / app.py がこの出力を読む）

cd "$(dirname "$0")"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

# 48kHzで録音
rec -q -r 48000 -c 1 -b 16 "$tmpdir/input48.wav" trim 0 5

# 16kHzに変換
sox "$tmpdir/input48.wav" -r 16000 -c 1 -b 16 "$tmpdir/input.wav" || exit 1

# Juliusで音声認識（ファイル入力）
echo "$tmpdir/input.wav" > "$tmpdir/list.txt"
julius -C asr/draw.jconf -filelist "$tmpdir/list.txt"
