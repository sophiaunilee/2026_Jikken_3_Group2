@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ==========================================
echo  📝 Julius 文法ファイルをコンパイル中...
echo ==========================================
python scripts\compile_grammar.py

echo.
echo ==========================================
echo  🚀 仮想環境(venv)の確認および準備中...
echo ==========================================
if not exist "venv\Scripts\python.exe" (
    echo 📦 Windows用の仮想環境(venv)を作成します...
    if exist "venv" rmdir /s /q venv
    python -m venv venv
)

venv\Scripts\python.exe -c "import fastapi, uvicorn, pydantic" 2>nul
if errorlevel 1 (
    echo 📦 依存パッケージをインストール中...
    venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    venv\Scripts\python.exe -m pip install --quiet fastapi uvicorn pydantic
)

echo.
echo ==========================================
echo  🎨 FastAPI サーバーを起動します...
echo  👉 ブラウザで http://localhost:8000 を開きます
echo ==========================================
start "" http://localhost:8000
venv\Scripts\python.exe -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
