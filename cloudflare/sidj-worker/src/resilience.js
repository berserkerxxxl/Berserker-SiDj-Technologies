// B/S tech: best-effort, per-isolate protection; no paid storage or personal-data logs.
import { PublicError, boundedJSON, fetchSafe } from "./security.js";

const windows = new Map();
export function allowRate(key, maximum, windowMs, now = Date.now()) {
  const found = windows.get(key);
  if (found && found.expires > now) {
    if (found.count >= maximum) return false;
    found.count++;
    return true;
  }
  // The map never becomes an unbounded per-IP database.
  if (windows.size >= 256) {
    for (const [id, item] of windows) if (item.expires <= now) windows.delete(id);
    if (windows.size >= 256) windows.delete(windows.keys().next().value);
  }
  windows.set(key, { count: 1, expires: now + windowMs });
  return true;
}

export function rateKey(request, route) {
  // Cloudflare sets CF-Connecting-IP at the edge. Never log or persist this key.
  return route + ":" + (request.headers.get("CF-Connecting-IP") || "unknown");
}

export function diagnostic(route, status, started, write = console.info) {
  // Strict allowlist: no headers, URLs, chat/update IDs, message text, errors or tokens.
  const kind = ["telegram", "admin", "setup", "health", "other"].includes(route) ? route : "other";
  try {
    write(JSON.stringify({
      event: "sidj_worker_request", kind, status,
      elapsed_ms: Math.max(0, Math.min(120000, Date.now() - started)),
    }));
  } catch { /* Logging must not prevent replies. */ }
}

const RETRYABLE = new Set([429, 500, 502, 503, 504]);
export async function githubJSON(url, init, limit, pause = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  // Only read-only GitHub GETs use retries. In particular, Telegram sends never retry.
  for (let attempt = 0; attempt < 3; attempt++) {
    const result = await fetchSafe(url, init);
    if (result.ok) return boundedJSON(result, limit);
    const status = result.status;
    await result.body?.cancel();
    if (attempt < 2 && RETRYABLE.has(status)) {
      // 150 + 300ms max. Bounded for the Workers Free request budget.
      await pause(150 * (attempt + 1));
      continue;
    }
    throw new PublicError("GitHub временно недоступен (HTTP " + status + ").");
  }
  throw new PublicError("GitHub временно недоступен.");
}
