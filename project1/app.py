# ==============================================================================
# 音声認識ドローイング バックエンドサーバー (app.py)
#
# 【このファイルの役割】
# 1. ブラウザに Web 画面 (web/index.html, web/sketch.js) を表示します。
# 2. スペースキーを押している間の録音（Push-to-Talk）およびボタン録音を制御します。
# 3. test.yomi の全単語リストをブラウザの「単語帳モーダル」に渡します。
# 4. 認識された日本語テキストを解析して図形を追加・編集します。
# ==============================================================================

import copy
import os
import random
import signal
import shutil
import subprocess
import tempfile
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# プロジェクトのルートフォルダのパス
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 起動時に test.yomi / test.grammar を自動でコンパイルする
from scripts.compile_grammar import compile_julius_grammar
compile_julius_grammar(os.path.join(BASE_DIR, "asr", "grammar"), "test")

# FastAPI アプリケーションの作成
app = FastAPI()

# ブラウザからの通信（CORS）を許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# 1. グローバル変数（図形履歴リスト・アンドゥ用スナップショット・録音プロセス管理）
# ==============================================================================
commands_history = []
undo_stack = []

# スペースキーを押している間の録音（Push-to-Talk）用の状態変数
active_rec_proc: Optional[subprocess.Popen] = None
active_rec_tmpdir: Optional[str] = None


# ==============================================================================
# 2. 位置・サイズ・色の計算ヘルパー関数
# ==============================================================================
def get_absolute_xy(text: str):
    """キャンバス全体（0.0〜1.0）に対する絶対座標 (x, y) を返す"""
    if "右上" in text:
        return 0.78, 0.22
    elif "左上" in text:
        return 0.22, 0.22
    elif "右下" in text:
        return 0.78, 0.78
    elif "左下" in text:
        return 0.22, 0.78
    elif "少し上" in text:
        return 0.50, 0.36
    elif "少し下" in text:
        return 0.50, 0.64
    elif "少し左" in text:
        return 0.36, 0.50
    elif "少し右" in text:
        return 0.64, 0.50
    elif "真ん中" in text or "中央" in text:
        return 0.50, 0.50
    elif "上" in text:
        return 0.50, 0.22
    elif "下" in text:
        return 0.50, 0.78
    elif "左" in text:
        return 0.22, 0.50
    elif "右" in text:
        return 0.78, 0.50
    return 0.50, 0.50


def get_shape_half_extents(cmd: dict):
    """
    図形の横方向の半径 (rx) と縦方向の半径 (ry) を正確に計算して返す。
    接点をつけて配置するとき（くっつけるとき）に輪郭線がぴったり重なるように使う。
    すべての図形で「縦長 (vertical)」「横長 (horizontal)」「通常 1:1 (normal)」に対応する。
    """
    size = cmd.get("size_ratio", 0.25)
    shape = cmd.get("shape", "circle")
    orientation = cmd.get("orientation", "normal")
    rot = cmd.get("rotation", 0) % 180

    # 90度回転している場合は縦と横の向きが入れ替わる
    if 45 <= rot <= 135:
        if orientation == "vertical":
            orientation = "horizontal"
        elif orientation == "horizontal":
            orientation = "vertical"

    if shape == "line":
        # 縦線は横幅0・縦幅 size、横線は横幅 size・縦幅0
        if orientation == "vertical":
            return 0.0, size / 2.0
        else:
            return size / 2.0, 0.0

    # 縦長・横長・通常(1:1) に応じた横幅(w)と縦幅(h)の計算（すべての図形で共通：1:2 比率でハッキリ差をつける）
    if orientation == "vertical":
        w = size * 0.65
        h = size * 1.35
    elif orientation == "horizontal":
        w = size * 1.35
        h = size * 0.65
    else:
        w = size
        h = size

    if shape == "curve":
        # 曲線は sketch.js で arc(0, -h*0.15, w, h*0.6, 0, PI) として描かれるため、
        # 上端(両端)が y = -h*0.15、下端(底)が y = +h*0.15 の対称なバウンディングボックスになる
        return w / 2.0, h * 0.15
    else:
        return w / 2.0, h / 2.0


def get_relative_xy(text: str, prev_shape: dict, new_shape_dict: dict):
    """
    「その」「あの」「中」「隣」などが使われたとき、
    直前の図形 (prev_shape) と新しい図形 (new_shape_dict) の大きさを元に座標を計算する。
    - 「くっつけて」「接して」「すぐ」「ぴったり」がある場合：輪郭同士がちょうど接する座標にする
    - それ以外の場合：少し余白（隙間）を空けて配置する
    """
    px = prev_shape.get("x", 0.50)
    py = prev_shape.get("y", 0.50)
    prx, pry = get_shape_half_extents(prev_shape)
    nrx, nry = get_shape_half_extents(new_shape_dict)

    is_touching = any(w in text for w in ["くっつけ", "接し", "接する", "ぴったり", "すぐ"])

    # ★ 特別ルール：縦線の「すぐ下」に曲線（口など）を描く場合
    # 曲線の「一番下の底（中点）」が縦線の下端にぴったり接するように配置する（ドラえもん等の口）
    if (
        prev_shape.get("shape") == "line"
        and new_shape_dict.get("shape") == "curve"
        and "下" in text
        and is_touching
    ):
        line_bottom_y = py + pry
        # 曲線の底（中心から +nry の位置）が line_bottom_y に一致するように中心 y を設定
        # （もし曲線の上端を線の下端に合わせるよりも、線の終点が曲線の真ん中に接する方が自然）
        return px, line_bottom_y - nry

    # (A) 「その中」「その内側」の場合 → 直前の図形の内部に配置する
    # ※ 注意：「真ん中」には「中」という文字が含まれるため、先に "真ん中" を除外して判定する！
    text_without_mannaka = text.replace("真ん中", "")
    if "中" in text_without_mannaka or "内側" in text:
        if is_touching:
            dx = max(0.0, prx - nrx)
            dy = max(0.0, pry - nry)
        else:
            dx = prx * 0.45
            dy = pry * 0.45

        if "右上" in text:
            return px + dx * 0.7, py - dy * 0.7
        elif "左上" in text:
            return px - dx * 0.7, py - dy * 0.7
        elif "右下" in text:
            return px + dx * 0.7, py + dy * 0.7
        elif "左下" in text:
            return px - dx * 0.7, py + dy * 0.7
        elif "上" in text:
            return px, py - dy
        elif "下" in text:
            return px, py + dy
        elif "左" in text:
            return px - dx, py
        elif "右" in text:
            return px + dx, py
        else:
            return px, py

    # (B) 「その上」「その下」「その隣」「その右」などの外側配置
    gap = 0.0 if is_touching else 0.06
    dist_x = prx + nrx + gap
    dist_y = pry + nry + gap

    if "右上" in text:
        return min(0.92, px + dist_x * 0.75), max(0.08, py - dist_y * 0.75)
    elif "左上" in text:
        return max(0.08, px - dist_x * 0.75), max(0.08, py - dist_y * 0.75)
    elif "右下" in text:
        return min(0.92, px + dist_x * 0.75), min(0.92, py + dist_y * 0.75)
    elif "左下" in text:
        return max(0.08, px - dist_x * 0.75), min(0.92, py + dist_y * 0.75)
    elif "上" in text:
        return px, max(0.08, py - dist_y)
    elif "下" in text:
        return px, min(0.92, py + dist_y)
    elif "左" in text:
        return max(0.08, px - dist_x), py
    elif "右" in text or "隣" in text:
        return min(0.92, px + dist_x), py

    return px, py


def get_actual_shapes(history: list):
    """履歴リストから『編集ステップ（action == "edit"）』を除いた、実際の図形リストだけを返す"""
    return [item for item in history if item.get("action", "draw") == "draw" and item.get("shape")]


def extract_shape_number(text: str, history: list):
    """
    テキストの中に「一番」「二番」「1番」「2番」などの番号指定があれば、
    そのステップ番号 (1始まり) に対応する図形データ（dict）を history から探して返す。
    番号指定がなければ直前に描かれた図形を返す。
    """
    actual_shapes = get_actual_shapes(history)
    if not actual_shapes:
        return None, None

    number_words = [
        (["十番", "10番", "１０番"], 10),
        (["九番", "9番", "９番"], 9),
        (["八番", "8番", "８番"], 8),
        (["七番", "7番", "７番"], 7),
        (["六番", "6番", "６番"], 6),
        (["五番", "5番", "５番"], 5),
        (["四番", "4番", "４番"], 4),
        (["三番", "3番", "３番"], 3),
        (["二番", "2番", "２番"], 2),
        (["一番", "1番", "１番", "最初"], 1),
    ]

    for keywords, num in number_words:
        if any(k in text for k in keywords):
            # 1. まずステップ番号 (1., 2., 3...) と一致する図形を探す
            if 1 <= num <= len(history):
                candidate = history[num - 1]
                if candidate.get("action", "draw") == "draw" and candidate.get("shape"):
                    return candidate, num
                # もし指定された番号が編集ステップだった場合は、その編集対象だった図形を返す
                target_id = candidate.get("target_id")
                if target_id:
                    for item in history:
                        if item.get("id") == target_id and item.get("shape"):
                            return item, num
            # 2. 見つからなければ N 番目に描かれた図形を返す
            if 1 <= num <= len(actual_shapes):
                return actual_shapes[num - 1], num
            else:
                return actual_shapes[-1], len(history)

    return actual_shapes[-1], None


def extract_color(text: str):
    """テキストに色が含まれていれば (色名, True) を返し、なければ (None, False) を返す"""
    if "赤" in text:
        return "red", True
    elif "青" in text:
        return "blue", True
    elif "緑" in text:
        return "green", True
    elif "黄色" in text:
        return "yellow", True
    elif "ピンク" in text:
        return "pink", True
    elif "白" in text:
        return "white", True
    elif "黒" in text:
        return "black", True
    return None, False


# ==============================================================================
# 3. 音声認識テキストを解析して「新規追加」または「直前の図形の編集」を行う関数
# ==============================================================================
def process_voice_text(text: str, history: list):
    if not text or not text.strip():
        return False

    actual_shapes = get_actual_shapes(history)

    # (1) 図形の種類（shape）が含まれているか調べる
    shape = None
    is_clone_shape = False
    if "楕円" in text:
        shape = "ellipse"
    elif "丸" in text or "円" in text:
        shape = "circle"
    elif "四角" in text or "正方形" in text:
        shape = "rect"
    elif "三角" in text:
        shape = "triangle"
    elif "カーブ" in text or "曲線" in text:
        shape = "curve"
    elif "直線" in text or "縦線" in text or "横線" in text or "線" in text:
        shape = "line"
    elif ("図形" in text or "もの" in text or "やつ" in text or "もう一つ" in text) and actual_shapes:
        shape = actual_shapes[-1].get("shape", "circle")
        is_clone_shape = True

    # ==================================================
    # ケースA：図形名がない場合 → 指定番号（または「それを」／直前）の図形を動かす・回転する
    # ==================================================
    if shape is None:
        if not actual_shapes:
            return False

        # 「二番を九十度回転して」なら2番の図形、「それを〜」や番号なしなら直前の図形を対象にする
        target_cmd, target_num = extract_shape_number(text, history)
        if target_cmd is None:
            return False

        # 変更前のスナップショットを保存してから編集を適用する
        snapshot = copy.deepcopy(history)
        modified = False

        # ① 回転命令（30度・45度・90度・180度に対応）
        if "回転" in text or "回して" in text or "度" in text:
            angle = 90
            if "三十度" in text or "30" in text:
                angle = 30
            elif "四十五度" in text or "45" in text:
                angle = 45
            elif "百八十度" in text or "180" in text:
                angle = 180
            elif "九十度" in text or "90" in text:
                angle = 90

            if "左" in text:
                angle = -angle

            target_cmd["rotation"] = (target_cmd.get("rotation", 0) + angle) % 360
            modified = True

        # ② 移動命令（「横長」の「横」と混同しないよう、縦長・横長を除いたテキストで判定する）
        text_for_loc = text.replace("縦長", "").replace("横長", "")
        if "動かして" in text or "移動" in text or any(w in text_for_loc for w in ["上", "下", "左", "右", "真ん中", "中央", "隣", "内側"]):
            if "少し上" in text:
                target_cmd["y"] = max(0.08, round(target_cmd["y"] - 0.12, 3))
            elif "少し下" in text:
                target_cmd["y"] = min(0.92, round(target_cmd["y"] + 0.12, 3))
            elif "少し左" in text:
                target_cmd["x"] = max(0.08, round(target_cmd["x"] - 0.12, 3))
            elif "少し右" in text:
                target_cmd["x"] = min(0.92, round(target_cmd["x"] + 0.12, 3))
            elif ("前の" in text or "その" in text or "あの" in text or "この" in text or "くっつけ" in text or "接し" in text or "すぐ" in text) and len(actual_shapes) >= 2:
                ref_base = actual_shapes[-2] if target_num is None else actual_shapes[-1]
                nx, ny = get_relative_xy(text, ref_base, target_cmd)
                target_cmd["x"], target_cmd["y"] = round(nx, 3), round(ny, 3)
            elif not ("回転" in text or "回して" in text):
                nx, ny = get_absolute_xy(text)
                target_cmd["x"], target_cmd["y"] = round(nx, 3), round(ny, 3)
            modified = True

        # ③ サイズ変更命令（「めっちゃ大きくして」「小さくして」など）
        is_extreme = any(w in text for w in ["めっちゃ", "すごく", "とても", "かなり", "超"])
        if "大き" in text:
            scale = 1.75 if is_extreme else 1.35
            target_cmd["size_ratio"] = min(0.85, round(target_cmd.get("size_ratio", 0.25) * scale, 3))
            modified = True
        elif "小さ" in text:
            scale = 0.45 if is_extreme else 0.70
            target_cmd["size_ratio"] = max(0.04, round(target_cmd.get("size_ratio", 0.25) * scale, 3))
            modified = True

        # ④ 縦長・横長の変更命令（「縦長にして」「横長にして」など）
        if "縦長" in text or "縦に長" in text or "縦の" in text:
            target_cmd["orientation"] = "vertical"
            modified = True
        elif "横長" in text or "横に長" in text or "横の" in text:
            target_cmd["orientation"] = "horizontal"
            modified = True

        # ⑤ 色・塗りつぶし変更命令
        col, has_col = extract_color(text)
        if has_col:
            target_cmd["color"] = col
            target_cmd["filled"] = True
            modified = True
        elif "塗って" in text or "塗りつぶし" in text or "黒塗り" in text:
            target_cmd["filled"] = True
            modified = True

        if modified:
            # 元の図形の下に入れるのではなく、独立した1つのコマンドステップとして履歴に追加する！
            undo_stack.append(snapshot)
            edit_step = {
                "id": len(history) + 1,
                "action": "edit",
                "target_id": target_cmd.get("id"),
                "text": text
            }
            history.append(edit_step)

        return modified

    # ==================================================
    # ケースB：図形名がある場合 → 新しい図形を追加する
    #          （「その〜」「前の〜」「一番の〜」「内側」「隣」「くっつけて」等の明示的な参照がある時だけ相対配置！）
    # ==================================================
    ref_shape, ref_num = extract_shape_number(text, history)

    # ※ 「真ん中」の「中」や「横長」の「横」で誤って前の図形を参照しないように除外してから判定する！
    text_clean_for_ref = text.replace("真ん中", "").replace("縦長", "").replace("横長", "").replace("横線", "")
    has_reference = (ref_num is not None) or any(
        w in text_clean_for_ref
        for w in ["前の", "その", "それの", "あの", "この", "内側", "隣", "くっつけ", "接し", "接する", "ぴったり", "すぐ"]
    )
    is_same = ("同じ" in text) or is_clone_shape
    is_inside = ("内側" in text_clean_for_ref) or ("中" in text_clean_for_ref)

    # (2) サイズ（size_ratio）を決定する
    #     「めっちゃ」「すごく」「とても」「かなり」「超」がある場合は極端なサイズにする
    is_extreme = any(w in text for w in ["めっちゃ", "すごく", "とても", "かなり", "超"])
    prev_size = ref_shape.get("size_ratio", 0.25) if ref_shape else 0.25

    if is_same:
        size_ratio = prev_size
    elif "より少し小さ" in text:
        size_ratio = round(prev_size * random.uniform(0.70, 0.85), 3)
    elif "より少し大き" in text:
        size_ratio = min(0.75, round(prev_size * random.uniform(1.15, 1.30), 3))
    elif "半分くらい" in text:
        size_ratio = round(prev_size * 0.50, 3)
    elif "大き" in text:
        if is_extreme:
            size_ratio = round(random.uniform(0.55, 0.72), 3)
        else:
            size_ratio = round(random.uniform(0.34, 0.46), 3)
    elif "小さ" in text:
        if is_extreme:
            size_ratio = round(random.uniform(0.04, 0.07), 3)
        elif ref_shape and is_inside:
            max_small = max(0.08, prev_size * 0.42)
            size_ratio = round(random.uniform(max_small * 0.75, max_small), 3)
        else:
            size_ratio = round(random.uniform(0.10, 0.16), 3)
    else:
        if ref_shape and is_inside:
            size_ratio = round(prev_size * 0.55, 3)
        else:
            size_ratio = round(random.uniform(0.20, 0.28), 3)

    # (3) 色と塗りつぶし（filled）を決定する
    color, has_color = extract_color(text)
    if not has_color:
        if is_same and ref_shape is not None:
            color = ref_shape.get("color", "black")
            filled = ref_shape.get("filled", False)
        else:
            color = "black"
            filled = False
    else:
        filled = True

    if "塗って" in text or "塗りつぶし" in text or "黒塗り" in text:
        filled = True

    # (4) すべての図形の向き（縦長・横長・通常）と回転角度
    if "縦線" in text or "縦の" in text or "縦長" in text or "縦に長" in text or "縦" in text:
        orientation = "vertical"
    elif "横線" in text or "横の" in text or "横長" in text or "横に長" in text or "横" in text:
        orientation = "horizontal"
    elif is_same and ref_shape is not None:
        orientation = ref_shape.get("orientation", "normal")
    elif shape in ("ellipse", "line"):
        # 楕円と直線は、特に指定がなければ横向きをデフォルトにする
        orientation = "horizontal"
    else:
        # 丸・四角・三角・カーブは、特に指定がなければ 1:1 の通常比率 ("normal") にする
        orientation = "normal"

    rotation = ref_shape.get("rotation", 0) if (is_same and ref_shape is not None) else 0

    new_command = {
        "id": len(history) + 1,
        "action": "draw",
        "shape": shape,
        "x": 0.50,
        "y": 0.50,
        "color": color,
        "filled": filled,
        "size_ratio": size_ratio,
        "orientation": orientation,
        "rotation": rotation,
        "text": text
    }

    # (5) 位置（x, y）を決定する
    if has_reference and ref_shape is not None:
        x, y = get_relative_xy(text, ref_shape, new_command)
    else:
        x, y = get_absolute_xy(text)

    new_command["x"] = round(x, 3)
    new_command["y"] = round(y, 3)

    # アンドゥ用に現在の状態を保存してから新しい図形ステップを追加する
    undo_stack.append(copy.deepcopy(history))
    history.append(new_command)
    return True


# ==============================================================================
# 4. 録音＆Julius音声認識の制御関数（スペースキー長押し録音 ＆ 自動停止録音）
# ==============================================================================
def run_julius_on_wav(wav48_path: str, tmpdir: str) -> Optional[str]:
    """録音された 48kHz の wav を音量正規化（gain -n -3）＆ 16kHz 変換して Julius で認識する"""
    wav16_path = os.path.join(tmpdir, "input.wav")
    list_path = os.path.join(tmpdir, "list.txt")

    # 録音前後に 0.25秒 の無音パッドを入れ、gain -n -3 でマイク音量を最適化する
    subprocess.run(
        ["sox", wav48_path, "-r", "16000", "-c", "1", "-b", "16", wav16_path, "gain", "-n", "-3", "pad", "0.25", "0.25"],
        cwd=BASE_DIR,
        check=True
    )
    with open(list_path, "w", encoding="utf-8") as f:
        f.write(wav16_path + "\n")

    j_res = subprocess.run(
        ["julius", "-C", "asr/grammar.jconf", "-filelist", list_path],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    # sentence1: の行から認識結果を取り出す
    for line in j_res.stdout.splitlines():
        if line.startswith("sentence1:"):
            text = line.replace("sentence1:", "").replace("silB", "").replace("silE", "").replace(" ", "").strip()
            return text
    return None


def get_asr_result():
    """従来の ./scripts/asr-recog.sh を実行して音声認識結果を取得"""
    try:
        script_path = os.path.join(BASE_DIR, "scripts", "asr-recog.sh")
        result = subprocess.run(
            ["/bin/bash", script_path],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"❌ 音声認識の実行エラー: {e}")
        return None


# ==============================================================================
# 5. test.yomi から全単語リストを読み取って単語帳データを返す関数
# ==============================================================================
CATEGORY_LABELS = {
    "REF": "指示語・番号参照（その・一番の・二番の）",
    "TARGET": "操作対象の番号指定（一番を・二番を）",
    "REL": "相対位置（中・隣など）",
    "TOUCH": "接点・密着（ぴったりくっつける）",
    "LOC": "位置・方向",
    "DEGREE": "強調・程度（めっちゃ・すごく）",
    "SIZE": "サイズ・大きさ比較",
    "ASPECT": "縦長・横長・太さ",
    "COLOR": "色・塗り方",
    "SHAPE": "図形・対象",
    "ANGLE": "回転の角度・方向",
    "P_NI": "助詞（に・へ）",
    "P_NO": "助詞（の）",
    "P_WO": "助詞（を）",
    "VERB": "描画の動詞",
    "EDIT_VERB": "移動・回転・変更の動詞",
    "PLZ": "丁寧語",
}


def load_vocabulary_book():
    """asr/grammar/test.yomi を読み込んでカテゴリごとの全単語リストを返す"""
    yomi_path = os.path.join(BASE_DIR, "asr", "grammar", "test.yomi")
    sections = []
    current = None

    if not os.path.exists(yomi_path):
        return sections

    with open(yomi_path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            if raw.startswith("%"):
                cat_code = raw[1:].strip()
                if cat_code in ("NS_B", "NS_E"):
                    current = None
                    continue
                current = {
                    "code": cat_code,
                    "title": CATEGORY_LABELS.get(cat_code, cat_code),
                    "words": []
                }
                sections.append(current)
            elif current is not None:
                parts = raw.split()
                if len(parts) >= 2:
                    current["words"].append({"word": parts[0], "yomi": parts[1]})
    return sections


class TextCommandRequest(BaseModel):
    text: str


# ==============================================================================
# 6. Web 画面と API のルーティング設定
# ==============================================================================
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(BASE_DIR, "web", "index.html"))


@app.get("/sketch.js")
def serve_sketch():
    return FileResponse(os.path.join(BASE_DIR, "web", "sketch.js"))


@app.get("/api/vocabulary")
def get_vocabulary():
    """test.yomi に登録されているすべての単語をカテゴリ別に返す"""
    return {"sections": load_vocabulary_book()}


@app.post("/api/record/start")
def start_recording():
    """スペースキーを押した瞬間にマイク録音を開始する"""
    global active_rec_proc, active_rec_tmpdir

    # すでに録音中ならそのまま返す
    if active_rec_proc is not None and active_rec_proc.poll() is None:
        return {"status": "already_recording"}

    active_rec_tmpdir = tempfile.mkdtemp()
    wav48_path = os.path.join(active_rec_tmpdir, "input48.wav")

    print("🎙️ [Push-to-Talk] 録音開始 (スペースキー押下中)...")
    active_rec_proc = subprocess.Popen(
        ["rec", "-q", "-r", "48000", "-c", "1", "-b", "16", wav48_path],
        cwd=BASE_DIR
    )
    return {"status": "started"}


@app.post("/api/record/stop")
def stop_recording():
    """スペースキーを離した瞬間に録音を停止し、Julius で音声認識を実行する"""
    global active_rec_proc, active_rec_tmpdir

    if active_rec_proc is None:
        return register_command(None)

    tmpdir = active_rec_tmpdir
    proc = active_rec_proc
    active_rec_proc = None
    active_rec_tmpdir = None

    try:
        # SoX (rec) に SIGINT を送って WAV ヘッダを正常に書き込んで終了させる
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=1.0)

        print("⏹️ [Push-to-Talk] 録音停止 → Julius で認識中...")
        wav48_path = os.path.join(tmpdir, "input48.wav")
        text_result = None
        if os.path.exists(wav48_path) and os.path.getsize(wav48_path) > 1000:
            text_result = run_julius_on_wav(wav48_path, tmpdir)
        return register_command(text_result)
    except Exception as e:
        print(f"❌ 録音停止・認識エラー: {e}")
        return register_command(None)
    finally:
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/api/recognize")
def recognize_speech():
    """ボタンクリック時（発話終了まで自動録音）"""
    print("🎤 音声認識を開始します... (話し終わるまで録音中)")
    text_result = get_asr_result()
    return register_command(text_result)


@app.post("/api/text_command")
def handle_text_command(req: TextCommandRequest):
    return register_command(req.text)


def register_command(text_result: Optional[str]):
    global commands_history

    if text_result:
        print(f"👉 認識テキスト: '{text_result}'")
        ok = process_voice_text(text_result, commands_history)

        if ok:
            print(f"🎨 現在の図形リスト (合計 {len(commands_history)} 個): {commands_history[-1]}")
            return {
                "understood": True,
                "text": text_result,
                "commands": commands_history
            }
        else:
            print("⚠️ 命令を解釈できませんでした。")
            return {
                "understood": False,
                "text": text_result,
                "commands": commands_history
            }
    else:
        print("⚠️ 音声テキストが取得できませんでした。")
        return {
            "understood": False,
            "text": "",
            "commands": commands_history
        }


@app.get("/api/command")
def get_current_commands():
    return {"commands": commands_history}


@app.post("/api/undo")
def undo_command():
    """直前の1ステップ（新規描画または編集）を取り消して1つ前の状態に戻す"""
    global commands_history, undo_stack
    if undo_stack:
        commands_history = undo_stack.pop()
    elif commands_history:
        commands_history.pop()
    return {"commands": commands_history}


@app.post("/api/reset")
def reset_commands():
    global commands_history, undo_stack
    commands_history = []
    undo_stack = []
    print("🗑️ キャンバスをリセットしました。")
    return {"commands": commands_history}


# ==============================================================================
# 7. サーバーの起動
# ==============================================================================
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
