#!/usr/bin/env python3
"""ブラウザで描画する版（Tkinter不要・標準ライブラリだけで動く）。

認識結果の受け取りと解釈は app.py、図形の状態管理は scene.py、描画だけブラウザのCanvasで行う。
描いた図形に対する「大きくして」「右にずらして」「回して」などの指示にも対応している。

  python3 app_web.py --demo                  # Juliusなしで、描く・大きくする・動かす・回すを実演
  python3 app_web.py                         # 起動中のJulius(モジュールモード)に接続
  python3 app_web.py --script ./asr-raw.sh   # 録音＋認識スクリプト方式（ボタン/スペースキーで録音）

起動すると http://127.0.0.1:8000 をブラウザで開く。
"""
import argparse
import json
import queue
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import app
from scene import Scene

lock = threading.Lock()
busy = threading.Lock()     # 録音スクリプトの二重起動を防ぐ
SCRIPT = None
q = queue.Queue()
scene = Scene()
# ブラウザへ渡す「今の状態」。seq は、変わるたびに増える番号（ブラウザは変化を見つけるために使う）
snapshot = {"seq": 0, "text": "待機中", "shapes": []}

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>音声お絵描き</title>
<style>
  body { margin: 0; font-family: sans-serif; background: #fafafa; }
  #bar { padding: 8px 12px; display: flex; gap: 12px; align-items: center; }
  #status { font-size: 16px; }
  canvas { background: #fff; display: block; margin: 0 auto; border: 1px solid #ddd; max-width: 100%; }
  button { font-size: 16px; padding: 6px 14px; }
</style></head><body>
<div id="bar"><span id="status">待機中</span><button id="rec" hidden>録音して描画（スペースキー）</button></div>
<canvas id="cv" width="900" height="600"></canvas>
<script>
const HAS_SCRIPT = __HAS_SCRIPT__;
const W = 900, H = 600;
const cv = document.getElementById('cv'), g = cv.getContext('2d');
const statusEl = document.getElementById('status');
let shapes = [], lastSeq = -1, anim = null;   // shapes は表示中の値（アニメーションの途中を含む）

function drawGrid() {
  g.strokeStyle = '#eee'; g.lineWidth = 1;
  for (const i of [1, 2]) {
    g.beginPath(); g.moveTo(W * i / 3, 0); g.lineTo(W * i / 3, H); g.stroke();
    g.beginPath(); g.moveTo(0, H * i / 3); g.lineTo(W, H * i / 3); g.stroke();
  }
}
function drawShape(s, selected) {
  const r = Math.max(0, s.r);      // 半径がマイナスだと arc() がエラーになるので、0未満にしない
  const sx = s.sx || 1, sy = s.sy || 1;
  // 中心に移して、画面の横・縦に伸ばして、回転する（伸ばす向きは、回しても画面の横・縦のまま）
  g.save(); g.translate(s.x, s.y); g.scale(sx, sy); g.rotate(s.angle * Math.PI / 180);
  g.beginPath();
  if (s.kind === 'CIRCLE') { g.arc(0, 0, r, 0, 2 * Math.PI); }
  else if (s.kind === 'ELLIPSE') { g.ellipse(0, 0, r, r * 0.6, 0, 0, 2 * Math.PI); }   // 横長（縦は横の0.6倍）
  else if (s.kind === 'SQUARE') { g.rect(-r, -r, 2 * r, 2 * r); }
  else if (s.kind === 'TRIANGLE') {
    g.moveTo(0, -r); g.lineTo(-r, r * 0.8); g.lineTo(r, r * 0.8); g.closePath();
  } else if (s.kind === 'LINE') { g.moveTo(-r, 0); g.lineTo(r, 0); }
  g.restore();   // 経路は伸ばした形のまま残る。線の太さが歪まないよう、変形を戻してから塗る・なぞる
  g.save(); g.fillStyle = s.color; g.strokeStyle = s.color; g.lineJoin = 'round';   // 色などは restore で戻るので、ここで設定する
  // 線は、もともと枠だけ。それ以外は、塗る・塗らないで、描き分ける
  if (s.kind === 'LINE') { g.lineWidth = 8; g.stroke(); }
  else if (s.fill) { g.fill(); }
  else { g.lineWidth = 6; g.stroke(); }
  if (s.color === '#ffffff') {   // 白は、白い背景に溶けて見えなくなるので、細い灰色の縁を付ける
    g.strokeStyle = '#9e9e9e'; g.lineWidth = 1.5; g.stroke();
  }
  g.restore();
  if (selected) {   // 変更の対象（直前に描いた図形）の目印：点線の円
    g.save(); g.strokeStyle = '#888'; g.lineWidth = 1.5; g.setLineDash([6, 6]);
    g.beginPath(); g.arc(s.x, s.y, r * Math.max(sx, sy) * 1.15, 0, 2 * Math.PI); g.stroke(); g.restore();
  }
}
function redraw() {
  g.clearRect(0, 0, W, H); drawGrid();
  shapes.forEach((s, i) => drawShape(s, i === shapes.length - 1));
}
// 新しい状態 to へ、0.45秒かけて滑らかに変える（大きさ・位置・角度）
function startAnim(to) {
  const prev = shapes;
  if (anim) { cancelAnimationFrame(anim); anim = null; }
  if (to.length < prev.length) { shapes = to; redraw(); return; }     // 消したときは、すぐ切り替える
  const from = to.map((t, i) =>
    (i < prev.length && prev[i].kind === t.kind) ? prev[i] : { ...t, r: 0 });   // 新しい図形は、小さい所から大きくなる
  const t0 = performance.now(), DUR = 450;
  const step = () => {
    // 時刻は performance.now() で測る。0〜1の範囲に収める（最初の1コマで、わずかにマイナスになるのを防ぐ）
    const k = Math.min(1, Math.max(0, (performance.now() - t0) / DUR)), e = k * (2 - k);   // 最初は速く、最後はゆっくり
    shapes = to.map((t, i) => {
      const f = from[i];
      const d = ((t.angle - f.angle + 540) % 360) - 180;                // 回転は、近いほうの向きに回す
      return { ...t, x: f.x + (t.x - f.x) * e, y: f.y + (t.y - f.y) * e,
               r: f.r + (t.r - f.r) * e, angle: f.angle + d * e,
               sx: (f.sx || 1) + ((t.sx || 1) - (f.sx || 1)) * e, sy: (f.sy || 1) + ((t.sy || 1) - (f.sy || 1)) * e };
    });
    anim = k < 1 ? requestAnimationFrame(step) : null;   // 先に次のコマを予約する（描画に失敗しても、アニメーションは止まらない）
    redraw();
  };
  anim = requestAnimationFrame(step);
}
async function poll() {
  try {
    const res = await fetch('/snapshot', { cache: 'no-store' });
    const snap = await res.json();
    if (snap.seq !== lastSeq) {
      lastSeq = snap.seq; statusEl.textContent = snap.text; startAnim(snap.shapes);
    }
  } catch (e) { statusEl.textContent = 'サーバーに接続できません'; }
}
function record() { fetch('/record', { method: 'POST' }); }

redraw();
if (HAS_SCRIPT) {
  const b = document.getElementById('rec'); b.hidden = false; b.onclick = record;
  document.addEventListener('keydown', e => { if (e.code === 'Space') { e.preventDefault(); record(); } });
}
setInterval(poll, 200); poll();
</script></body></html>
"""


def pump():
    """app.py の受信・解釈結果（キュー）を、図形の状態に反映して、ブラウザ向けの状態を更新する。"""
    while True:
        item = q.get()
        with lock:
            if item[0] == "status":
                snapshot["text"] = item[1]
            else:
                _, cmd, shown = item
                result = scene.apply(cmd)
                snapshot["text"] = f"認識: {shown} → {result}"
                snapshot["shapes"] = scene.to_list()
            snapshot["seq"] += 1


def start_record():
    if not busy.acquire(blocking=False):
        return

    def work():
        try:
            app.run_script(SCRIPT, q)
        finally:
            busy.release()
    threading.Thread(target=work, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):       # アクセスログは出さない
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            page = PAGE.replace("__HAS_SCRIPT__", "true" if SCRIPT else "false")
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path == "/favicon.ico":          # ブラウザが自動で取りに来るアイコン。無いと404のエラーが出る
            self._send(204, "", "image/x-icon")
        elif self.path.startswith("/snapshot"):
            with lock:
                body = json.dumps(snapshot, ensure_ascii=False)
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path == "/record" and SCRIPT:
            start_record()
            self._send(200, "ok", "text/plain")
        else:
            self._send(404, "not found", "text/plain")


def demo_commands():
    C = app.Command
    return [
        (C("draw", "CIRCLE", "RED", "LARGE", "TOP_RIGHT"), "デモ: 右上に大きい赤い丸"),
        (C("draw", "TRIANGLE", "BLUE", "MEDIUM", "LEFT"), "デモ: 左に青い三角"),
        (C("draw", "SQUARE", "GREEN", "SMALL", "BOTTOM_LEFT"), "デモ: 左下に小さい緑の四角"),
        (C("modify", op="rotate", sign=1, angle=30), "デモ: 30度回して"),
        (C("modify", op="scale", sign=1, amount="MORE"), "デモ: もっと大きくして"),
        (C("modify", op="move", direction="RIGHT", amount="MORE"), "デモ: もっと右にずらして"),
        (C("modify", op="stretch", direction="H"), "デモ: 横に伸ばして"),
        (C("modify", op="stretch", direction="V", amount="MORE"), "デモ: もっと縦に伸ばして"),
        (C("undo"), "デモ: 元に戻して（縦に伸ばす前に戻る）"),
        (C("undo"), "デモ: 元に戻して（横に伸ばす前に戻る）"),
        (C("undo"), "デモ: 元に戻して（右にずらす前に戻る）"),
        (C("undo"), "デモ: 元に戻して（大きくする前に戻る）"),
        (C("draw", "CIRCLE", "BLUE", "LARGE", "CENTER", fill=False), "デモ: 枠だけの大きい青い丸"),
        (C("modify", op="fill", sign=1), "デモ: 塗って"),
        (C("modify", op="fill", sign=-1), "デモ: 枠だけにして"),
    ]


def run_demo(interval):
    """デモの指示を、interval 秒ずつあけて送る（1つずつ変化が見えるように）。"""
    time.sleep(2.0)                      # ブラウザが開いて、読み込まれるのを待つ
    for cmd, shown in demo_commands():
        q.put(("command", cmd, shown))
        time.sleep(interval)


def main():
    global SCRIPT
    ap = argparse.ArgumentParser(description="音声お絵描き（ブラウザ版）")
    ap.add_argument("--script", help="録音＋Julius認識を1回行うスクリプト（例: ./asr-raw.sh）")
    ap.add_argument("--demo", action="store_true",
                    help="Juliusなしで、図形を描いて、回転・拡大・移動まで実演する")
    ap.add_argument("--demo-interval", type=float, default=2.0,
                    help="--demo で、指示を送る間隔（秒）。ゆっくり見たいときは大きくする")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    args = ap.parse_args()
    SCRIPT = args.script

    threading.Thread(target=pump, daemon=True).start()
    if args.demo:
        threading.Thread(target=run_demo, args=(args.demo_interval,), daemon=True).start()
    elif not SCRIPT:
        threading.Thread(target=app.julius_reader, args=(q,), daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)   # 自分のPCからだけ接続できる
    url = f"http://127.0.0.1:{args.port}"
    print(f"ブラウザで {url} を開いてください（Ctrl+Cで終了）", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
