#!/bin/bash
# ==============================================================================
# マルチOS対応 起動スクリプト (run.sh) — macOS / Ubuntu (Linux) / WSL 対応
#
# 【使い方】
#   ./run.sh を実行すると、以下を自動で行います：
#   1. test.yomi と test.grammar から Julius 音声認識辞書をコンパイル
#   2. 現在のOS用の Python 仮想環境 (venv) の準備（別OSのvenvが残っていれば自動再作成）
#   3. FastAPI サーバーの起動＆ブラウザで http://localhost:8000 を開く
# ==============================================================================

cd "$(dirname "$0")" || exit 1

# システムの python3 を探す
PYTHON_BIN="$(command -v python3 || command -v python)"
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ エラー: python3 が見つかりません。インストールしてください。"
    exit 1
fi

echo "=========================================="
echo " 📝 Julius 文法ファイルをコンパイル中..."
echo "=========================================="
"$PYTHON_BIN" ./scripts/compile_grammar.py

echo ""
echo "=========================================="
echo " 🚀 仮想環境(venv)の確認および準備中..."
echo "=========================================="

# 既存の venv が別のOS（例: Mac → Ubuntu移動時）で作られたものなら作り直す
if [ ! -x "venv/bin/python3" ] || ! ./venv/bin/python3 -c "import sys" 2>/dev/null; then
    echo "📦 現在のOSに合わせて仮想環境(venv)を作成します..."
    rm -rf venv
    "$PYTHON_BIN" -m venv venv
fi

# 念のため fastapi と uvicorn が入っているかチェックし、なければインストール
if ! ./venv/bin/python3 -c "import fastapi, uvicorn, pydantic" 2>/dev/null; then
    echo "📦 依存パッケージをインストール中..."
    ./venv/bin/python3 -m pip install --quiet --upgrade pip
    ./venv/bin/python3 -m pip install --quiet fastapi uvicorn pydantic
fi

echo ""
echo "=========================================="
echo " 🎨 FastAPI サーバーを起動します..."
echo " 👉 ブラウザで http://localhost:8000 を開きます"
echo "=========================================="

# OSに合わせてブラウザを自動で開く (macOS: open / Ubuntu: xdg-open / WSL: explorer.exe)
(
    sleep 1
    if command -v open >/dev/null 2>&1; then
        open "http://localhost:8000"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:8000" >/dev/null 2>&1
    elif command -v explorer.exe >/dev/null 2>&1; then
        explorer.exe "http://localhost:8000"
    fi
) &

./venv/bin/python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
