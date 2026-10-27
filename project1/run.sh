#!/bin/bash
# ==============================================================================
# 起動スクリプト (run.sh)
#
# 【使い方】
#   ./run.sh を実行すると、以下を自動で行います：
#   1. test.yomi と test.grammar から Julius 音声認識辞書をコンパイル
#   2. Python 仮想環境 (venv) の準備とパッケージ確認
#   3. FastAPI サーバーの起動＆ブラウザで http://localhost:8000 を開く
# ==============================================================================

cd "$(dirname "$0")" || exit 1

echo "=========================================="
echo " 📝 Julius 文法ファイルをコンパイル中..."
echo "=========================================="
/usr/bin/python3 ./scripts/compile_grammar.py

echo ""
echo "=========================================="
echo " 🚀 仮想環境(venv)の確認および準備中..."
echo "=========================================="

# フォルダを移動しても壊れないよう、venv/bin/python3 を直接使って確認する
if [ ! -x "venv/bin/python3" ]; then
    echo "📦 仮想環境(venv)を作成します..."
    rm -rf venv
    python3 -m venv venv
fi

# 念のため fastapi と uvicorn が入っているかチェックし、なければインストール
if ! ./venv/bin/python3 -c "import fastapi, uvicorn, pydantic" 2>/dev/null; then
    echo "📦 依存パッケージをインストール中..."
    ./venv/bin/python3 -m pip install --quiet fastapi uvicorn pydantic
fi

echo ""
echo "=========================================="
echo " 🎨 FastAPI サーバーを起動します..."
echo " 👉 ブラウザで http://localhost:8000 を開きます"
echo "=========================================="

(sleep 1 && open "http://localhost:8000") &

./venv/bin/python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
