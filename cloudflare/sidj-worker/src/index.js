// B/S tech · СиДжи. No credentials, queues or paid storage in the source tree.
import snapshot from "../../../automation/sidj_projects.json" with { type: "json" };
import { adminRoute } from "./setup.js";
import {
  API, RAW, BOT_USERNAME, MAX_ATTACHMENT, PublicError, response, checkConfig,
  webhookSecret, equalSecret, allowedUpdate, boundedBytes, boundedJSON,
  fetchSafe, validateCatalog, fileURL, hashHex, timeMSK,
} from "./security.js";

export const COMMANDS = [
  ["start", "Приветствие и возможности"], ["projects", "Все программы B/S tech"],
  ["project", "Описание выбранной программы"], ["download", "Скачать программу в Telegram"],
  ["status", "Состояние всех проектов"], ["builds", "Последние сборки программ"],
  ["errors", "Ошибки сборок"], ["help", "Справка на русском"],
].map(([command, description]) => ({ command, description }));
const HELP = "🤖 СиДжи | B/S tech\n\n/projects — каталог разработок\n/project — описание программы\n" +
  "/download — получить файл\n/status — состояние проектов\n/builds — последние сборки\n" +
  "/errors — ошибки сборок\n/help — справка\n\n⚡ Ответы через Cloudflare.\n🔒 Только личный чат владельца.";
const projectRows = projects => projects.map(p => [{ text: p.name, callback_data: "p:" + p.id }]);
// Performance optimizations only, never the authorization boundary.
const jsonCache = new Map(), completed = new Map(), inFlight = new Map();

export async function telegram(env, method, data, timeout = 6000) {
  const multipart = data instanceof FormData;
  const r = await fetchSafe("https://api.telegram.org/bot" + env.SIDJ_TELEGRAM_BOT_TOKEN + "/" + method, {
    method: "POST", headers: multipart ? {} : { "Content-Type": "application/json" },
    body: multipart ? data : JSON.stringify(data),
  }, timeout);
  // Never include a Telegram URL, raw exception or API response in diagnostics.
  if (!r.ok) { await r.body?.cancel(); throw new PublicError("Telegram временно не принял запрос (HTTP " + r.status + ")."); }
  let value;
  try { value = await boundedJSON(r); }
  catch { throw new PublicError("Некорректный ответ Telegram."); }
  if (!value.ok) throw new PublicError("Telegram отклонил запрос. Повтори команду.");
  return value.result;
}

export function say(env, message, rows) {
  const payload = { chat_id: env.SIDJ_TELEGRAM_CHAT_ID, text: String(message).slice(0, 3900),
    link_preview_options: { is_disabled: true } };
  if (rows?.length) payload.reply_markup = { inline_keyboard: rows };
  return telegram(env, "sendMessage", payload);
}

async function cachedJSON(url, ttl, limit = 256 * 1024, headers = {}) {
  const cached = jsonCache.get(url);
  if (cached && cached.expires > Date.now()) return cached.promise;
  const promise = (async () => {
    const r = await fetchSafe(url, { headers, cf: { cacheEverything: true, cacheTtl: ttl } });
    if (!r.ok) { await r.body?.cancel(); throw new PublicError("GitHub временно недоступен (HTTP " + r.status + ")."); }
    return boundedJSON(r, limit);
  })();
  if (jsonCache.size > 64) jsonCache.clear();
  const record = { promise, expires: Date.now() + ttl * 1000 };
  jsonCache.set(url, record);
  try { return await promise; }
  catch (error) { if (jsonCache.get(url) === record) jsonCache.delete(url); throw error; }
}

async function catalog() {
  try { return validateCatalog(await cachedJSON(RAW + "main/automation/sidj_projects.json", 60, 64 * 1024)); }
  catch { return validateCatalog(snapshot); }
}

async function showProjects(env) {
  const { projects } = await catalog();
  return say(env, "📂 B/S tech — наши разработки\n\n" + projects.map(p => "• " + p.name + " · " + p.version).join("\n") +
    "\n\nВыбери программу:", projectRows(projects));
}

async function showProject(env, id) {
  const p = (await catalog()).projects.find(p => p.id === id);
  if (!p) return showProjects(env);
  const rows = p.downloads.map(d => [{ text: "📥 " + d.label, callback_data: "d:" + p.id + ":" + d.id }]);
  rows.push([{ text: "◀️ Все проекты", callback_data: "projects" }]);
  return say(env, "📦 " + p.name + " · " + p.version + "\n\n" + p.description + "\n\nℹ️ " + p.notes +
    "\n\n🌐 " + p.page + "\n\nВыбери файл:", rows);
}

async function linkToFile(env, p, entry, url, explanation) {
  return say(env, explanation + "\n📦 " + p.name + " · " + p.version + "\n" + entry.label +
    "\nРазмер: " + (entry.size_bytes / 1024 / 1024).toFixed(2) + " МБ" +
    "\nSHA-256 опубликованной версии:\n" + entry.sha256,
  [[{ text: "⬇️ Скачать из GitHub", url }]]);
}

async function sendFile(env, pid, did) {
  const manifest = await catalog(), p = manifest.projects.find(p => p.id === pid);
  const entry = p?.downloads.find(d => d.id === did);
  if (!entry) return say(env, "Файл не найден в каталоге. Открой /projects.");
  const url = fileURL(manifest, entry);
  // Telegram can fetch ZIP/PDF by HTTPS URL (20 MB). The immutable Git commit
  // and the manifest prepared from its bytes bind this URL to the release.
  // No 18 MB buffer or multipart copy is created in the Free Worker.
  if (entry.size_bytes > MAX_ATTACHMENT && entry.size_bytes <= 20_000_000 && /\.(zip|pdf)$/i.test(entry.path)) {
    try {
      return await telegram(env, "sendDocument", { chat_id: env.SIDJ_TELEGRAM_CHAT_ID, document: url,
        caption: ("📦 " + p.name + " · " + p.version + "\n" + entry.label +
          "\nSHA-256 опубликованной версии:\n" + entry.sha256).slice(0, 1000) }, 15000);
    } catch {
      return linkToFile(env, p, entry, url, "Telegram не подтвердил получение архива. Доступна прямая ссылка.");
    }
  }
  if (entry.size_bytes > MAX_ATTACHMENT) return linkToFile(env, p, entry, url,
    "Для этого формата или размера доступна прямая ссылка на файл.");
  let bytes;
  try {
    const r = await fetchSafe(url);
    if (!r.ok) { await r.body?.cancel(); throw new PublicError("Файл недоступен в GitHub."); }
    bytes = await boundedBytes(r, MAX_ATTACHMENT);
  } catch (error) {
    if (error instanceof PublicError && error.status === 413) return say(env, "⛔ Размер загрузки не соответствует каталогу. Передача отменена.");
    return linkToFile(env, p, entry, url, "Не удалось подготовить вложение. Доступна ссылка на опубликованную версию.");
  }
  if (bytes.byteLength !== entry.size_bytes || await hashHex(bytes) !== entry.sha256) {
    return say(env, "⛔ Размер или SHA-256 не совпали с каталогом. Файл и ссылка не отправлены.");
  }
  const filename = entry.path.split("/").at(-1), form = new FormData();
  form.set("chat_id", String(env.SIDJ_TELEGRAM_CHAT_ID));
  form.set("caption", ("📦 " + p.name + " · " + p.version + "\n" + entry.label + "\n✅ SHA-256 проверен").slice(0, 1000));
  form.set("disable_content_type_detection", "true");
  form.set("document", new File([bytes], filename, { type: "application/octet-stream" }), filename);
  try { return await telegram(env, "sendDocument", form); }
  catch { return linkToFile(env, p, entry, url, "Telegram не подтвердил отправку вложения. Доступна прямая ссылка."); }
}

function github(path) {
  return cachedJSON(API + path, 60, 768 * 1024, {
    Accept: "application/vnd.github+json", "User-Agent": "BS-tech-SiDj", "X-GitHub-Api-Version": "2022-11-28",
  });
}

async function projectRuns(p, limit = 12) {
  const results = await Promise.allSettled(p.workflows.map(name => github(
    "/actions/workflows/" + name + "/runs?per_page=20")));
  const all = results.filter(r => r.status === "fulfilled").flatMap(r => r.value.workflow_runs || []);
  if (results.some(r => r.status === "rejected")) throw new PublicError("Не удалось получить полную историю сборок GitHub.");
  return all.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, limit);
}

function state(run) {
  return { success: "✅ Успешно", failure: "❌ Ошибка", timed_out: "⏱ Превышено время",
    cancelled: "⚪ Отменено", skipped: "⏭ Пропущено", action_required: "⚠️ Требуется действие" }[run.conclusion] ||
    ({ queued: "🕒 Ожидание", waiting: "🕒 Ожидание", in_progress: "🔄 Выполняется" }[run.status] || "ℹ️ Нет результата");
}

async function failureReason(run) {
  if (run.conclusion === "timed_out") return "Превышено время выполнения";
  if (run.conclusion !== "failure") return "";
  if (Number.isSafeInteger(run.id)) {
    try {
      const jobs = (await github("/actions/runs/" + run.id + "/jobs?per_page=30")).jobs || [];
      const job = jobs.find(j => ["failure", "timed_out"].includes(j.conclusion));
      const step = job?.steps?.find(s => ["failure", "timed_out"].includes(s.conclusion));
      if (job) return ("Не прошёл этап: " + job.name + (step ? " → " + step.name : "")).slice(0, 240);
    } catch { /* Report available evidence, never guess a root cause. */ }
  }
  return "Один из этапов завершился ошибкой; подробности в журнале GitHub";
}

async function runText(p, run) {
  const reason = await failureReason(run);
  // Historic runs do not necessarily build the current published version.
  return p.name + ": " + state(run) + "\nСборка #" + run.run_number +
    " · " + String(run.name || "").slice(0, 70) + "\nМосква: " + timeMSK(run.updated_at || run.created_at) +
    (reason ? "\nПричина: " + reason : "");
}

function errorRows(entries) {
  return entries.filter(([, r]) => ["failure", "timed_out"].includes(r.conclusion) &&
    /^https:\/\/github\.com\/berserkerxxxl\/Berserker-SiDj-Technologies\/actions\/runs\/\d+$/.test(r.html_url || ""))
    .map(([, r]) => [{ text: "🔍 Посмотреть ошибку #" + r.run_number, url: r.html_url }]);
}

async function status(env) {
  const { projects } = await catalog(), entries = [];
  const lines = await Promise.all(projects.map(async p => {
    if (!p.workflows.length) return "📦 " + p.name + " · " + p.version + "\nОпубликован. Автосборка не настроена.";
    try {
      const run = (await projectRuns(p, 1))[0];
      if (!run) return p.name + ": нет данных о сборке.";
      entries.push([p, run]);
      return "Публикация: " + p.version + "\n" + await runText(p, run);
    } catch { return p.name + " · " + p.version + "\n⚠️ Состояние сборки GitHub временно недоступно."; }
  }));
  return say(env, "📊 B/S tech — состояние проектов\n\n" + lines.join("\n\n"),
    [[{ text: "📂 Каталог программ", callback_data: "projects" }], ...errorRows(entries)]);
}

async function recent(env, onlyErrors) {
  const projects = (await catalog()).projects.filter(p => p.workflows.length);
  const results = await Promise.allSettled(projects.map(p => projectRuns(p, 20)));
  const incomplete = results.some(r => r.status === "rejected");
  const entries = results.flatMap((r, i) => r.status === "fulfilled" ? r.value.map(run => [projects[i], run]) : [])
    .filter(([, r]) => !onlyErrors || ["failure", "timed_out"].includes(r.conclusion))
    .sort((a, b) => String(b[1].created_at).localeCompare(String(a[1].created_at))).slice(0, 5);
  if (!entries.length) return say(env, incomplete ? "⚠️ История сборок GitHub временно недоступна. Повтори команду." :
    onlyErrors ? "✅ В последних доступных запусках ошибок нет." : "Сборок пока нет.");
  const texts = await Promise.all(entries.map(([p, r]) => runText(p, r)));
  return say(env, (onlyErrors ? "🚨 Ошибки в последних запусках" : "🔧 Последние сборки") + "\n\n" +
    texts.join("\n\n") + (incomplete ? "\n\n⚠️ Часть истории недоступна." : ""), errorRows(entries));
}

async function command(env, text) {
  const words = text.trim().split(/\s+/), [name, mention, extra] = words[0].toLowerCase().split("@");
  if ((mention && mention !== BOT_USERNAME) || extra) return;
  if (["/start", "/help"].includes(name)) return say(env, HELP, [
    [{ text: "📂 Все проекты", callback_data: "projects" }], [{ text: "📥 Скачать", callback_data: "downloads" }],
  ]);
  if (name === "/projects") return showProjects(env);
  if (name === "/project") return showProject(env, (words[1] || "").toLowerCase());
  if (name === "/download") {
    if (words[1] && words[2]) return sendFile(env, words[1].toLowerCase(), words[2].toLowerCase());
    return words[1] ? showProject(env, words[1].toLowerCase()) : showProjects(env);
  }
  if (name === "/status") return status(env);
  if (name === "/builds") return recent(env, false);
  if (name === "/errors") return recent(env, true);
  return say(env, "Напиши /help или выбери программу в /projects.");
}

async function handleUpdate(env, body) {
  const cb = body.callback_query;
  if (!cb) return command(env, body.message.text);
  // Stop the spinner BEFORE catalog/file/API calls. An expired ack must not
  // prevent delivery of the actual response below.
  try { await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id }); }
  catch { /* Best effort; the actual answer below is still awaited. */ }
  if (["projects", "downloads"].includes(cb.data)) return showProjects(env);
  if (/^p:[a-z0-9_]{1,24}$/.test(cb.data)) return showProject(env, cb.data.slice(2));
  if (/^d:[a-z0-9_]{1,24}:[a-z0-9_]{1,24}$/.test(cb.data)) return sendFile(env, ...cb.data.split(":").slice(1));
  return say(env, "Кнопка устарела. Открой /projects.");
}

async function processOnce(env, body, key) {
  if (completed.get(key) > Date.now()) return;
  if (inFlight.has(key)) return inFlight.get(key);
  const task = (async () => {
    // Reply delivery is awaited before 2xx. No fire-and-forget command handling.
    await handleUpdate(env, body);
    if (completed.size >= 512) {
      for (const [id, expires] of completed) if (expires <= Date.now()) completed.delete(id);
      if (completed.size >= 512) completed.delete(completed.keys().next().value);
    }
    completed.set(key, Date.now() + 24 * 60 * 60 * 1000);
  })();
  inFlight.set(key, task);
  try { await task; } finally { inFlight.delete(key); }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/setup" || url.pathname.startsWith("/admin/")) return await adminRoute(request, env, telegram, COMMANDS);
      if (url.pathname === "/activate") return response("Активация через GET отключена. Используй защищённую панель /setup.", 405, { Allow: "POST" });
      if (url.pathname === "/telegram") {
        if (request.method !== "POST") return response("Method not allowed", 405, { Allow: "POST" });
        if (url.origin !== checkConfig(env)) return response("Forbidden", 403);
        const secret = await webhookSecret(env);
        if (!await equalSecret(request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "", secret)) return response("Forbidden", 403);
        if (!/^application\/json(?:;|$)/i.test(request.headers.get("content-type") || "")) return response("JSON required", 415);
        const body = await boundedJSON(request);
        if (!body || !Number.isSafeInteger(body.update_id) || body.update_id < 0) return response("Invalid update", 400);
        if (!allowedUpdate(env, body)) return response("OK");
        await processOnce(env, body, secret + ":" + body.update_id);
        return response("OK");
      }
      if (url.pathname === "/" && request.method === "GET") return response("🤖 СиДжи | B/S tech\nWorker доступен. Настройка владельца: /setup.");
      return response("Not found", 404);
    } catch (error) {
      return response(error instanceof PublicError ? error.message : "Временная ошибка обработки. Telegram повторит запрос.",
        error instanceof PublicError ? error.status : 502);
    }
  },
};
