#!/bin/bash
# ==============================================================================
# 音声録音＆認識スクリプト (asr-recog.sh)
#
# 【役割】
# 1. SoX の rec コマンドでマイクから録音します。
#    （話し始めると録音が開始され、話し終わって0.8秒間静かになると自動で停止します）
# 2. 録音した音声を 16kHz に変換し、Julius で音声認識を実行して結果テキストを出力します。
# ==============================================================================

# プロジェクトのルートディレクトリに移動
cd "$(dirname "$0")/.." || exit 1

# 一時フォルダを作成（スクリプト終了時に自動削除）
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

# 1. 48kHzでマイク録音（VAD：発話開始から無音になるまで録音、最大10秒で安全停止）
# ※ 周囲の雑音で止まらない場合は「2%」の数値を「3%」や「5%」に上げると止まりやすくなります。
rec -q -r 48000 -c 1 -b 16 "$tmpdir/input48.wav" \
    silence 1 0.1 2% 1 0.8 2% pad 0.3 0.3 trim 0 10

# 2. Julius 用に 16kHz・16bit・モノラルに変換
sox "$tmpdir/input48.wav" -r 16000 -c 1 -b 16 "$tmpdir/input.wav" || exit 1

# 3. Julius で音声認識を実行し、認識された文字列だけを出力
echo "$tmpdir/input.wav" > "$tmpdir/list.txt"
julius -C asr/grammar.jconf -filelist "$tmpdir/list.txt" 2>/dev/null | ./scripts/asr-output.pl
