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

if [ ! -d "venv" ]; then
    echo "📦 仮想環境(venv)を作成します..."
    python3 -m venv venv
fi

source venv/bin/activate

echo ""
echo "=========================================="
echo " 📦 依存パッケージの確認中..."
echo "=========================================="

pip install --quiet --upgrade pip
pip install --quiet fastapi uvicorn pydantic

echo ""
echo "=========================================="
echo " 🎨 FastAPI サーバーを起動します..."
echo " 👉 ブラウザで http://localhost:8000 を開きます"
echo "=========================================="

(sleep 1 && open "http://localhost:8000") &

python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
