/**
 * Review queue screen.
 *
 * Loads pending review tasks, renders the selected inspection image with its
 * candidate defect boxes, and submits reviewer decisions.
 * Request/response shapes follow docs/api.md (API contract v0.1).
 */

// Single switch between local mock data and the live API.
const CONFIG = { useMock: true, apiBase: "http://localhost:8000" };

const MOCK_TASKS_URL = "mock/review_tasks.json";
const MOCK_IMAGE_URL = "mock/sample.png";

const STORAGE_KEYS = { reviewer: "reviewQueue.reviewer", doneToday: "reviewQueue.doneToday" };
const NOTICE_MS = 4000;

const BOX_COLOR = "#f97316";
const MISSED_BOX_COLOR = "#a855f7";
const MISSED_DEFECT_TYPE = "foreign_object"; // only defect type in v0.1
const MIN_BOX_SRC_PX = 3; // ignore accidental clicks that produce a near-empty box
const BOX_LINE_PX = 2; // on-screen line width, independent of image scale

const state = {
  tasks: [],          // pending review tasks, in queue order
  selectedIndex: -1,
  image: null,        // HTMLImageElement for the selected inspection
  imageFailed: false, // the selected inspection's image could not be loaded
  scale: 1,           // screen px per source image px
  submitting: false,  // blocks double submits (e.g. a held-down key)
  drawMode: false,    // "add missed defect" mode
  dragStart: null,    // {x, y} in source px while the pointer is down
  draft: null,        // [x, y, w, h] in source px, the box being drawn
};

const els = {
  list: document.getElementById("task-list"),
  empty: document.getElementById("empty-message"),
  canvas: document.getElementById("viewer"),
  canvasWrap: document.querySelector(".canvas-wrap"),
  meta: document.getElementById("viewer-meta"),
  imageError: document.getElementById("image-error"),
  statPending: document.getElementById("stat-pending"),
  statDoneToday: document.getElementById("stat-done-today"),
  modeBadge: document.getElementById("mode-badge"),
  drawHint: document.getElementById("draw-hint"),
  confirmButton: document.getElementById("btn-confirm"),
  confirmLabel: document.getElementById("label-confirm"),
  rejectButton: document.getElementById("btn-reject"),
  missedButton: document.getElementById("btn-missed"),
  reviewer: document.getElementById("reviewer"),
  notice: document.getElementById("notice"),
  buttons: [
    document.getElementById("btn-confirm"),
    document.getElementById("btn-reject"),
    document.getElementById("btn-missed"),
  ],
};

// ---------------------------------------------------------------------------
// Data access
// ---------------------------------------------------------------------------

async function fetchPendingTasks() {
  const url = CONFIG.useMock
    ? MOCK_TASKS_URL
    : `${CONFIG.apiBase}/review-tasks?status=pending&limit=50`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`GET review tasks failed: HTTP ${res.status}`);
  }
  const tasks = await res.json();
  return tasks.filter((t) => t.status === "pending");
}

/** Mock mode keeps the contract's image_url untouched and swaps the source here. */
function imageUrlFor(task) {
  return CONFIG.useMock ? MOCK_IMAGE_URL : `${CONFIG.apiBase}${task.inspection.image_url}`;
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    img.src = url;
  });
}

/**
 * Sends one decision. Body shape follows the contract:
 *   { decision: "confirm" | "reject" | "add_missed", reviewer, [defect_type, bbox] }
 * Resolves to "ok" or "conflict" (409: already decided elsewhere); throws otherwise.
 */
async function submitDecision(task, body) {
  const path = `/review-tasks/${task.id}/decision`;
  if (CONFIG.useMock) {
    console.log(`POST ${path}`, JSON.stringify(body));
    return "ok";
  }
  const res = await fetch(`${CONFIG.apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 409) return "conflict";
  if (!res.ok) {
    throw new Error(`POST ${path} failed: HTTP ${res.status}`);
  }
  return "ok";
}

// ---------------------------------------------------------------------------
// Local persistence (per browser; storage may be unavailable)
// ---------------------------------------------------------------------------

function readStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Non-critical: the counter and reviewer name just won't survive a reload.
  }
}

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Decisions made in this browser today; resets when the local date changes. */
function readDoneToday() {
  try {
    const saved = JSON.parse(readStorage(STORAGE_KEYS.doneToday));
    return saved && saved.date === todayKey() ? saved.count : 0;
  } catch {
    return 0;
  }
}

function incrementDoneToday() {
  const count = readDoneToday() + 1;
  writeStorage(STORAGE_KEYS.doneToday, JSON.stringify({ date: todayKey(), count }));
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/** Local wall-clock time as HH:MM:SS. */
function formatTime(iso) {
  const d = new Date(iso);
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

function selectedTask() {
  return state.tasks[state.selectedIndex] ?? null;
}

function renderStats() {
  els.statPending.textContent = String(state.tasks.length);
  els.statDoneToday.textContent = String(readDoneToday());
}

let noticeTimer = null;

function showNotice(message) {
  els.notice.textContent = message;
  els.notice.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { els.notice.hidden = true; }, NOTICE_MS);
}

function renderList() {
  els.list.replaceChildren(
    ...state.tasks.map((task, index) => {
      const li = document.createElement("li");
      li.className = "task-item" + (index === state.selectedIndex ? " selected" : "");
      li.dataset.index = String(index);

      const badge = document.createElement("span");
      badge.className = `badge ${task.reason}`; // class name mirrors the API value
      badge.textContent = task.reason;

      const lot = document.createElement("span");
      lot.className = "lot";
      lot.textContent = task.inspection.lot_code;

      const time = document.createElement("span");
      time.className = "time";
      time.textContent = `#${task.id} · ${formatTime(task.created_at)}`;

      li.append(badge, lot, time);
      return li;
    }),
  );

  const hasTasks = state.tasks.length > 0;
  els.empty.hidden = hasTasks;
  renderDecisionButtons();

  const selected = els.list.querySelector(".selected");
  if (selected) selected.scrollIntoView({ block: "nearest" });
}

/**
 * "confirm" means different things depending on the task (docs/api.md):
 * with candidates it confirms the defects; without candidates (audit sample)
 * it records that the OK verdict was correct. The label follows that meaning.
 */
const CONFIRM_LABELS = {
  defects: { text: "결함 확정", title: "후보 결함이 실제 결함임을 확정합니다" },
  noCandidates: { text: "OK 판정 맞음", title: "결함이 없다는 OK 판정이 맞음을 기록합니다" },
};

function hasCandidates(task) {
  return task.defects.length > 0;
}

/**
 * Decisions need a visible image: a reviewer must not confirm or reject
 * evidence they could not see.
 */
function renderDecisionButtons() {
  const task = selectedTask();
  const blocked = !task || state.imageFailed;
  els.buttons.forEach((btn) => { btn.disabled = blocked; });
  if (!task) return;

  const label = hasCandidates(task) ? CONFIRM_LABELS.defects : CONFIRM_LABELS.noCandidates;
  els.confirmLabel.textContent = label.text;
  els.confirmButton.title = label.title;
  // Red reads as "defect"; an OK-verdict confirmation gets its own color.
  els.confirmButton.classList.toggle("ok-verdict", !hasCandidates(task));
  // Nothing to reject when the engine proposed no candidates.
  if (!hasCandidates(task)) els.rejectButton.disabled = true;
}

function renderImageError() {
  els.imageError.hidden = !state.imageFailed;
}

function renderMeta(task) {
  if (!task) {
    els.meta.textContent = "";
    return;
  }
  const { inspection, defects } = task;
  els.meta.textContent =
    `Inspection #${inspection.id} · Lot ${inspection.lot_code} · ` +
    `판정 ${inspection.verdict} · 후보 ${defects.length}개 · ` +
    `촬영 ${formatTime(inspection.captured_at)}`;
}

/**
 * Draws the image and boxes in source-pixel coordinates.
 * The canvas transform alone maps source px to screen px, so bbox values from
 * the API are used as-is and never rescaled by hand.
 */
function drawViewer() {
  const task = selectedTask();
  const ctx = els.canvas.getContext("2d");

  if (!task || !state.image) {
    els.canvas.width = 0;
    els.canvas.height = 0;
    // Clear the CSS size too, or the empty canvas keeps its old footprint.
    els.canvas.style.width = "";
    els.canvas.style.height = "";
    return;
  }

  const { width: srcW, height: srcH } = task.inspection;
  const availW = els.canvasWrap.clientWidth;
  const availH = els.canvasWrap.clientHeight;
  state.scale = Math.min(availW / srcW, availH / srcH);

  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.floor(srcW * state.scale);
  const cssH = Math.floor(srcH * state.scale);
  els.canvas.style.width = `${cssW}px`;
  els.canvas.style.height = `${cssH}px`;
  els.canvas.width = Math.floor(cssW * dpr);
  els.canvas.height = Math.floor(cssH * dpr);

  ctx.setTransform(state.scale * dpr, 0, 0, state.scale * dpr, 0, 0);
  ctx.drawImage(state.image, 0, 0, srcW, srcH);

  for (const defect of task.defects) {
    // confidence is null for defects a reviewer added by hand.
    const label = defect.confidence == null ? "human" : defect.confidence.toFixed(2);
    drawBox(ctx, defect.bbox, BOX_COLOR, label);
  }
  if (state.draft) {
    drawBox(ctx, state.draft, MISSED_BOX_COLOR, "missed");
  }
}

function drawBox(ctx, [x, y, w, h], color, label) {
  const unit = 1 / state.scale; // one screen pixel, in source pixels

  ctx.lineWidth = BOX_LINE_PX * unit;
  ctx.strokeStyle = color;
  ctx.strokeRect(x, y, w, h);

  if (!label) return;
  ctx.font = `${12 * unit}px ui-monospace, monospace`;
  const padding = 3 * unit;
  const textW = ctx.measureText(label).width;
  const labelH = 16 * unit;
  const labelY = y - labelH >= 0 ? y - labelH : y + h; // keep label inside the image
  ctx.fillStyle = color;
  ctx.fillRect(x, labelY, textW + padding * 2, labelH);
  ctx.fillStyle = "#fff";
  ctx.textBaseline = "middle";
  ctx.fillText(label, x + padding, labelY + labelH / 2);
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

async function selectTask(index) {
  if (state.tasks.length === 0) {
    exitDrawMode();
    state.selectedIndex = -1;
    state.image = null;
    state.imageFailed = false;
    renderImageError();
    renderList();
    renderMeta(null);
    drawViewer();
    return;
  }

  exitDrawMode(); // a half-drawn box never carries over to another task
  state.selectedIndex = Math.max(0, Math.min(index, state.tasks.length - 1));
  const task = selectedTask();
  // Drop the previous image so its pixels are never drawn under this task's boxes.
  state.image = null;
  state.imageFailed = false;
  renderImageError();
  renderList();
  renderMeta(task);

  let image = null;
  try {
    image = await loadImage(imageUrlFor(task));
  } catch (err) {
    console.error(err);
  }
  // Ignore a stale result if the reviewer moved on while the load was in flight.
  if (selectedTask() !== task) return;
  state.image = image;
  state.imageFailed = image === null;
  renderImageError();
  renderDecisionButtons();
  drawViewer();
}

function moveSelection(delta) {
  if (state.tasks.length === 0) return;
  selectTask(state.selectedIndex + delta);
}

// ---------------------------------------------------------------------------
// Missed-defect drawing
// ---------------------------------------------------------------------------

function enterDrawMode() {
  if (!selectedTask() || !state.image) return;
  state.drawMode = true;
  state.draft = null;
  els.canvas.classList.add("drawing");
  els.missedButton.classList.add("active");
  els.drawHint.hidden = false;
}

function exitDrawMode() {
  state.drawMode = false;
  state.dragStart = null;
  state.draft = null;
  els.canvas.classList.remove("drawing");
  els.missedButton.classList.remove("active");
  els.drawHint.hidden = true;
}

/**
 * Converts a pointer position to source-image pixels.
 * Screen px / scale = source px; the result is clamped to the image bounds.
 */
function toSourcePoint(event) {
  const { width: srcW, height: srcH } = selectedTask().inspection;
  const rect = els.canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) / state.scale;
  const y = (event.clientY - rect.top) / state.scale;
  return {
    x: Math.min(Math.max(x, 0), srcW),
    y: Math.min(Math.max(y, 0), srcH),
  };
}

/** Builds [x, y, w, h] from two corners, whichever direction the drag went. */
function boxFromCorners(a, b) {
  return [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(a.x - b.x), Math.abs(a.y - b.y)];
}

function onPointerDown(event) {
  if (!state.drawMode || event.button !== 0) return;
  els.canvas.setPointerCapture(event.pointerId); // keep receiving moves outside the canvas
  state.dragStart = toSourcePoint(event);
  state.draft = null;
}

function onPointerMove(event) {
  if (!state.drawMode || !state.dragStart) return;
  state.draft = boxFromCorners(state.dragStart, toSourcePoint(event));
  drawViewer();
}

function onPointerUp() {
  state.dragStart = null;
}

function submitMissedDefect() {
  const draft = state.draft;
  if (!draft || draft[2] < MIN_BOX_SRC_PX || draft[3] < MIN_BOX_SRC_PX) {
    showNotice("이미지 위에서 드래그로 박스를 먼저 그리세요.");
    return;
  }
  decide("add_missed", {
    defect_type: MISSED_DEFECT_TYPE,
    bbox: draft.map((v) => Math.round(v)),
  });
}

// ---------------------------------------------------------------------------
// Decisions
// ---------------------------------------------------------------------------

/** Drops the task from the queue and selects the one that moved into its slot. */
function removeTask(task) {
  const index = state.tasks.indexOf(task);
  if (index === -1) return;
  state.tasks.splice(index, 1);
  renderStats();
  selectTask(Math.min(index, state.tasks.length - 1));
}

async function decide(decision, extra = {}) {
  const task = selectedTask();
  if (!task || state.submitting) return;
  if (!state.image) {
    // Covers keyboard shortcuts too; the buttons are already disabled on failure.
    if (state.imageFailed) showNotice("이미지가 없어 결정할 수 없습니다.");
    return;
  }
  if (decision === "reject" && !hasCandidates(task)) {
    showNotice("반려할 후보 결함이 없습니다.");
    return;
  }

  const reviewer = els.reviewer.value.trim();
  if (!reviewer) {
    showNotice("검수자 이름을 먼저 입력하세요.");
    els.reviewer.focus();
    return;
  }

  state.submitting = true;
  try {
    const result = await submitDecision(task, { decision, reviewer, ...extra });
    if (result === "conflict") {
      showNotice(`작업 #${task.id}: 이미 결정된 작업이라 목록에서 제외합니다.`);
    } else {
      incrementDoneToday();
    }
    removeTask(task);
  } catch (err) {
    console.error(err);
    showNotice("전송에 실패했습니다. 잠시 후 다시 시도하세요.");
  } finally {
    state.submitting = false;
  }
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

function isTypingTarget(target) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

/**
 * Uses event.code (physical key) rather than event.key so the shortcuts keep
 * working when the keyboard is in Korean input mode (KeyA would report "ㅁ").
 */
function onKeyDown(event) {
  if (isTypingTarget(event.target)) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return; // keep browser shortcuts (e.g. Ctrl+R)

  // While drawing, only Enter (submit) and Escape (cancel) are active.
  if (state.drawMode) {
    if (event.code === "Enter" || event.code === "NumpadEnter") {
      event.preventDefault();
      if (!event.repeat) submitMissedDefect();
    } else if (event.code === "Escape") {
      exitDrawMode();
      drawViewer();
    }
    return;
  }

  switch (event.code) {
    case "ArrowUp":
      event.preventDefault();
      moveSelection(-1);
      break;
    case "ArrowDown":
      event.preventDefault();
      moveSelection(1);
      break;
    case "KeyA":
      // preventDefault: if focus jumps to the name field, the letter must not be typed into it.
      event.preventDefault();
      if (!event.repeat) decide("confirm");
      break;
    case "KeyR":
      event.preventDefault();
      if (!event.repeat) decide("reject");
      break;
    case "KeyM":
      event.preventDefault();
      enterDrawMode();
      break;
    default:
      break;
  }
}

function onListClick(event) {
  const item = event.target.closest(".task-item");
  if (item) selectTask(Number(item.dataset.index));
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

async function init() {
  els.modeBadge.textContent = CONFIG.useMock ? "MOCK" : "";
  els.reviewer.value = readStorage(STORAGE_KEYS.reviewer) ?? "";
  els.reviewer.addEventListener("input", () => {
    writeStorage(STORAGE_KEYS.reviewer, els.reviewer.value.trim());
  });
  // Enter in the name field hands focus back to the queue so shortcuts work again.
  els.reviewer.addEventListener("keydown", (event) => {
    if (event.key === "Enter") els.reviewer.blur();
  });
  document.getElementById("btn-confirm").addEventListener("click", () => decide("confirm"));
  document.getElementById("btn-reject").addEventListener("click", () => decide("reject"));
  els.missedButton.addEventListener("click", (event) => {
    event.currentTarget.blur(); // so Enter submits the box instead of re-clicking the button
    enterDrawMode();
  });
  els.canvas.addEventListener("pointerdown", onPointerDown);
  els.canvas.addEventListener("pointermove", onPointerMove);
  els.canvas.addEventListener("pointerup", onPointerUp);
  els.canvas.addEventListener("pointercancel", onPointerUp);
  els.list.addEventListener("click", onListClick);
  document.addEventListener("keydown", onKeyDown);
  // Redraw whenever the viewer area changes size (window resize, layout shifts).
  new ResizeObserver(() => drawViewer()).observe(els.canvasWrap);

  try {
    state.tasks = await fetchPendingTasks();
  } catch (err) {
    console.error(err);
    state.tasks = [];
  }
  renderStats();
  await selectTask(0);
}

init();