import subprocess

def get_asr_result():
    """
    ./asr-recog.sh を実行し、
    ターミナルに出力された認識結果（テキスト）を取得します。
    """
    try:
        # ./asr-recog.sh スクリプトの実行
        # capture_output=True: ターミナル出力を変数にキャプチャ
        # text=True: 文字列（String）形式で取得
        result = subprocess.run(
            ["./asr-recog.sh"],
            capture_output=True,
            text=True,
            check=True
        )

        # ターミナルに出力されたテキスト（前後の空白・改行を削除）
        recognized_sentence = result.stdout.strip()
        return recognized_sentence

    except subprocess.CalledProcessError as e:
        print("❌ Shellスクリプトの実行中にエラーが発生しました:")
        print(e.stderr)
        return None
    except FileNotFoundError:
        print("❌ './asr-recog.sh' ファイルが見つかりません。パスを確認してください。")
        return None

if __name__ == "__main__":
    print("🎤 音声認識を開始します。(5秒間お話しください)...")
    
    # 1. スクリプトを実行して認識結果を取得
    text_result = get_asr_result()

    # 2. 結果を出力して活用
    if text_result:
        print(f"\n👉 認識された文: '{text_result}'")
        
        # TODO: ここで取得した text_result を解析し、
        # 図形や色の JSON データを生成して Web (p5.js) に送信します。