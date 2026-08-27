const unavailable = "Nobus Space временно недоступен";
const state = document.querySelector("#state");
const tasks = document.querySelector("#tasks");
const detail = document.querySelector("#detail");
let bearer = null;

function showUnavailable() {
  bearer = null;
  tasks.replaceChildren();
  detail.hidden = true;
  state.hidden = false;
  state.textContent = unavailable;
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
  try {
    const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    detail.replaceChildren();
    const title = document.createElement("h2");
    title.textContent = `Задача ${task.task_id}`;
    const status = document.createElement("p");
    status.textContent = `Статус: ${task.status}`;
    const updated = document.createElement("p");
    updated.className = "meta";
    updated.textContent = `Обновлена: ${new Date(task.updated_at).toLocaleString()}`;
    detail.append(title, status, updated);
    detail.hidden = false;
  } catch {
    showUnavailable();
  }
}

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
    const result = await api("/api/tasks?limit=20");
    tasks.replaceChildren(
      ...result.tasks.map((task) => {
        const item = document.createElement("li");
        const button = document.createElement("button");
        const title = document.createElement("strong");
        title.textContent = task.status;
        const meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = ` · ${new Date(task.updated_at).toLocaleString()}`;
        button.append(title, meta);
        button.addEventListener("click", () => showTask(task.task_id));
        item.append(button);
        return item;
      }),
    );
    state.hidden = true;
  } catch {
    showUnavailable();
  }
}

start();
