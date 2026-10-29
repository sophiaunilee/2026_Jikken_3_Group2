// ==============================================================================
// p5.js ブラインド音声ドローイングゲーム スクリプト (sketch.js)
//
// 【このファイルの役割】
// 1. 画面いっぱいの正方形キャンバスを作成します（完成ボタンを押すまで黒いカバーで隠します）。
// 2. 入力されたすべてのコマンドに「1., 2., 3...」と番号を付けて右側のリストに表示します。
// 3. スペースキーを押している間だけ録音（Push-to-Talk）し、離すと音声認識を実行します。
// 4. 「完成！絵を見る」ボタンでカバーを外して完成した絵をジャジャーンと表示します。
// ==============================================================================

// これまでに描かれたすべての図形を保持する配列
let drawnShapes = [];
let lastHistorySignature = "";
let mainCanvas;

// スペースキー長押し録音の状態管理フラグ
let isHoldRecording = false;

// キャンバスが公開（完成）されているかどうかのフラグ（初期状態は隠れている）
let isCanvasRevealed = false;

// 録音変数の未設定の確認、修正
let recordStartPromise = null;

// 色の名前とカラーコードの対応表
const COLOR_MAP = {
  black: "#1e293b",
  red: "#ef4444",
  blue: "#2563eb",
  green: "#10b981",
  yellow: "#facc15",
  pink: "#f472b6",
  white: "#ffffff"
};

// 画面サイズに合わせて正方形キャンバスの1辺の長さを計算する関数
function getCanvasSize() {
  const stage = document.getElementById("canvas-stage");
  if (stage) {
    const rect = stage.getBoundingClientRect();
    return max(300, min(rect.width - 24, rect.height - 24));
  }
  return max(300, min(windowWidth - 440, windowHeight - 120));
}

// 初期化処理（ページを開いたときに1回だけ実行される）
function setup() {
  let s = getCanvasSize();
  mainCanvas = createCanvas(s, s);
  mainCanvas.parent("canvas-holder");

  // サーバーから現在の図形リストを取得し、1秒ごとに更新を確認する
  fetchCommand();
  setInterval(fetchCommand, 1000);

  // キーボードのスペースキー長押しイベントを登録
  setupSpaceKeyPushToTalk();
}

// ブラウザのウィンドウサイズが変わったときにキャンバスもリサイズする
function windowResized() {
  let s = getCanvasSize();
  resizeCanvas(s, s);
}

// 毎フレーム実行される描画関数
function draw() {
  background(255); // 背景を白でクリア

  if (!drawnShapes || drawnShapes.length === 0) {
    return;
  }

  for (let cmd of drawnShapes) {
    drawSingleShape(cmd);
  }
}

// 1つの図形データをキャンバスに描く関数
function drawSingleShape(cmd) {
  if (!cmd || !cmd.shape) return;

  push();

  // 1. 中心座標 (x, y) に移動し、回転角度 (rotation) を適用する
  let x = (cmd.x !== undefined ? cmd.x : 0.5) * width;
  let y = (cmd.y !== undefined ? cmd.y : 0.5) * height;
  translate(x, y);

  if (cmd.rotation) {
    rotate(radians(cmd.rotation));
  }

  // 2. 色と塗りつぶし（filled）を設定する
  let colorCode = COLOR_MAP[cmd.color] || "#1e293b";
  stroke("#1e293b");
  strokeWeight(3);

  if (cmd.filled) {
    fill(colorCode);
  } else {
    noFill();
  }

  // 3. サイズと縦横比（縦長・横長・通常）を計算して原点 (0, 0) を中心に図形を描画する
  //    縦長・横長がひと目で分かるように 0.65 : 1.35（約 1 : 2）の比率にする
  let size = width * (cmd.size_ratio || 0.25);
  let w = size;
  let h = size;

  if (cmd.orientation === "vertical") {
    w = size * 0.65;
    h = size * 1.35;
  } else if (cmd.orientation === "horizontal" || cmd.shape === "ellipse") {
    w = size * 1.35;
    h = size * 0.65;
  }

  if (cmd.shape === "circle" || cmd.shape === "ellipse") {
    ellipse(0, 0, w, h);
  } else if (cmd.shape === "rect") {
    rectMode(CENTER);
    rect(0, 0, w, h);
  } else if (cmd.shape === "triangle") {
    triangle(
      0, -h / 2,
      -w / 2, h / 2,
      w / 2, h / 2
    );
  } else if (cmd.shape === "line") {
    if (cmd.orientation === "vertical") {
      line(0, -size / 2, 0, size / 2);
    } else {
      line(-size / 2, 0, size / 2, 0);
    }
  } else if (cmd.shape === "curve") {
    // 曲線（下に凸の弧）：上端が -h*0.15、下端(底)が +h*0.15 になり中心(0,0)に対して上下対称にする
    noFill();
    arc(0, -h * 0.15, w, h * 0.6, 0, PI);
  }

  pop();
}

// ==============================================================================
// 番号付きコマンド履歴リスト (1., 2., 3...) の表示更新
// （新規描画も編集もすべて独立した1つのステップとして順番に表示する）
// ==============================================================================
function renderCommandHistoryList() {
  const listEl = document.getElementById("commandHistoryList");
  const counterEl = document.getElementById("blindCounter");

  if (counterEl) {
    let shapeCount = (drawnShapes || []).filter((c) => c && c.shape).length;
    counterEl.innerText = `現在の図形数: ${shapeCount} 個 ／ コマンド数: ${(drawnShapes || []).length} 手`;
  }

  if (!listEl) return;

  // 前回とコマンド履歴の内容が同じなら、再描画＆自動スクロールをしない（スクロール位置を維持！）
  const currentSignature = JSON.stringify(drawnShapes || []);
  if (currentSignature === lastHistorySignature) {
    return;
  }
  lastHistorySignature = currentSignature;

  if (!drawnShapes || drawnShapes.length === 0) {
    listEl.innerHTML = `
      <div class="history-empty">
        まだ図形がありません。<br>最初の図形（1.）を声で描いてみましょう！
      </div>
    `;
    return;
  }

  listEl.innerHTML = drawnShapes
    .map((cmd, idx) => {
      let num = idx + 1;
      let isEdit = cmd.action === "edit" || !cmd.shape;
      let badge = isEdit
        ? `<span class="history-edit-tag">✏️ ${cmd.target_id || ""}番の図形を編集</span>`
        : "";
      return `
        <div class="history-item">
          <span class="history-num">${num}.</span>
          <div class="history-text">
            「${cmd.text || ""}」
            ${badge}
          </div>
        </div>
      `;
    })
    .join("");

  // 新しいコマンドが追加・変更されたときだけ一番下へスクロール
  listEl.scrollTop = listEl.scrollHeight;
}

// ==============================================================================
// 「完成！絵を見る」ブラインドカバーの開閉処理
// ==============================================================================
function revealCanvas() {
  isCanvasRevealed = true;
  updateBlindCoverUI();
  let statusDiv = document.getElementById("status");
  if (statusDiv) {
    statusDiv.style.color = "#fbbf24";
    statusDiv.innerText = "🎉 ジャジャーン！あなたが声だけで描いた作品です！";
  }
}

function hideCanvas() {
  isCanvasRevealed = false;
  updateBlindCoverUI();
}

function toggleRevealCanvas() {
  if (isCanvasRevealed) {
    hideCanvas();
  } else {
    revealCanvas();
  }
}

function updateBlindCoverUI() {
  const cover = document.getElementById("blind-cover");
  const rehideBtn = document.getElementById("rehide-btn");
  if (!cover) return;

  if (isCanvasRevealed) {
    cover.classList.add("revealed");
    if (rehideBtn) rehideBtn.classList.add("visible");
  } else {
    cover.classList.remove("revealed");
    if (rehideBtn) rehideBtn.classList.remove("visible");
  }
}

// ==============================================================================
// スペースキーを押している間だけ録音する (Push-to-Talk) ＆ キーボードショートカット処理
// - Space 長押し: 録音
// - Backspace: 1つ戻す (Undo)
// - Escape: 単語帳を閉じる
// ==============================================================================
function setupSpaceKeyPushToTalk() {
  window.addEventListener("keydown", (e) => {
    const modal = document.getElementById("vocabModal");
    const isModalOpen = modal && modal.classList.contains("open");

    // 1. Esc キー：単語帳を閉じる
    if (e.code === "Escape") {
      closeVocabModal();
      return;
    }

    // 2. Backspace キー：1つ戻す(Undo)
    if (!isModalOpen && !e.repeat && e.code === "Backspace") {
      e.preventDefault();
      undoLastShape();
      return;
    }

    // 3. Space キー長押し：録音開始
    if (e.code === "Space" && !e.repeat && !isModalOpen) {
      e.preventDefault();
      startHoldRecording();
    }
  });

  window.addEventListener("keyup", (e) => {
    if (e.code === "Space") {
      e.preventDefault();
      stopHoldRecording();
    }
  });
}

async function startHoldRecording() {
  if (isHoldRecording) return;
  isHoldRecording = true;

  let statusDiv = document.getElementById("status");
  let btn = document.getElementById("recBtn");

  statusDiv.style.color = "#f87171";
  statusDiv.innerText = "🔴 録音中... そのまま話し続けてください（話し終わったら離す）";
  if (btn) {
    btn.classList.add("recording");
    btn.innerText = "🔴 録音中... (離すと認識)";
  }

  try {
    await fetch("/api/record/start", { method: "POST" });
  } catch (error) {
    console.error("録音開始エラー:", error);
  }
}

async function stopHoldRecording() {
  if (!isHoldRecording) return;
  isHoldRecording = false;

  let statusDiv = document.getElementById("status");
  let btn = document.getElementById("recBtn");

  statusDiv.style.color = "#93c5fd";
  statusDiv.innerText = "⏳ 音声認識中... しばらくお待ちください";
  if (btn) {
    btn.classList.remove("recording");
    btn.innerText = "🎤 長押し or スペース長押しで録音";
    btn.disabled = true;
  }

  try {
    let response = await fetch("/api/record/stop", { method: "POST" });
    let data = await response.json();
    updateStatusAfterRecognition(data);
  } catch (error) {
    statusDiv.style.color = "#f87171";
    statusDiv.innerText = "❌ サーバー通信エラーが発生しました。";
    console.error(error);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ==============================================================================
// 全単語帳モーダル（ポップアップ）の表示・非表示処理
// ==============================================================================
async function openVocabModal() {
  const modal = document.getElementById("vocabModal");
  const body = document.getElementById("vocabModalBody");
  if (!modal || !body) return;

  modal.classList.add("open");
  body.innerHTML = "読み込み中...";

  try {
    let res = await fetch("/api/vocabulary");
    let data = await res.json();
    let sections = data.sections || [];

    body.innerHTML = sections
      .map((sec) => {
        let chips = sec.words
          .map((w) => `<span class="vocab-chip"><b>${w.word}</b><small>${w.yomi}</small></span>`)
          .join("");
        return `
          <div class="vocab-section">
            <h3>${sec.title} <small style="color:#94a3b8;font-weight:normal;">(% ${sec.code})</small></h3>
            <div class="vocab-chips">${chips}</div>
          </div>
        `;
      })
      .join("");
  } catch (error) {
    body.innerHTML = "❌ 単語帳データの読み込みに失敗しました。";
  }
}

function closeVocabModal() {
  const modal = document.getElementById("vocabModal");
  if (modal) {
    modal.classList.remove("open");
  }
}

// ==============================================================================
// バックエンドとの通信・ボタン操作処理
// ==============================================================================
async function fetchCommand() {
  try {
    let response = await fetch("/api/command");
    if (response.ok) {
      let data = await response.json();
      if (Array.isArray(data.commands)) {
        drawnShapes = data.commands;
        renderCommandHistoryList();
      }
    }
  } catch (error) {
    console.error("図形データの取得に失敗しました:", error);
  }
}

function updateStatusAfterRecognition(data) {
  let statusDiv = document.getElementById("status");

  if (data.understood && data.text) {
    statusDiv.style.color = "#34d399";
    statusDiv.innerText = `✅ 認識結果: 「${data.text}」 を記録しました！`;
    if (Array.isArray(data.commands)) {
      drawnShapes = data.commands;
      renderCommandHistoryList();
    }
  } else {
    statusDiv.style.color = "#f87171";
    let heard = data.text ? `（認識語: 「${data.text}」）` : "";
    statusDiv.innerText = `⚠️ よくわかりませんでした${heard}。「真ん中に大きな円を描いてください」のように再度指示してください。`;
  }
}

async function undoLastShape() {
  let statusDiv = document.getElementById("status");
  let response = await fetch("/api/undo", { method: "POST" });
  if (response.ok) {
    let data = await response.json();
    drawnShapes = data.commands || [];
    renderCommandHistoryList();
    statusDiv.style.color = "#cbd5e1";
    statusDiv.innerText = "↩️ 直前の図形を1つ取り消しました。";
  }
}

async function resetCanvas() {
  let statusDiv = document.getElementById("status");
  let response = await fetch("/api/reset", { method: "POST" });
  if (response.ok) {
    drawnShapes = [];
    renderCommandHistoryList();
    hideCanvas(); // リセットしたら再びキャンバスを黒いカバーで隠す
    statusDiv.style.color = "#cbd5e1";
    statusDiv.innerText = "🗑️ リセットしました！またキャンバスを隠して新しいゲームを始めます。";
  }
}

function saveDrawing() {
  let statusDiv = document.getElementById("status");
  saveCanvas(mainCanvas, "voice-drawing", "jpg");
  statusDiv.style.color = "#34d399";
  statusDiv.innerText = "💾 現在のキャンバスを voice-drawing.jpg として保存しました！";
}
