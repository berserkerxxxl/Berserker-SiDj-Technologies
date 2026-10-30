export const REPO = "berserkerxxxl/Berserker-SiDj-Technologies";
export const RAW = "https://raw.githubusercontent.com/" + REPO + "/";
export const API = "https://api.github.com/repos/" + REPO;
// Conservative CPU/memory budget for Workers Free, below Telegram's 50 MB limit.
export const MAX_ATTACHMENT = 1024 * 1024;
export const MAX_UPDATE = 64 * 1024;
export const BOT_USERNAME = "bs_sidj_bot";
const moscowFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export class PublicError extends Error {
  constructor(message, status = 502) { super(message); this.status = status; }
}

export function response(text, status = 200, extra = {}) {
  return new Response(text, { status, headers: {
    "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", ...extra,
  } });
}

export function canonicalOrigin(env) {
  try {
    const url = new URL(env.SIDJ_PUBLIC_URL);
    if (url.protocol === "https:" && url.pathname === "/" && !url.search && !url.hash &&
        !url.username && !url.password && !url.port) return url.origin;
  } catch { /* Never include configuration values in diagnostics. */ }
  throw new PublicError("Проверь SIDJ_PUBLIC_URL: нужен точный HTTPS-адрес Worker без пути.", 503);
}

export function checkConfig(env) {
  if (!/^\d{5,16}:[A-Za-z0-9_-]{20,}$/.test(env.SIDJ_TELEGRAM_BOT_TOKEN || "") ||
      !/^[1-9]\d{0,15}$/.test(String(env.SIDJ_TELEGRAM_CHAT_ID || "")) ||
      !Number.isSafeInteger(Number(env.SIDJ_TELEGRAM_CHAT_ID))) {
    throw new PublicError("Добавь корректные Telegram Secrets в Cloudflare.", 503);
  }
  return canonicalOrigin(env);
}

export async function hashHex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
}

export async function webhookSecret(env) {
  return hashHex(new TextEncoder().encode("B/S-SiDj-webhook:" + env.SIDJ_TELEGRAM_BOT_TOKEN));
}

export async function equalSecret(actual, expected) {
  if (typeof actual !== "string" || typeof expected !== "string" || actual.length > 256) return false;
  const encoder = new TextEncoder();
  const [a, b] = await Promise.all([actual, expected].map(s => crypto.subtle.digest("SHA-256", encoder.encode(s))));
  const x = new Uint8Array(a), y = new Uint8Array(b);
  let difference = 0;
  for (let i = 0; i < 32; i++) difference |= x[i] ^ y[i];
  return difference === 0;
}

export function isOwner(env, chat, sender) {
  const owner = String(env.SIDJ_TELEGRAM_CHAT_ID);
  return /^[1-9]\d{0,15}$/.test(owner) && chat?.type === "private" &&
    String(chat.id) === owner && String(sender?.id) === owner && sender?.is_bot === false;
}

export function allowedUpdate(env, body) {
  if (!body || !Number.isSafeInteger(body.update_id) || body.update_id < 0) return false;
  if (body.callback_query) {
    const cb = body.callback_query;
    return isOwner(env, cb.message?.chat, cb.from) && typeof cb.id === "string" &&
      cb.id.length <= 128 && typeof cb.data === "string" &&
      new TextEncoder().encode(cb.data).byteLength <= 64;
  }
  return isOwner(env, body.message?.chat, body.message?.from) && typeof body.message.text === "string";
}

export async function boundedBytes(message, limit) {
  const length = message.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > limit)) {
    if (message.body) await message.body.cancel().catch(() => {});
    throw new PublicError("Превышен допустимый размер.", 413);
  }
  if (!message.body) return new Uint8Array();
  const reader = message.body.getReader(), chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel().catch(() => {});
        throw new PublicError("Превышен допустимый размер.", 413);
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes;
}

export async function boundedJSON(message, limit = MAX_UPDATE) {
  try { return JSON.parse(new TextDecoder().decode(await boundedBytes(message, limit))); }
  catch (error) {
    if (error instanceof PublicError) throw error;
    throw new PublicError("Некорректный JSON.", 400);
  }
}

export async function fetchSafe(url, init = {}, timeout = 4000) {
  try { return await fetch(url, { ...init, redirect: "error", signal: AbortSignal.timeout(timeout) }); }
  catch { throw new PublicError("Сервис временно недоступен. Повтори команду."); }
}

export function validPath(path) {
  return typeof path === "string" && /^(apps|downloads)\/[A-Za-z0-9._/-]+$/.test(path) &&
    path.split("/").every(part => part && part !== "." && part !== "..");
}

export function validateCatalog(data) {
  const invalid = () => { throw new PublicError("Каталог программ временно недоступен."); };
  if (!data || !/^[a-f0-9]{40}$/.test(data.files_ref || "") ||
      !Array.isArray(data.projects) || data.projects.length > 12 || !data.projects.length) invalid();
  const ids = new Set();
  for (const p of data.projects) {
    if (!p || typeof p !== "object") invalid();
    if (!/^[a-z0-9_]{1,24}$/.test(p.id || "") || ids.has(p.id)) invalid();
    ids.add(p.id);
    for (const [key, max] of [["name", 100], ["version", 50], ["description", 1500], ["notes", 600]]) {
      if (typeof p[key] !== "string" || p[key].length > max) invalid();
    }
    if (typeof p.page !== "string" || !p.page.startsWith("https://berserkerxxxl.github.io/Berserker-SiDj-Technologies/")) invalid();
    if (!Array.isArray(p.workflows) || p.workflows.length > 4 ||
        p.workflows.some(w => !/^[A-Za-z0-9._-]+\.ya?ml$/.test(w))) invalid();
    if (!Array.isArray(p.downloads) || p.downloads.length > 8) invalid();
    const downloadIds = new Set();
    for (const d of p.downloads) {
      if (!d || typeof d !== "object") invalid();
      if (!/^[a-z0-9_]{1,24}$/.test(d.id || "") || downloadIds.has(d.id) || !validPath(d.path) ||
          typeof d.label !== "string" || d.label.length > 80 ||
          !/^[a-f0-9]{64}$/.test(d.sha256 || "") || !Number.isSafeInteger(d.size_bytes) || d.size_bytes < 1) invalid();
      downloadIds.add(d.id);
    }
  }
  // Stay inside the Free plan's 50 subrequests, including error diagnostics.
  if (data.projects.reduce((n, p) => n + p.workflows.length, 0) > 6) invalid();
  return data;
}

export function fileURL(catalog, entry) {
  if (!validPath(entry.path) || !/^[a-f0-9]{40}$/.test(catalog.files_ref)) throw new PublicError("Некорректный путь файла.");
  return RAW + catalog.files_ref + "/" + entry.path.split("/").map(encodeURIComponent).join("/");
}

export function timeMSK(value) {
  const date = new Date(value || "");
  return Number.isNaN(date.getTime()) ? "неизвестно" : moscowFormatter.format(date);
}
