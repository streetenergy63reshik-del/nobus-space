const unavailable = "Nobus Space временно недоступен";
const state = document.querySelector("#state");
const tasks = document.querySelector("#tasks");
const detail = document.querySelector("#detail");
const createTask = document.querySelector("#create-task");
const instruction = document.querySelector("#instruction");
let bearer = null;
let pendingMutation = null;
let pollTimer = null;
let selectedTaskId = null;
let requestGeneration = 0;

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function showUnavailable() {
  requestGeneration += 1;
  stopPolling();
  selectedTaskId = null;
  bearer = null;
  tasks.replaceChildren();
  detail.hidden = true;
  createTask.hidden = true;
  state.hidden = false;
  state.textContent = unavailable;
}

function selectionIsCurrent(taskId, generation) {
  return selectedTaskId === taskId && requestGeneration === generation;
}

async function api(path) {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${bearer}` },
    cache: "no-store",
  });
  if (!response.ok) throw new Error("request_failed");
  return response.json();
}

async function showTask(taskId) {
  stopPolling();
  selectedTaskId = taskId;
  const generation = ++requestGeneration;
  try {
    const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    if (!selectionIsCurrent(taskId, generation)) return;
    const eventResult = await api(
      `/api/tasks/${encodeURIComponent(taskId)}/events?limit=20`,
    );
    if (!selectionIsCurrent(taskId, generation)) return;
    detail.replaceChildren();
    const title = document.createElement("h2");
    title.textContent = `Задача ${task.task_id}`;
    const status = document.createElement("p");
    status.textContent = `Статус: ${task.status_label}`;
    const updated = document.createElement("p");
    updated.className = "meta";
    updated.textContent = `Обновлена: ${new Date(task.updated_at).toLocaleString()}`;
    detail.append(title, status, updated);
    if (eventResult.events.length > 0) {
      const eventTitle = document.createElement("h3");
      eventTitle.textContent = "Ход задачи";
      const events = document.createElement("ol");
      for (const event of eventResult.events) {
        const item = document.createElement("li");
        item.textContent = `${event.kind} · ${new Date(event.emitted_at).toLocaleString()}`;
        events.append(item);
      }
      detail.append(eventTitle, events);
    }
    if (task.has_verified_answer) {
      const result = await api(
        `/api/tasks/${encodeURIComponent(taskId)}/result?revision=${encodeURIComponent(task.result_revision)}`,
      );
      if (!selectionIsCurrent(taskId, generation)) return;
      const answerTitle = document.createElement("h3");
      answerTitle.textContent = "Проверенный ответ";
      const answer = document.createElement("pre");
      answer.textContent = result.answer;
      detail.append(answerTitle, answer);
    }
    detail.hidden = false;
    if (!task.terminal && selectionIsCurrent(taskId, generation)) {
      pollTimer = setTimeout(() => showTask(taskId), 3_000);
    }
  } catch {
    if (selectionIsCurrent(taskId, generation)) showUnavailable();
  }
}

async function loadTasks() {
  const result = await api("/api/tasks?limit=20");
  tasks.replaceChildren(
    ...result.tasks.map((task) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const title = document.createElement("strong");
      title.textContent = task.status_label;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = ` · ${new Date(task.updated_at).toLocaleString()}`;
      button.append(title, meta);
      button.addEventListener("click", () => showTask(task.task_id));
      item.append(button);
      return item;
    }),
  );
}

createTask.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = instruction.value.trim();
  if (!text) return;
  if (!pendingMutation || pendingMutation.instruction !== text) {
    pendingMutation = { instruction: text, requestId: crypto.randomUUID() };
  }
  let created;
  try {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bearer}`,
        "Content-Type": "application/json",
        "Idempotency-Key": pendingMutation.requestId,
      },
      body: JSON.stringify({ instruction: text }),
      cache: "no-store",
    });
    if (!response.ok) throw new Error("task_create_failed");
    created = await response.json();
  } catch {
    state.hidden = false;
    state.textContent = "Создание не подтверждено. Повторите запрос.";
    return;
  }
  pendingMutation = null;
  instruction.value = "";
  state.hidden = true;
  try {
    await loadTasks();
    await showTask(created.task_id);
  } catch {
    state.hidden = false;
    state.textContent = "Задача принята. Статус временно недоступен.";
  }
});

async function start() {
  try {
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
    createTask.hidden = false;
    state.hidden = true;
  } catch {
    showUnavailable();
  }
}

start();
