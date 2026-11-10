"""描いた図形の状態を持ち、「大きくして」「右にずらして」「回して」などの指示を反映する。

画面（ブラウザ）は、ここで持っている図形の一覧を、そのまま描くだけにする。
変更の対象は「直前に描いた図形」（リストの最後）。
"""
import copy
from dataclasses import asdict, dataclass

import app

W, H = app.W, app.H
STEP = 60                      # 「右に」1回あたりの移動量(px)。「少し」は半分、「もっと」は2倍
SCALE_STEP = 0.25              # 「大きく」1回あたりの拡大率(+25%)。「少し」「もっと」で増減
AMOUNT = {"": 1.0, "LITTLE": 0.5, "MORE": 2.0}
ANGLE = {"": 45, "LITTLE": 15, "MORE": 90}       # 角度を言わなかったときの回転量(度)
STRETCH_STEP = 0.4             # 「横に伸ばして」1回あたりの伸び率(+40%)。「少し」「もっと」で増減
S_MIN, S_MAX = 0.25, 4.0       # 横・縦の倍率の下限・上限
R_MIN, R_MAX = 12, 200         # 図形の半径の下限・上限(px)
HISTORY_MAX = 50               # 「戻して」で戻れる最大の回数
DIRS = {"RIGHT": (1, 0), "LEFT": (-1, 0), "TOP": (0, -1), "BOTTOM": (0, 1),
        "TOP_RIGHT": (0.707, -0.707), "TOP_LEFT": (-0.707, -0.707),
        "BOTTOM_RIGHT": (0.707, 0.707), "BOTTOM_LEFT": (-0.707, 0.707)}
LABEL = {"LITTLE": "少し", "MORE": "もっと", "": ""}


@dataclass
class Shape:
    kind: str          # CIRCLE / ELLIPSE / SQUARE / TRIANGLE / LINE
    color: str         # "#rrggbb"
    x: float           # 中心の座標(px)
    y: float
    r: float           # 半径(px)
    angle: float = 0.0     # 回転角(度)。正の向きが右回り
    fill: bool = True      # False なら、塗らずに枠線だけ
    sx: float = 1.0        # 横方向の倍率（「横に伸ばして」で増える）
    sy: float = 1.0        # 縦方向の倍率（「縦に伸ばして」で増える）


class Scene:
    def __init__(self):
        self.shapes = []
        self.history = []      # 変更する前の状態（図形の一覧のコピー）。いちばん新しいものが最後

    def to_list(self):
        return [{**asdict(s), "x": round(s.x, 1), "y": round(s.y, 1),
                 "r": round(s.r, 1), "angle": round(s.angle, 1),
                 "sx": round(s.sx, 3), "sy": round(s.sy, 3)} for s in self.shapes]

    def apply(self, cmd):
        """指示を反映して、画面に出す短い結果の文を返す。

        図形が実際に変わったときだけ、変わる前の状態を履歴に残す。
        （図形がなくて変更できなかったときや、大きさが上限で変わらなかったときは、残さない）
        """
        if cmd.action == "undo":
            if not self.history:
                return "これ以上、戻れません"
            self.shapes = self.history.pop()
            return "一つ前に戻しました"
        before = copy.deepcopy(self.shapes)
        message = self._apply(cmd)
        if self.shapes != before:
            self.history.append(before)
            del self.history[:-HISTORY_MAX]
        return message

    def _apply(self, cmd):
        if cmd.action == "clear":
            self.shapes.clear()
            return "全部消しました"
        if cmd.action == "draw":
            col, row = app.POSITIONS[cmd.pos]
            self.shapes.append(Shape(cmd.shape, app.COLORS[cmd.color],
                                     W * (col + 0.5) / 3, H * (row + 0.5) / 3,
                                     app.SIZES[cmd.size], fill=cmd.fill))
            return "描きました" if cmd.fill else "枠だけで描きました"
        if not self.shapes:
            return "変更する図形がありません。先に図形を描いてください"
        s = self.shapes[-1]                    # 直前に描いた図形が対象
        m = AMOUNT[cmd.amount]
        if cmd.op == "fill":
            s.fill = cmd.sign > 0
            return "塗りました" if s.fill else "枠だけにしました"
        if cmd.op == "scale":
            f = 1 + SCALE_STEP * m
            s.r = min(R_MAX, max(R_MIN, s.r * f if cmd.sign > 0 else s.r / f))
            return f"{LABEL[cmd.amount]}{'大きく' if cmd.sign > 0 else '小さく'}しました"
        if cmd.op == "stretch":
            f = 1 + STRETCH_STEP * m
            if cmd.direction == "H":
                s.sx = min(S_MAX, max(S_MIN, s.sx * f))
                return f"{LABEL[cmd.amount]}横に伸ばしました"
            s.sy = min(S_MAX, max(S_MIN, s.sy * f))
            return f"{LABEL[cmd.amount]}縦に伸ばしました"
        if cmd.op == "move":
            if cmd.direction == "CENTER":
                s.x, s.y = W / 2, H / 2
                return "真ん中に動かしました"
            dx, dy = DIRS[cmd.direction]
            s.x = min(W, max(0, s.x + dx * STEP * m))
            s.y = min(H, max(0, s.y + dy * STEP * m))
            return f"{LABEL[cmd.amount]}動かしました"
        if cmd.op == "rotate":
            deg = cmd.angle or ANGLE[cmd.amount]
            s.angle = (s.angle + cmd.sign * deg) % 360
            return f"{deg}度、{'右' if cmd.sign > 0 else '左'}に回しました"
        return "解釈できませんでした"
