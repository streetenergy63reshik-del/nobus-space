const unavailable = "Nobus Space временно недоступен";
const state = document.querySelector("#state");
const taskPanel = document.querySelector("#task-panel");
const tasks = document.querySelector("#tasks");
const empty = document.querySelector("#empty");
const taskCount = document.querySelector("#task-count");
const newTask = document.querySelector("#new-task");
const composerSheet = document.querySelector("#composer-sheet");
const closeComposer = document.querySelector("#close-composer");
const createTask = document.querySelector("#create-task");
const displayTitle = document.querySelector("#display-title");
const instruction = document.querySelector("#instruction");
const characterCount = document.querySelector("#character-count");
const submitTask = document.querySelector("#submit-task");
const detailSheet = document.querySelector("#detail-sheet");
const closeDetail = document.querySelector("#close-detail");
const detailReference = document.querySelector("#detail-reference");
const detailTitle = document.querySelector("#detail-title");
const detail = document.querySelector("#detail");

let bearer = null;
let pendingMutation = null;
let pollTimer = null;
let selectedTaskId = null;
let requestGeneration = 0;

const eventLabels = {
  started: "Codex начал работу",
  progress: "Задача выполняется",
  waiting_input: "Нужно ваше действие",
  artifact_ready: "Артефакт подготовлен",
  result_ready: "Результат проверен",
  failed: "Выполнение остановлено",
  stopped: "Задача остановлена",
};

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function closeSheet(sheet) {
  if (sheet.open) sheet.close();
}

function openComposer() {
  if (!composerSheet.open) composerSheet.showModal();
  setTimeout(() => displayTitle.focus(), 0);
}

function openDetail(task) {
  detailReference.textContent = `Задача #${shortTaskId(task.task_id)}`;
  detailTitle.textContent = task.description;
  detail.replaceChildren(loadingBlock());
  if (!detailSheet.open) detailSheet.showModal();
}

function showUnavailable() {
  requestGeneration += 1;
  stopPolling();
  selectedTaskId = null;
  bearer = null;
  closeSheet(composerSheet);
  closeSheet(detailSheet);
  tasks.replaceChildren();
  taskPanel.hidden = true;
  newTask.hidden = true;
  state.hidden = false;
  state.textContent = unavailable;
}

function selectionIsCurrent(taskId, generation) {
  return selectedTaskId === taskId && requestGeneration === generation;
}

function shortTaskId(taskId) {
  return String(taskId).split("-", 1)[0].toUpperCase();
}

function formatTime(value) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusClass(status) {
  if (status === "ready") return "status-answered";
  if (status === "failed") return "status-failed";
  if (status === "attention") return "status-failed";
  return "status-running";
}

function element(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function loadingBlock() {
  return element("p", "detail-loading", "Загружаем задачу…");
}

async function api(path) {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${bearer}` },
    cache: "no-store",
  });
  if (!response.ok) throw new Error("request_failed");
  return response.json();
}

async function downloadArtifact(taskId, result, artifact, generation) {
  try {
    const path =
      `/api/tasks/${encodeURIComponent(taskId)}/artifacts/` +
      `${encodeURIComponent(artifact.artifact_id)}?revision=` +
      encodeURIComponent(result.result_revision);
    const response = await fetch(path, {
      headers: { Authorization: `Bearer ${bearer}` },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("artifact_unavailable");
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength !== artifact.size) throw new Error("artifact_mismatch");
    const digest = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      (value) => value.toString(16).padStart(2, "0"),
    ).join("");
    if (`sha256:${digest}` !== artifact.content_digest) {
      throw new Error("artifact_mismatch");
    }
    if (!selectionIsCurrent(taskId, generation)) return;
    const objectUrl = URL.createObjectURL(new Blob([bytes], { type: artifact.media_type }));
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = artifact.filename;
    anchor.rel = "noopener";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  } catch {
    if (!selectionIsCurrent(taskId, generation)) return;
    state.hidden = false;
    state.textContent = "Артефакт временно недоступен.";
  }
}

function detailMeta(task) {
  const grid = element("div", "detail-meta-grid");
  const status = element("div", `detail-meta ${statusClass(task.status)}`);
  status.append(element("span", "", "Статус"), element("strong", "status-pill", task.status_label));
  const updated = element("div", "detail-meta");
  updated.append(element("span", "", "Обновлена"), element("strong", "", formatTime(task.updated_at)));
  grid.append(status, updated);
  return grid;
}

function eventTimeline(events) {
  const section = document.createDocumentFragment();
  section.append(element("h3", "", "Ход задачи"));
  const list = element("ol", "timeline");
  for (const event of events) {
    const item = element("li", "timeline-item");
    const dot = element("span", "timeline-dot");
    dot.setAttribute("aria-hidden", "true");
    const copy = document.createElement("div");
    copy.append(
      element("p", "", eventLabels[event.kind] || "Статус обновлён"),
      element("time", "", formatTime(event.emitted_at)),
    );
    item.append(dot, copy);
    list.append(item);
  }
  section.append(list);
  return section;
}

async function showTask(taskId, initialTask = null) {
  stopPolling();
  selectedTaskId = taskId;
  const generation = ++requestGeneration;
  if (initialTask) openDetail(initialTask);
  try {
    const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    if (!selectionIsCurrent(taskId, generation)) return;
    const eventResult = await api(`/api/tasks/${encodeURIComponent(taskId)}/events?limit=20`);
    if (!selectionIsCurrent(taskId, generation)) return;

    detailReference.textContent = `Задача #${shortTaskId(task.task_id)}`;
    detailTitle.textContent = task.description;
    detail.replaceChildren();
    detail.append(detailMeta(task));
    if (task.instruction_available) {
      const instructionCard = element("section", "instruction-card");
      instructionCard.append(
        element("h3", "", "Содержание задачи"),
        element("p", "", task.instruction),
      );
      detail.append(instructionCard);
    } else {
      detail.append(element("p", "legacy-note", "Исходный текст недоступен для задач, созданных до обновления карточки."));
    }
    if (!task.description_available) {
      detail.append(element("p", "legacy-note", "Описание этой задачи создано до обновления интерфейса. Для идентификации используется устойчивый номер."));
    }
    if (eventResult.events.length > 0) detail.append(eventTimeline(eventResult.events));

    if (task.has_verified_answer) {
      const result = await api(`/api/tasks/${encodeURIComponent(taskId)}/result?revision=${encodeURIComponent(task.result_revision)}`);
      if (!selectionIsCurrent(taskId, generation)) return;
      const resultCard = element("section", "result-card");
      resultCard.append(element("h3", "", "Проверенный ответ"), element("pre", "", result.answer));
      detail.append(resultCard);
      if (result.artifact) {
        const artifactCard = element("section", "artifact-card");
        const artifactCopy = document.createElement("div");
        artifactCopy.append(
          element("strong", "", result.artifact.filename),
          element("p", "", `${result.artifact.size} байт · проверен SHA-256`),
        );
        const download = element("button", "artifact-button", "Скачать");
        download.type = "button";
        download.addEventListener("click", () => downloadArtifact(taskId, result, result.artifact, generation));
        artifactCard.append(artifactCopy, download);
        detail.append(artifactCard);
      }
    }
    if (!detailSheet.open) detailSheet.showModal();
    if (!task.terminal && selectionIsCurrent(taskId, generation)) {
      pollTimer = setTimeout(() => showTask(taskId), 3_000);
    }
  } catch {
    if (selectionIsCurrent(taskId, generation)) showUnavailable();
  }
}

function taskCard(task) {
  const item = element("li", `task-item ${statusClass(task.status)}`);
  const button = element("button", "task-button");
  button.type = "button";
  button.setAttribute("aria-label", `${task.description}. ${task.status_label}`);
  const copy = element("div", "task-copy");
  copy.append(element("p", "task-description", task.description));
  const meta = element("div", "task-meta");
  meta.append(
    element("span", "status-pill", task.status_label),
    element("span", "", `#${shortTaskId(task.task_id)}`),
    element("span", "", formatTime(task.updated_at)),
  );
  copy.append(meta);
  button.append(copy, element("span", "task-chevron", "›"));
  button.addEventListener("click", () => showTask(task.task_id, task));
  item.append(button);
  return item;
}

async function loadTasks() {
  const result = await api("/api/tasks?limit=20");
  tasks.replaceChildren(...result.tasks.map(taskCard));
  taskCount.textContent = result.tasks.length ? String(result.tasks.length) : "";
  empty.hidden = result.tasks.length > 0;
  taskPanel.hidden = false;
}

newTask.addEventListener("click", openComposer);
closeComposer.addEventListener("click", () => closeSheet(composerSheet));
closeDetail.addEventListener("click", () => {
  requestGeneration += 1;
  selectedTaskId = null;
  stopPolling();
  closeSheet(detailSheet);
});
instruction.addEventListener("input", () => {
  characterCount.textContent = `${instruction.value.length} / 2000`;
});

createTask.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = displayTitle.value.trim();
  const text = instruction.value.trim();
  if (!title || !text) return;
  if (
    !pendingMutation ||
    pendingMutation.displayTitle !== title ||
    pendingMutation.instruction !== text
  ) {
    pendingMutation = {
      displayTitle: title,
      instruction: text,
      requestId: crypto.randomUUID(),
    };
  }
  submitTask.disabled = true;
  submitTask.textContent = "Создаём…";
  let created;
  try {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bearer}`,
        "Content-Type": "application/json",
        "Idempotency-Key": pendingMutation.requestId,
      },
      body: JSON.stringify({ display_title: title, instruction: text }),
      cache: "no-store",
    });
    if (!response.ok) throw new Error("task_create_failed");
    created = await response.json();
  } catch {
    state.hidden = false;
    state.textContent = "Создание не подтверждено. Повторите запрос.";
    submitTask.disabled = false;
    submitTask.textContent = "Создать задачу";
    return;
  }
  pendingMutation = null;
  displayTitle.value = "";
  instruction.value = "";
  characterCount.textContent = "0 / 2000";
  submitTask.disabled = false;
  submitTask.textContent = "Создать задачу";
  closeSheet(composerSheet);
  state.hidden = true;
  try {
    await loadTasks();
    const accepted = {
      task_id: created.task_id,
      description: title,
    };
    await showTask(created.task_id, accepted);
  } catch {
    state.hidden = false;
    state.textContent = "Задача принята. Статус временно недоступен.";
  }
});

async function start() {
  try {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
    const initData = window.Telegram?.WebApp?.initData || "";
    if (!initData) throw new Error("telegram_context_missing");
    const session = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "text/plain; charset=utf-8" },
      body: initData,
      cache: "no-store",
    });
    if (!session.ok) throw new Error("session_failed");
    bearer = (await session.json()).access_token;
    await loadTasks();
    newTask.hidden = false;
    state.hidden = true;
  } catch {
    showUnavailable();
  }
}

start();
