
let drawnShapes = [];
let lastHistorySignature = "";
let mainCanvas;

let isHoldRecording = false;

let isCanvasRevealed = false;

let recordStartPromise = null;

const COLOR_MAP = {
  black: "#1e293b",
  red: "#ef4444",
  blue: "#2563eb",
  green: "#10b981",
  yellow: "#facc15",
  pink: "#f472b6",
  white: "#ffffff"
};

function getCanvasSize() {
  const stage = document.getElementById("canvas-stage");
  if (stage) {
    const rect = stage.getBoundingClientRect();
    return max(300, min(rect.width - 24, rect.height - 24));
  }
  return max(300, min(windowWidth - 440, windowHeight - 120));
}

function setup() {
  let s = getCanvasSize();
  mainCanvas = createCanvas(s, s);
  mainCanvas.parent("canvas-holder");

  fetchCommand();
  setInterval(fetchCommand, 1000);

  setupSpaceKeyPushToTalk();
}

function windowResized() {
  let s = getCanvasSize();
  resizeCanvas(s, s);
}

function draw() {
  background(255); 

  if (!drawnShapes || drawnShapes.length === 0) {
    return;
  }

  for (let cmd of drawnShapes) {
    drawSingleShape(cmd);
  }
}

function drawSingleShape(cmd) {
  if (!cmd || !cmd.shape) return;

  push();

  let x = (cmd.x !== undefined ? cmd.x : 0.5) * width;
  let y = (cmd.y !== undefined ? cmd.y : 0.5) * height;
  translate(x, y);

  if (cmd.rotation) {
    rotate(radians(cmd.rotation));
  }

  let colorCode = COLOR_MAP[cmd.color] || "#1e293b";
  stroke("#1e293b");
  strokeWeight(3);

  if (cmd.filled) {
    fill(colorCode);
  } else {
    noFill();
  }

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
    noFill();
    arc(0, -h * 0.15, w, h * 0.6, 0, PI);
  }

  pop();
}

function renderCommandHistoryList() {
  const listEl = document.getElementById("commandHistoryList");
  const counterEl = document.getElementById("blindCounter");

  if (counterEl) {
    let shapeCount = (drawnShapes || []).filter((c) => c && c.shape).length;
    counterEl.innerText = `現在の図形数: ${shapeCount} 個 ／ コマンド数: ${(drawnShapes || []).length} 手`;
  }

  if (!listEl) return;

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

  listEl.scrollTop = listEl.scrollHeight;
}

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

function setupSpaceKeyPushToTalk() {
  window.addEventListener("keydown", (e) => {
    const modal = document.getElementById("vocabModal");
    const isModalOpen = modal && modal.classList.contains("open");

    if (e.code === "Escape") {
      closeVocabModal();
      return;
    }

    if (!isModalOpen && !e.repeat && e.code === "Backspace") {
      e.preventDefault();
      undoLastShape();
      return;
    }

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
    hideCanvas(); 
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
