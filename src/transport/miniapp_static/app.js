// Only opaque navigation/request markers survive reload. Core owns all decisions.
const $ = (id) => document.querySelector("#" + id);
const state = $("state"), tasks = $("tasks"), composer = $("composer-sheet");
const detailSheet = $("detail-sheet"), detail = $("detail"), instruction = $("instruction");
const displayTitle = $("display-title"), submit = $("submit-task");
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f-]{27}$/i;
let bearer = null, sessionPromise = null, freshAuthAttempted = false;
let selectedTaskId = marker("selected"), pendingRequest = marker("pending") || marker("clarification");
let clarification = null, submitting = false, selectionGeneration = 0, listGeneration = 0;
let pollTimer = null, pollReads = 0, lastTaskRevision = 0, lastRender = null;

function marker(name) {
  try {
    const value = localStorage.getItem("nobus." + name);
    return value && /^[A-Za-z0-9._~-]{16,128}$/.test(value) ? value : null;
  } catch { return null; }
}
function saveMarker(name, value) {
  try {
    if (value === null) localStorage.removeItem("nobus." + name);
    else localStorage.setItem("nobus." + name, value);
    return value === null || marker(name) === value;
  } catch { return false; }
}
function safeText(value) {
  return String(value ?? "").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "");
}
function element(tag, className = "", value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = safeText(value);
  return node;
}
function button(label, action, className = "secondary-button") {
  const node = element("button", className, label);
  node.type = "button"; node.addEventListener("click", action); return node;
}
function announce(message) {
  if ($("announcement").textContent !== message) $("announcement").textContent = message;
}
function notice(message, label, action) {
  state.hidden = false; state.replaceChildren(element("p", "", message));
  if (label && action) state.append(button(label, action));
  announce(message);
}
function composerMessage(message) {
  $("composer-error").textContent = safeText(message);
  $("composer-error").hidden = !message; announce(message);
  if (message && composer.open) $("composer-error").focus();
}
function stopPolling() { if (pollTimer !== null) clearTimeout(pollTimer); pollTimer = null; }
function current(taskId, generation) { return selectedTaskId === taskId && selectionGeneration === generation; }
function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Время недоступно" :
    new Intl.DateTimeFormat("ru-RU", {day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit"}).format(date);
}
function statusClass(status) {
  return status === "ready" ? "status-answered" : ["failed","attention"].includes(status) ? "status-failed" : "status-running";
}
class ApiError extends Error {
  constructor(status, body = {}) { super("request_failed"); this.status = status; this.body = body; }
}
async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35000);
  try {
    const response = await fetch(path, {...options, cache:"no-store", credentials:"same-origin", signal:controller.signal});
    // Keep the deadline through the response body, including a stalled download.
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > 2 * 1024 * 1024) throw new ApiError(503);
    return new Response(bytes, {status:response.status, headers:response.headers});
  } finally { clearTimeout(timeout); }
}
async function jsonResponse(response) {
  let body;
  try { body = await response.json(); } catch { throw new ApiError(response.status); }
  if (!response.ok) throw new ApiError(response.status, body);
  return body;
}
async function establishSession(allowFresh = false) {
  if (sessionPromise) return sessionPromise;
  sessionPromise = (async () => {
    bearer = null;
    let response = await request("/api/session/recover", {method:"POST"});
    if (response.status === 401 && allowFresh && !freshAuthAttempted) {
      freshAuthAttempted = true;
      if (!window.Telegram?.WebApp?.initData) throw new ApiError(401);
      response = await request("/api/session", {method:"POST",
        headers:{"Content-Type":"text/plain; charset=utf-8"}, body:window.Telegram.WebApp.initData});
    }
    const grant = await jsonResponse(response);
    if (typeof grant.access_token !== "string" || grant.access_token.length < 32) throw new ApiError(503);
    bearer = grant.access_token;
  })();
  try { await sessionPromise; } finally { sessionPromise = null; }
}
async function api(path) {
  let response = await request(path, {headers:{Authorization:"Bearer " + bearer}});
  if (response.status === 401) {
    await establishSession();
    // Exactly one read after session rotation; mutations are never repeated here.
    response = await request(path, {headers:{Authorization:"Bearer " + bearer}});
  }
  return jsonResponse(response);
}
function showError(error, retry = refresh) {
  stopPolling();
  let message, label, action = retry;
  if (error?.status === 401) {
    bearer = null;
    message = "Сессия завершена. Закройте Mini App и откройте его снова из Telegram. Задачи сохранены.";
    label = "Закрыть Mini App"; action = () => window.Telegram?.WebApp?.close();
  } else if (error?.status === 404) {
    message = "Эта задача недоступна. Вернитесь к списку задач.";
    label = "К списку задач";
    action = () => { if (detailSheet.open) detailSheet.close(); return loadTasksSafely(); };
  } else {
    message = navigator.onLine === false ? "Нет соединения. На экране — последние полученные данные." :
      "Не удалось обновить данные. На экране — последнее полученное состояние.";
    label = "Повторить чтение";
  }
  notice(message, label, action);
  if (detailSheet.open) {
    if (lastRender === null) detail.replaceChildren();
    $("detail-error").hidden = false;
    $("detail-error").replaceChildren(element("p", "", message), button(label, action));
  }
  if (composer.open) composerMessage(message);
  updateComposer();
}
function updateComposer() {
  const locked = submitting || Boolean(pendingRequest);
  submit.disabled = locked || !bearer; instruction.disabled = locked; displayTitle.disabled = locked;
  submit.textContent = submitting ? "Проверяем запрос…" : clarification ? "Ответить" : "Создать задачу";
  $("pending-read").hidden = !pendingRequest || submitting;
  $("pending-cancel").hidden = !pendingRequest || submitting;
  $("pending-cancel").disabled = !bearer;
  $("new-task").disabled = locked;
}
function openComposer() {
  if (pendingRequest) { reconcilePending(); return; }
  if (!composer.open) composer.showModal();
  instruction.focus();
}
function taskCard(task) {
  const item = element("li", "task-item " + statusClass(task.status));
  const control = button("", () => selectTask(task.task_id), "task-button");
  const copy = element("div", "task-copy"), meta = element("div", "task-meta");
  copy.append(element("p", "task-description", task.description));
  meta.append(element("span", "status-pill", task.status_label), element("time", "", formatTime(task.created_at)));
  copy.append(meta);
  control.setAttribute("aria-label", safeText(task.description + ". " + task.status_label));
  control.append(copy, element("span", "task-chevron", "›")); item.append(control); return item;
}
async function loadTasks() {
  const generation = ++listGeneration;
  const result = await api("/api/tasks?limit=20");
  if (generation !== listGeneration) return;
  if (!Array.isArray(result.tasks)) throw new ApiError(503);
  tasks.replaceChildren(...result.tasks.map(taskCard));
  $("task-count").textContent = result.tasks.length ? String(result.tasks.length) : "";
  $("empty").hidden = result.tasks.length > 0;
  $("task-panel").hidden = false; $("new-task").hidden = false; updateComposer();
}
async function loadTasksSafely() {
  try { await loadTasks(); state.hidden = true; } catch (error) { showError(error, loadTasksSafely); }
}
function selectTask(taskId) {
  if (!uuidPattern.test(taskId)) return;
  stopPolling(); selectedTaskId = taskId; saveMarker("selected", taskId); selectionGeneration++;
  lastTaskRevision = 0; lastRender = null; pollReads = 0;
  detail.replaceChildren(element("p", "detail-loading", "Загружаем задачу…"));
  $("detail-title").textContent = "Задача"; $("detail-reference").textContent = ""; $("detail-error").hidden = true;
  if (!detailSheet.open) detailSheet.showModal();
  readTask(taskId, selectionGeneration);
}
function renderTask(task, events, result, generation) {
  $("detail-reference").textContent = "Принята " + formatTime(task.created_at);
  $("detail-title").textContent = safeText(task.description);
  const fragment = document.createDocumentFragment(), status = element("section", "detail-meta " + statusClass(task.status));
  status.append(element("h3", "", "Сейчас"), element("strong", "status-pill", task.status_label));
  if (task.reason_label) status.append(element("p", "", task.reason_label));
  status.append(element("time", "", "Обновлено " + formatTime(task.updated_at))); fragment.append(status);
  if (task.instruction_available && typeof task.instruction === "string") {
    const source = element("section", "instruction-card");
    source.append(element("h3", "", "Запрос"), element("p", "", task.instruction)); fragment.append(source);
  }
  if (events.length) {
    fragment.append(element("h3", "", "Ход задачи"));
    const timeline = element("ol", "timeline");
    for (const event of events) {
      const item = element("li", "timeline-item"), dot = element("span", "timeline-dot"), copy = element("div");
      dot.setAttribute("aria-hidden", "true");
      copy.append(element("p", "", event.label || "Состояние обновлено"), element("time", "", formatTime(event.emitted_at)));
      item.append(dot, copy); timeline.append(item);
    }
    fragment.append(timeline);
  }
  if (result) {
    const card = element("section", "result-card"), answer = element("pre", "", result.answer);
    answer.tabIndex = 0;
    const copyStatus = element("p", "copy-status");
    card.append(element("h3", "", "Результат"), answer, button("Копировать результат", async () => {
      try { await navigator.clipboard.writeText(safeText(result.answer)); copyStatus.textContent = "Результат скопирован"; }
      catch {
        const range = document.createRange(); range.selectNodeContents(answer);
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); answer.focus();
        copyStatus.textContent = "Текст выделен. Выберите «Копировать» или нажмите Ctrl+C.";
      }
      announce(copyStatus.textContent);
    }), copyStatus);
    fragment.append(card);
    if (result.artifact) {
      const file = result.artifact, fileCard = element("section", "artifact-card"), copy = element("div"), fileStatus = element("p", "file-status");
      copy.append(element("strong", "", file.filename), element("p", "", "Текстовый файл · " + file.size + " байт"));
      const download = button("Скачать файл", () => downloadArtifact(task.task_id, result, file, generation, download, fileStatus), "artifact-button");
      fileCard.append(copy, download, fileStatus); fragment.append(fileCard);
    }
  }
  if (task.delivery_label) fragment.append(element("p", "delivery-note", task.delivery_label));
  detail.replaceChildren(fragment); $("detail-error").hidden = true;
  announce(task.description + ". " + task.status_label);
}
async function readTask(taskId, generation) {
  try {
    const task = await api("/api/tasks/" + encodeURIComponent(taskId));
    if (!current(taskId, generation)) return;
    if (task.task_id !== taskId || !Number.isInteger(task.task_revision)) throw new ApiError(503);
    if (task.task_revision < lastTaskRevision) return;
    const events = await api("/api/tasks/" + encodeURIComponent(taskId) + "/events?limit=20");
    if (!current(taskId, generation)) return;
    let result = null;
    if (task.has_verified_answer) {
      result = await api("/api/tasks/" + encodeURIComponent(taskId) + "/result?revision=" + task.result_revision);
      if (!current(taskId, generation)) return;
      if (result.task_id !== taskId || result.result_revision !== task.result_revision ||
          result.task_revision !== task.task_revision || result.result_digest !== task.result_digest) throw new ApiError(503);
    }
    if (!Array.isArray(events.events)) throw new ApiError(503);
    lastTaskRevision = task.task_revision;
    const renderKey = JSON.stringify([task.task_revision, task.delivery_label, task.delivery_pending, events.events]);
    if (renderKey !== lastRender) { renderTask(task, events.events, result, generation); lastRender = renderKey; }
    $("detail-error").hidden = true;
    if (!pendingRequest) state.hidden = true;
    if ((!task.terminal || task.delivery_pending) && current(taskId, generation)) {
      if (++pollReads <= 100) pollTimer = setTimeout(() => readTask(taskId, generation), 3000);
      else notice("Автообновление приостановлено. Задача сохранена в журнале.", "Обновить состояние", refresh);
    }
  } catch (error) { if (current(taskId, generation)) showError(error); }
}
async function downloadArtifact(taskId, result, artifact, generation, control, fileStatus) {
  control.disabled = true; let objectUrl = null;
  try {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(artifact.filename) ||
        artifact.media_type !== "text/plain; charset=utf-8" || !Number.isInteger(artifact.size) ||
        artifact.size < 1 || artifact.size > 1024 * 1024) throw new ApiError(503);
    const path = "/api/tasks/" + encodeURIComponent(taskId) + "/artifacts/" + encodeURIComponent(artifact.artifact_id) + "?revision=" + result.result_revision;
    let response = await request(path, {headers:{Authorization:"Bearer " + bearer}});
    if (response.status === 401) {
      await establishSession(); response = await request(path, {headers:{Authorization:"Bearer " + bearer}});
    }
    if (!response.ok) throw new ApiError(response.status);
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength !== artifact.size) throw new ApiError(503);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (value) => value.toString(16).padStart(2,"0")).join("");
    if ("sha256:" + digest !== artifact.content_digest) throw new ApiError(503);
    if (!current(taskId, generation)) return;
    objectUrl = URL.createObjectURL(new Blob([bytes], {type:artifact.media_type}));
    const anchor = element("a"); anchor.href = objectUrl; anchor.download = artifact.filename; anchor.rel = "noopener";
    document.body.append(anchor); anchor.click(); anchor.remove();
    fileStatus.textContent = "Файл получен, целостность проверена. Сохранение передано браузеру.";
    announce(fileStatus.textContent);
  } catch (error) {
    if (!current(taskId, generation)) return;
    fileStatus.textContent = "Файл не получен. Обновите состояние и повторите скачивание.";
    if (error?.status === 401) showError(error);
    announce(fileStatus.textContent);
  } finally {
    if (objectUrl) setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    control.disabled = false;
  }
}
function clearPending() { pendingRequest = null; saveMarker("pending", null); updateComposer(); }
function showClarification(question, token, requestId) {
  if (typeof question !== "string" || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new ApiError(503);
  if (!saveMarker("clarification", requestId)) throw new ApiError(503);
  clarification = token; clearPending();
  $("clarification-question").textContent = safeText(question); $("clarification-question").hidden = false;
  $("composer-title").textContent = "Уточните запрос";
  displayTitle.closest("label").hidden = true; displayTitle.required = false; instruction.value = "";
  $("character-count").textContent = "0 / 2000"; composerMessage(""); updateComposer(); openComposer();
}
async function acceptCreation(created) {
  if (!uuidPattern.test(created.task_id)) throw new ApiError(503);
  clearPending(); saveMarker("clarification", null); clarification = null; instruction.value = ""; displayTitle.value = "";
  if (composer.open) composer.close();
  announce("Задача принята"); selectTask(created.task_id); await loadTasks();
}
function resetClarification() {
  saveMarker("clarification", null); clarification = null;
  $("composer-title").textContent = "Что нужно сделать?"; $("clarification-question").hidden = true;
  displayTitle.closest("label").hidden = false; displayTitle.required = true; updateComposer();
}
function unknownRequest(message) {
  composerMessage(message);
  notice(message, "Проверить приём", reconcilePending);
  state.append(button("Отменить отправку", cancelPending));
  state.append(element("p", "", "Отмена возможна, только если запрос ещё не принят."));
}
async function handleRequestOutcome(result, requestId) {
  if (pendingRequest !== requestId || result.request_id !== requestId) throw new ApiError(503);
  if (result.state === "accepted") { await acceptCreation(result); return true; }
  if (result.state === "clarification") { showClarification(result.question, result.clarification_token, requestId); return true; }
  if (result.state === "not_accepted") {
    clearPending(); resetClarification();
    const message = result.detail === "capability_unavailable" ? "Эта функция пока недоступна. Задача не создана." :
      result.detail === "request_cancelled" ? "Отправка отменена. Этот запрос не создаст задачу." :
      result.detail === "clarification_invalid" ? "Уточнение истекло или уже использовано. Задача не создана. Укажите новый запрос и название." :
      "Запрос не принят. Проверьте формулировку.";
    composerMessage(message); notice(message); return true;
  }
  if (result.state !== "pending") throw new ApiError(503);
  return false;
}
async function cancelPending() {
  if (!pendingRequest || submitting || !bearer) return;
  const requestId = pendingRequest;
  submitting = true; updateComposer();
  try {
    const response = await request("/api/requests/" + encodeURIComponent(requestId) + "/cancel", {
      method:"POST", headers:{Authorization:"Bearer " + bearer}});
    const result = await jsonResponse(response);
    if (!(await handleRequestOutcome(result, requestId)))
      unknownRequest("Запрос уже зафиксирован, отмена не подтверждена. Проверяйте его состояние.");
  } catch (error) {
    if (error?.status === 401) showError(error);
    else unknownRequest("Отмена не подтверждена. Исходный запрос сохранён; проверьте его состояние.");
  } finally { submitting = false; updateComposer(); }
}
async function reconcilePending() {
  if (!pendingRequest || submitting) return;
  const requestId = pendingRequest;
  try {
    const result = await api("/api/requests/" + encodeURIComponent(requestId));
    if (pendingRequest !== requestId) return;
    if (await handleRequestOutcome(result, requestId)) return;
    unknownRequest("Приём ещё не подтверждён. Повторная задача не отправляется.");
  } catch (error) {
    if (pendingRequest !== requestId) return;
    if (error?.status === 401) showError(error, reconcilePending);
    else unknownRequest("Исход отправки неизвестен. Повторная задача не отправляется.");
  }
  updateComposer();
}
async function createTask(event) {
  event.preventDefault();
  if (submitting || pendingRequest || !bearer) return;
  const value = instruction.value.trim(), title = displayTitle.value.trim();
  if (!value || (!clarification && !title)) return;
  const requestId = crypto.randomUUID();
  if (!saveMarker("pending", requestId)) {
    composerMessage("Не удалось сохранить номер запроса для восстановления. Откройте Mini App снова из Telegram."); return;
  }
  pendingRequest = requestId; submitting = true; updateComposer(); composerMessage("");
  const payload = clarification ? {instruction:value, clarification_token:clarification} : {instruction:value, display_title:title};
  try {
    const response = await request("/api/tasks", {method:"POST",
      headers:{Authorization:"Bearer " + bearer, "Content-Type":"application/json", "Idempotency-Key":requestId},
      body:JSON.stringify(payload)});
    if (response.status === 202) await acceptCreation(await jsonResponse(response));
    else if ([400,401,403,408,413,415].includes(response.status)) {
      // Only the Core boundary's exact 408 proves refusal before admission.
      if (response.status === 408 && (await response.json()).detail !== "request_timeout") throw new ApiError(408);
      clearPending();
      if (response.status === 401) showError(new ApiError(401));
      else composerMessage(response.status === 413 ? "Запрос слишком большой. Сократите текст." :
        "Запрос не принят. Проверьте текст и откройте приложение из Telegram.");
    }
  } catch { composerMessage("Ответ на отправку не получен. Проверяем исходный запрос."); }
  finally { submitting = false; updateComposer(); }
  if (pendingRequest) await reconcilePending();
}
async function refresh() {
  stopPolling();
  try {
    if (!bearer) await establishSession();
    if (pendingRequest) await reconcilePending();
    await loadTasks();
    if (selectedTaskId) { pollReads = 0; await readTask(selectedTaskId, ++selectionGeneration); }
    else if (!pendingRequest) state.hidden = true;
  } catch (error) { showError(error); }
}
$("new-task").addEventListener("click", () => {
  if (!clarification) {
    $("composer-title").textContent = "Что нужно сделать?"; $("clarification-question").hidden = true;
    displayTitle.closest("label").hidden = false; displayTitle.required = true;
  }
  openComposer();
});
$("close-composer").addEventListener("click", () => composer.close());
$("close-detail").addEventListener("click", () => detailSheet.close());
detailSheet.addEventListener("close", () => {
  selectionGeneration++; selectedTaskId = null; saveMarker("selected", null); stopPolling();
});
$("create-task").addEventListener("submit", createTask);
$("pending-read").addEventListener("click", reconcilePending);
$("pending-cancel").addEventListener("click", cancelPending);
$("refresh-tasks").addEventListener("click", refresh);
instruction.addEventListener("input", () => { $("character-count").textContent = instruction.value.length + " / 2000"; });
window.addEventListener("offline", () => showError(new ApiError(0)));
window.addEventListener("online", refresh);
window.addEventListener("storage", (event) => {
  if (event.key === "nobus.pending" && !submitting) {
    pendingRequest = marker("pending"); updateComposer();
    if (pendingRequest) reconcilePending();
  }
});
document.addEventListener("visibilitychange", () => { if (document.hidden) stopPolling(); else refresh(); });
async function start() {
  window.Telegram?.WebApp?.ready(); window.Telegram?.WebApp?.expand();
  const themeChanged = () => {
    const theme = window.Telegram?.WebApp?.colorScheme;
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  };
  themeChanged(); window.Telegram?.WebApp?.onEvent?.("themeChanged", themeChanged);
  notice("Открываем журнал задач…");
  try {
    await establishSession(true); await loadTasks();
    if (pendingRequest) await reconcilePending();
    else if (selectedTaskId) selectTask(selectedTaskId);
    else state.hidden = true;
  } catch (error) { showError(error); }
}
start();
