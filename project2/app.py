#!/usr/bin/env python3
"""Julius(モジュールモード)からTCPで認識結果を受け取り、Tkinterで図形を描く。

使い方:
  1. julius -C julius.jconf        （Juliusを先に起動。クライアントの接続を待つ）
  2. python app.py                  （このアプリを起動）
  ※ マイクなしで試すときは mock_julius.py を代わりに起動する
"""
import math
import argparse
import queue
import re
import shlex
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

try:
    import tkinter as tk
except ImportError:       # Tkが無い環境でも、app_web.py から解釈部分を使えるようにする
    tk = None

HOST, PORT = "127.0.0.1", 10500
CM_THRESHOLD = 0.3          # 信頼度の平均がこれ未満の認識結果は無視する

# ---- 語彙（draw.voca の出力文字列と対応させる） -----------------------------
COLORS = {"RED": "#e53935", "BLUE": "#1e88e5", "YELLOW": "#fdd835",
          "GREEN": "#43a047", "BLACK": "#212121", "WHITE": "#ffffff"}
SIZES = {"SMALL": 30, "MEDIUM": 55, "LARGE": 85}       # 半径(px)
SHAPES = {"CIRCLE", "ELLIPSE", "SQUARE", "TRIANGLE", "LINE"}
# 3x3の格子上の位置 (列, 行) 0=左/上, 1=中央, 2=右/下
POSITIONS = {"TOP_LEFT": (0, 0), "TOP": (1, 0), "TOP_RIGHT": (2, 0),
             "LEFT": (0, 1), "CENTER": (1, 1), "RIGHT": (2, 1),
             "BOTTOM_LEFT": (0, 2), "BOTTOM": (1, 2), "BOTTOM_RIGHT": (2, 2)}
IGNORED = {"[s]", "[/s]", "silB", "silE", "WO", "NI", "DRAW",
           "を", "に", "描いて", "書いて"}
SENTENCE_MARKS = ("[s]", "[/s]", "silB", "silE")

# 日本語表記の単語 → 上のキー。voca の出力を日本語にした場合はここで変換する
WORD_ALIASES = {
    "丸": "CIRCLE", "四角": "SQUARE", "三角": "TRIANGLE",
    "線": "LINE",
    "楕円形": "ELLIPSE",     # 「円」「楕円」は「線」と音が近く聞き間違えやすいので、使わない
    "赤い": "RED", "青い": "BLUE", "黄色い": "YELLOW", "緑の": "GREEN",
    "黒い": "BLACK", "真っ白な": "WHITE",   # 「白い」は「黒い」と音が近く聞き間違えやすいので、使わない
    "大きい": "LARGE", "大きな": "LARGE", "小さい": "SMALL", "小さな": "SMALL",
    "中くらいの": "MEDIUM",
    "右上": "TOP_RIGHT", "左上": "TOP_LEFT", "右下": "BOTTOM_RIGHT",
    "左下": "BOTTOM_LEFT", "真ん中": "CENTER", "中央": "CENTER",
    "右": "RIGHT", "左": "LEFT", "上": "TOP", "下": "BOTTOM",
    "消して": "CLEAR", "全部消して": "CLEAR",
    # 変更の指示
    "大きく": "BIGGER", "大きくして": "BIGGER", "小さく": "SMALLER", "小さくして": "SMALLER",
    "動かして": "MOVE", "ずらして": "MOVE", "回転して": "ROTATE", "回して": "ROTATE",
    "横に": "AXIS_H", "縦に": "AXIS_V", "伸ばして": "STRETCH",
    "少し": "LITTLE", "ちょっと": "LITTLE", "もっと": "MORE",
    # 塗りつぶし（描くときの「枠だけの」「塗らない」と、変更の「塗って」「枠だけにして」）
    "枠だけの": "OUTLINE", "塗らない": "OUTLINE",
    "塗って": "FILLED", "枠だけにして": "OUTLINED",
    "白抜きにして": "OUTLINED", "透明にして": "OUTLINED",      # 「枠だけにして」の言い換え（聞き分けやすい）
    # 一つ前に戻す。短い「戻して」は「回して」「もっと下」と音が近く、聞き間違えやすいので使わない。
    # 「消して」と音が近い「取り消して」も使わない
    "元に戻して": "UNDO", "前に戻して": "UNDO",
}   # 「15度」のような角度は、parse_words の中で数字を読み取る
DEBUG_RAW = True     # True なら Julius から届いた生のメッセージをターミナルに表示する

W, H = 900, 600


@dataclass
class Command:
    action: str                 # "draw"（描く）/ "clear"（全消去）/ "modify"（直前の図形を変更）/ "undo"（一つ前に戻す）
    shape: str = "CIRCLE"
    color: str = "BLACK"
    size: str = "MEDIUM"
    pos: str = "CENTER"
    fill: bool = True           # draw: False なら、塗らずに枠線だけで描く
    # --- modify のときだけ使う ---
    op: str = ""                # "scale"（大きさ）/ "move"（移動）/ "rotate"（回転）/ "fill"（塗る・塗らない）/ "stretch"（横・縦に伸ばす）
    amount: str = ""            # "" = ふつう / "LITTLE" = 少し / "MORE" = もっと
    sign: int = 1               # scale: +1 大きく, -1 小さく / rotate: +1 右回り, -1 左回り
    direction: str = ""         # move: POSITIONS のキー（RIGHT, TOP_LEFT, CENTER など）
    angle: int = 0              # rotate: 度数（0 なら amount から決める）


def parse_modify(words):
    """「少し大きく」「右にずらして」「45度回して」など、直前の図形への変更指示を解釈する。"""
    amount = "MORE" if "MORE" in words else "LITTLE" if "LITTLE" in words else ""
    direction = next((w for w in words if w in POSITIONS), "")
    angle = 0
    for w in words:
        m = re.fullmatch(r"(\d+)度", w)
        if m:
            angle = int(m.group(1))
    if "FILLED" in words or "OUTLINED" in words:
        return Command("modify", op="fill", sign=1 if "FILLED" in words else -1)
    if "STRETCH" in words:
        axis = "V" if "AXIS_V" in words else "H"        # direction に、横=H / 縦=V を入れる
        return Command("modify", op="stretch", direction=axis, amount=amount)
    if "BIGGER" in words or "SMALLER" in words:
        return Command("modify", op="scale", sign=1 if "BIGGER" in words else -1, amount=amount)
    if "ROTATE" in words:
        sign = -1 if "LEFT" in direction else 1          # 左なら左回り。それ以外は右回り
        return Command("modify", op="rotate", sign=sign, amount=amount, angle=angle)
    if direction:
        return Command("modify", op="move", direction=direction, amount=amount)
    return None


def parse_words(words):
    """認識された単語（出力文字列）のリスト → Command。解釈できなければ None。"""
    words = [WORD_ALIASES.get(w, w) for w in words]
    if "CLEAR" in words:
        return Command("clear")
    if "UNDO" in words:
        return Command("undo")
    if not any(w in SHAPES for w in words):
        return parse_modify(words)          # 図形がなければ、直前の図形への変更指示
    cmd = Command("draw")
    found_shape = False
    for w in words:
        if w in IGNORED:
            continue
        if w in COLORS:
            cmd.color = w
        elif w in SIZES:
            cmd.size = w
        elif w in SHAPES:
            cmd.shape, found_shape = w, True
        elif w in POSITIONS:
            cmd.pos = w
    cmd.fill = "OUTLINE" not in words           # 「枠だけの」「塗らない」があれば、塗らずに描く
    return cmd if found_shape else None


# ---- Julius との通信 ----------------------------------------------------------
def parse_recogout(text):
    """<RECOGOUT> の最上位仮説から (単語リスト, 平均信頼度) を取り出す。"""
    m = re.search(r"<SHYPO.*?</SHYPO>", text, re.S)
    if not m:
        return None, 0.0
    words, cms = [], []
    for tag in re.findall(r"<WHYPO\s[^>]*>", m.group(0)):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
        word = attrs.get("WORD", "")
        words.append(word)
        if word not in SENTENCE_MARKS and "CM" in attrs:
            cms.append(float(attrs["CM"]))
    return words, (sum(cms) / len(cms) if cms else 1.0)


def julius_reader(q):
    """別スレッドでJuliusに接続し、認識結果をキューに流す（切れたら再接続）。"""
    while True:
        try:
            with socket.create_connection((HOST, PORT), timeout=5) as s:
                s.settimeout(None)
                q.put(("status", f"Julius に接続しました ({HOST}:{PORT})"))
                buf = b""
                while True:
                    data = s.recv(4096)
                    if not data:
                        break
                    buf += data.replace(b"\r\n", b"\n")
                    # Juliusのメッセージは「\n.\n」で区切られる
                    while b"\n.\n" in buf:
                        msg, buf = buf.split(b"\n.\n", 1)
                        handle_message(decode_text(msg), q)
        except OSError:
            q.put(("status", "Julius に接続できません。再接続を試みます…"))
        time.sleep(2)


def decode_text(raw):
    """Juliusの出力は辞書と同じ文字コード。UTF-8でだめならEUC-JP、Shift_JISを試す。"""
    for enc in ("utf-8", "euc_jp", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def handle_message(text, q):
    if DEBUG_RAW:
        print(text, flush=True)
    if "<RECOGFAIL" in text:
        q.put(("status", "認識に失敗しました"))
    elif "<RECOGOUT" in text:
        words, cm = parse_recogout(text)
        if words:
            emit_result(words, cm, q)


def emit_result(words, cm, q):
    """認識結果（単語リストと信頼度）を解釈して、描画命令か状態表示をキューに流す。"""
    shown = " ".join(w for w in words if w not in SENTENCE_MARKS)
    if cm < CM_THRESHOLD:
        q.put(("status", f"信頼度が低いので無視: {shown} (CM={cm:.2f})"))
        return
    cmd = parse_words(words)
    if cmd is None:
        q.put(("status", f"解釈できませんでした: {shown}"))
    else:
        q.put(("command", cmd, shown))


# ---- スクリプト方式（録音→Julius(ファイル入力)を1回実行して、標準出力を読む） ----
def parse_julius_stdout(text):
    """ファイル入力モードのJulius出力から sentence1（単語列）と cmscore1（信頼度）を探す。

    文法認識では wseq1 は単語IDの数字になるので、単語が並ぶ sentence1 を使う。
    """
    words, fallback, cms = None, None, []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("sentence1:"):
            words = line.split()[1:]
        elif line.startswith("wseq1:"):
            fallback = line.split()[1:]
        elif line.startswith("cmscore1:"):
            cms = [float(x) for x in line.split()[1:]]
    if words is None:
        words = fallback
    if words is None:
        return None, 0.0
    inner = cms[1:-1] if len(cms) >= 3 else cms      # 文頭・文末の無音を除く
    return words, (sum(inner) / len(inner) if inner else 1.0)


def run_script(command, q):
    """録音と認識を行うシェルスクリプトを1回実行し、結果をキューに流す。"""
    q.put(("status", "録音中… 話してください"))
    try:
        r = subprocess.run(shlex.split(command), capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        q.put(("status", f"スクリプトを実行できませんでした: {e}"))
        return
    text = decode_text(r.stdout + b"\n" + r.stderr)
    if DEBUG_RAW:
        print(text, flush=True)
    words, cm = parse_julius_stdout(text)
    if not words:
        q.put(("status", "認識結果が見つかりませんでした"))
    else:
        emit_result(words, cm, q)


# ---- 描画 ----------------------------------------------------------------------
class App:
    def __init__(self, root, q, script=None):
        self.q = q
        self.script = script
        self.busy = False
        root.title("音声お絵描き")
        self.canvas = tk.Canvas(root, width=W, height=H, bg="white")
        self.canvas.pack()
        self.label = tk.Label(root, text="待機中", anchor="w", font=("", 12))
        self.label.pack(fill="x")
        for i in (1, 2):   # 3x3 の目安線
            self.canvas.create_line(W * i / 3, 0, W * i / 3, H, fill="#eeeeee")
            self.canvas.create_line(0, H * i / 3, W, H * i / 3, fill="#eeeeee")
        if script:
            tk.Button(root, text="録音して描画（スペースキーでも可）",
                      command=self.record).pack(fill="x")
            root.bind("<space>", lambda e: self.record())
        root.after(50, self.poll)
        self.root = root

    def record(self):
        """スクリプトを別スレッドで1回実行する（実行中の二重起動は無視）。"""
        if self.busy:
            return
        self.busy = True

        def work():
            try:
                run_script(self.script, self.q)
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        """キューを定期的に確認（Tkinterの操作は必ずメインスレッドで行う）。"""
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "status":
                    self.label.config(text=item[1])
                else:
                    _, cmd, shown = item
                    self.label.config(text=f"認識: {shown}")
                    if DEBUG_RAW:
                        print("描画:", cmd, flush=True)
                    try:
                        self.execute(cmd)
                    except Exception as e:      # 描画に失敗したら画面とターミナルに出す
                        import traceback
                        traceback.print_exc()
                        self.label.config(text=f"描画エラー: {e}")
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def execute(self, cmd):
        if cmd.action in ("modify", "undo"):
            self.label.config(text="Tk版は図形の変更（大きさ・移動・回転）と「元に戻して」に未対応です。app_web.py を使ってください")
            return
        if cmd.action == "clear":
            self.canvas.delete("shape")
            return
        col, row = POSITIONS[cmd.pos]
        cx, cy = W * (col + 0.5) / 3, H * (row + 0.5) / 3
        r, color = SIZES[cmd.size], COLORS[cmd.color]
        c = self.canvas
        if cmd.shape == "CIRCLE":
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="", tags="shape")
        elif cmd.shape == "ELLIPSE":
            c.create_oval(cx - r, cy - r * 0.6, cx + r, cy + r * 0.6, fill=color, outline="", tags="shape")
        elif cmd.shape == "SQUARE":
            c.create_rectangle(cx - r, cy - r, cx + r, cy + r, fill=color, outline="", tags="shape")
        elif cmd.shape == "TRIANGLE":
            c.create_polygon(cx, cy - r, cx - r, cy + r * 0.8, cx + r, cy + r * 0.8,
                             fill=color, outline="", tags="shape")
        elif cmd.shape == "LINE":
            c.create_line(cx - r, cy, cx + r, cy, fill=color, width=8, tags="shape")


def main():
    ap = argparse.ArgumentParser(description="音声お絵描き")
    ap.add_argument("--script", help="録音＋Julius認識を1回行うスクリプト（例: ./asr-raw.sh）。"
                                     "指定しなければ、起動中のJulius(モジュールモード)に接続する")
    ap.add_argument("--demo", action="store_true",
                    help="Juliusに接続せず、起動時に図形を3つ描く（画面表示の確認用）")
    args = ap.parse_args()
    q = queue.Queue()
    if args.demo:
        q.put(("command", Command("draw", "CIRCLE", "RED", "LARGE", "TOP_RIGHT"), "デモ: 右上に大きい赤い丸"))
        q.put(("command", Command("draw", "TRIANGLE", "BLUE", "MEDIUM", "LEFT"), "デモ: 左に青い三角"))
        q.put(("command", Command("draw", "SQUARE", "GREEN", "SMALL", "BOTTOM_LEFT"), "デモ: 左下に小さい緑の四角"))
    elif not args.script:
        threading.Thread(target=julius_reader, args=(q,), daemon=True).start()
    root = tk.Tk()
    App(root, q, args.script)
    # Macでは、ウィンドウが他のアプリの後ろに開くことがあるので、前面に出す
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.mainloop()


if __name__ == "__main__":
    main()
