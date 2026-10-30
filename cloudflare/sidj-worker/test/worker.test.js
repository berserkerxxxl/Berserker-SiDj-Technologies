import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import manifest from "../../../automation/sidj_projects.json" with { type: "json" };
import { webhookSecret, boundedBytes, validateCatalog, fileURL, timeMSK, MAX_ATTACHMENT, fetchSafe } from "../src/security.js";

const env = { SIDJ_TELEGRAM_BOT_TOKEN: "12345:" + "x".repeat(35), SIDJ_TELEGRAM_CHAT_ID: "42",
  SIDJ_PUBLIC_URL: "https://bs-tech-sidj.example.workers.dev/", SIDJ_ADMIN_TOKEN: "a".repeat(48) };
const origin = new URL(env.SIDJ_PUBLIC_URL).origin;
const sender = { id: 42, is_bot: false }, chat = { id: 42, type: "private" };
let serial = 0, updateId = 100;
const realFetch = globalThis.fetch;
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const message = text => ({ update_id: ++updateId, message: { from: sender, chat, text } });
const callback = data => ({ update_id: ++updateId, callback_query: { id: "callback", from: sender, message: { chat }, data } });
const run = (id, conclusion) => ({ id, run_number: id, status: "completed", conclusion, name: "Reserve build",
  created_at: "2026-10-30T10:00:00Z", updated_at: "2026-10-30T10:01:00Z",
  html_url: "https://github.com/berserkerxxxl/Berserker-SiDj-Technologies/actions/runs/" + id });

async function fixture(options = {}) {
  const worker = (await import("../src/index.js?test=" + ++serial)).default;
  const calls = [], tg = [];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(url), method = parsed.pathname.split("/").at(-1);
    calls.push({ url, init });
    assert.equal(init.redirect, "manual");
    if (parsed.hostname === "api.telegram.org") {
      const data = init.body instanceof FormData ? init.body : JSON.parse(init.body);
      tg.push({ method, data });
      if (options.telegram) { const result = await options.telegram(method, data); if (result) return result; }
      const results = { getMe: { is_bot: true, username: "BS_SiDj_bot" }, getChat: { id: 42, type: "private" },
        getWebhookInfo: { url: options.webhook || "", pending_update_count: 0 },
        sendMessage: { message_id: 1 }, sendDocument: { message_id: 2 } };
      return json({ ok: true, result: results[method] ?? true });
    }
    if (parsed.pathname.endsWith("automation/sidj_projects.json")) {
      return options.catalogError ? json({}, 503) : json(options.manifest || manifest);
    }
    if (parsed.hostname === "raw.githubusercontent.com") {
      if (options.file) return options.file(url);
      const entry = manifest.projects.flatMap(p => p.downloads).find(d => url.endsWith("/" + d.path));
      assert.ok(entry, "only allowlisted files may be fetched");
      const bytes = await readFile(new URL("../../../" + entry.path, import.meta.url));
      return new Response(bytes);
    }
    if (parsed.hostname === "api.github.com") {
      if (options.githubError) return json({}, 403);
      if (parsed.pathname.endsWith("/jobs")) return json({ jobs: [{ name: "Windows", conclusion: "failure", steps: [{ name: "Compile", conclusion: "failure" }] }] });
      return json({ workflow_runs: options.runs || [run(10, "success"), run(9, "failure")] });
    }
    throw Error("Unexpected outbound request");
  };
  return { worker, calls, tg, async send(body, customHeaders = {}, customEnv = env) {
    return worker.fetch(new Request(origin + "/telegram", { method: "POST", headers: {
      "Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": await webhookSecret(customEnv), ...customHeaders,
    }, body: typeof body === "string" ? body : JSON.stringify(body) }), customEnv);
  }, async admin(action, headers = {}, customEnv = env, data = { confirm: action }) {
    return worker.fetch(new Request(origin + "/admin/" + action, { method: "POST", headers: {
      "Content-Type": "application/json", Authorization: "Bearer " + env.SIDJ_ADMIN_TOKEN, ...headers,
    }, body: JSON.stringify(data) }), customEnv);
  } };
}
test.afterEach(() => { globalThis.fetch = realFetch; });

test("outbound redirects are rejected without forwarding the authorization header", async () => {
  let calls = 0, cancelled = false;
  globalThis.fetch = async (_url, init) => {
    calls++;
    assert.equal(init.redirect, "manual");
    return new Response(new ReadableStream({ cancel() { cancelled = true; } }), {
      status: 302, headers: { Location: "https://untrusted.example/" },
    });
  };
  await assert.rejects(fetchSafe("https://api.telegram.org/test", {
    headers: { Authorization: "Bearer test-only" },
  }), /Сервис временно недоступен/);
  assert.equal(calls, 1);
  assert.equal(cancelled, true);
});

test("cached webhook digest changes after token rotation and rejects stale headers", async () => {
  const old = await webhookSecret(env);
  assert.equal(await webhookSecret(env), old);
  const rotated = { ...env, SIDJ_TELEGRAM_BOT_TOKEN: "12345:" + "y".repeat(35) };
  const replacement = await webhookSecret(rotated);
  assert.notEqual(replacement, old);
  assert.equal(await webhookSecret(env), old);
  const f = await fixture();
  assert.equal((await f.send(message("/start"), {
    "X-Telegram-Bot-Api-Secret-Token": old,
  }, rotated)).status, 403);
  assert.equal((await f.send(message("/start"), {
    "X-Telegram-Bot-Api-Secret-Token": replacement,
  }, rotated)).status, 200);
});

test("public GET activation cannot change Telegram configuration", async () => {
  const f = await fixture();
  for (const path of ["/activate", "/admin/activate", "/admin/rollback"]) {
    assert.equal((await f.worker.fetch(new Request(origin + path), env)).status, 405);
  }
  assert.equal(f.calls.length, 0);
});

test("setup page has CSP, no persistent credential storage and no embedded secrets", async () => {
  const f = await fixture(), r = await f.worker.fetch(new Request(origin + "/setup"), env), html = await r.text();
  assert.equal(r.status, 200);
  assert.match(r.headers.get("content-security-policy"), /frame-ancestors 'none'/);
  assert.match(r.headers.get("content-security-policy"), /script-src 'nonce-/);
  assert.equal(r.headers.get("cache-control"), "no-store");
  for (const value of [env.SIDJ_TELEGRAM_BOT_TOKEN, env.SIDJ_ADMIN_TOKEN, "localStorage", "sessionStorage"]) assert.ok(!html.includes(value));
  assert.equal(f.calls.length, 0);
});

test("admin rejects missing/wrong key, cross-site requests, wrong confirmation and preview origin", async () => {
  const f = await fixture();
  for (const headers of [{ Authorization: "" }, { Authorization: "Bearer wrong" }, { Origin: "https://evil.example" }, { "Sec-Fetch-Site": "cross-site" }]) {
    assert.equal((await f.admin("activate", headers)).status, 403);
  }
  assert.equal((await f.admin("activate", {}, { ...env, SIDJ_PUBLIC_URL: "https://other.workers.dev/" })).status, 403);
  assert.equal((await f.admin("activate", {}, env, {})).status, 400);
  assert.equal(f.calls.length, 0);
});

test("activation checks identity, preserves queue and refreshes the webhook secret", async () => {
  let active = false;
  const f = await fixture({ telegram(method) {
    if (method === "setWebhook") active = true;
    if (method === "getWebhookInfo") return json({ ok: true, result: { url: active ? origin + "/telegram" : "" } });
  } });
  assert.equal((await f.admin("activate")).status, 200);
  assert.deepEqual(f.tg.map(t => t.method), ["getMe", "getChat", "getWebhookInfo", "setMyCommands", "setWebhook", "getWebhookInfo"]);
  const { data } = f.tg.find(t => t.method === "setWebhook");
  assert.equal(data.url, origin + "/telegram");
  assert.equal(data.drop_pending_updates, false);
  assert.equal(data.max_connections, 1);
  assert.equal(data.secret_token, await webhookSecret(env));
  assert.deepEqual(data.allowed_updates, ["message", "callback_query"]);
  assert.deepEqual(f.tg.find(t => t.method === "setMyCommands").data.scope, { type: "chat", chat_id: 42 });
  assert.equal((await f.admin("activate")).status, 200);
  assert.equal(f.tg.filter(t => t.method === "setWebhook").length, 2);
});

test("activation never overwrites another bot, group owner or existing foreign webhook", async () => {
  for (const settings of [
    { webhook: "https://existing.example/telegram" },
    { telegram: method => method === "getMe" ? json({ ok: true, result: { is_bot: true, username: "different_bot" } }) : null },
    { telegram: method => method === "getChat" ? json({ ok: true, result: { id: 42, type: "group" } }) : null },
  ]) {
    const f = await fixture(settings);
    assert.equal((await f.admin("activate")).status, 409);
    assert.ok(!f.tg.some(t => ["setWebhook", "setMyCommands", "deleteWebhook"].includes(t.method)));
  }
});

test("admin status redacts Telegram diagnostics and rollback preserves pending updates", async () => {
  const f = await fixture({ webhook: origin + "/telegram" });
  const status = await f.admin("status");
  assert.match(await status.text(), /подключён к этому Worker/);
  assert.ok(!f.tg.some(t => t.method.startsWith("set")));
  let removed = false;
  const g = await fixture({ telegram(method) {
    if (method === "deleteWebhook") removed = true;
    if (method === "getWebhookInfo") return json({ ok: true, result: { url: removed ? "" : origin + "/telegram" } });
  } });
  assert.equal((await g.admin("rollback")).status, 200);
  assert.deepEqual(g.tg.find(t => t.method === "deleteWebhook").data, { drop_pending_updates: false });
});

test("webhook rejects unsigned, malformed, oversized, wrong-origin and non-JSON requests", async () => {
  const f = await fixture();
  assert.equal((await f.send(message("/start"), { "X-Telegram-Bot-Api-Secret-Token": "" })).status, 403);
  assert.equal((await f.send(message("/start"), { "X-Telegram-Bot-Api-Secret-Token": "wrong" })).status, 403);
  assert.equal((await f.send(message("/start"), { "Content-Type": "text/plain" })).status, 415);
  assert.equal((await f.send("{")).status, 400);
  assert.equal((await f.send("x".repeat(70000))).status, 413);
  assert.equal((await f.send({ update_id: "123" })).status, 400);
  assert.equal((await f.send(message("/start"), {}, { ...env, SIDJ_PUBLIC_URL: "https://other.workers.dev/" })).status, 403);
  assert.equal(f.calls.length, 0);
});

test("only owner sender AND owner private chat can invoke commands or callbacks", async () => {
  const f = await fixture();
  const cases = [message("/start"), message("/start"), message("/start"), callback("projects"), callback("projects")];
  cases[0].message.chat = { ...chat, type: "group" };
  cases[1].message.from = { id: 43, is_bot: false };
  cases[2].message.from = { id: 42, is_bot: true };
  cases[3].callback_query.from = { id: 43, is_bot: false };
  delete cases[4].callback_query.message;
  for (const body of cases) assert.equal((await f.send(body)).status, 200);
  assert.equal(f.calls.length, 0);
});

test("start/help answer without GitHub; mentions for another bot are ignored", async () => {
  const f = await fixture();
  for (const text of ["/start", "/help", "/help@BS_SiDj_bot"]) assert.equal((await f.send(message(text))).status, 200);
  assert.equal(f.tg.length, 3);
  assert.ok(f.tg.every(t => t.method === "sendMessage" && t.data.chat_id === "42"));
  assert.equal((await f.send(message("/start@other_bot"))).status, 200);
  assert.equal(f.tg.length, 3);
  assert.equal(f.calls.length, 3);
});

test("all catalog commands show programs, descriptions, versions and download buttons", async () => {
  const f = await fixture();
  for (const text of ["/projects", "/project", "/download", "/project reserve", "/download reserve"]) {
    assert.equal((await f.send(message(text))).status, 200);
  }
  const shown = f.tg.at(-1).data;
  assert.match(shown.text, /B\/S Reserve · 0.2.0/);
  assert.ok(shown.text.includes(manifest.projects.at(-1).description));
  assert.equal(shown.reply_markup.inline_keyboard[0][0].callback_data, "d:reserve:win");
});

test("callback ack precedes all catalog/API/file work, including stale ack errors", async () => {
  const f = await fixture({ telegram: method => method === "answerCallbackQuery" ? json({}, 400) : null });
  assert.equal((await f.send(callback("p:reserve"))).status, 200);
  assert.match(f.calls[0].url, /answerCallbackQuery$/);
  assert.equal(f.tg.at(-1).method, "sendMessage");
  assert.match(f.tg.at(-1).data.text, /B\/S Reserve/);
});

test("small file is sent as original multipart bytes after SHA-256 verification", async () => {
  const f = await fixture();
  assert.equal((await f.send(callback("d:limits:script"))).status, 200);
  const form = f.tg.find(t => t.method === "sendDocument").data;
  const file = form.get("document");
  assert.equal(file.name, "BS-tech-Limits-AI-v3.9.user.js");
  const original = await readFile(new URL("../../../downloads/" + file.name, import.meta.url));
  assert.deepEqual(new Uint8Array(await file.arrayBuffer()), new Uint8Array(original));
  assert.match(form.get("caption"), /SHA-256 проверен/);
});

test("checksum/size mismatch stops attachment and does not offer a bypass link", async () => {
  const f = await fixture({ file: () => new Response("corrupt") });
  assert.equal((await f.send(message("/download limits script"))).status, 200);
  assert.ok(!f.tg.some(t => t.method === "sendDocument"));
  assert.match(f.tg.at(-1).data.text, /не совпали/);
  assert.equal(f.tg.at(-1).data.reply_markup, undefined);
});

test("large tar.gz uses immutable commit link and expected SHA, without buffering its body", async () => {
  const f = await fixture();
  assert.equal((await f.send(message("/download reserve linux_x64"))).status, 200);
  assert.equal(f.calls.filter(c => c.url.includes("raw.githubusercontent.com")).length, 1, "only the catalog is fetched");
  const data = f.tg.at(-1).data, file = manifest.projects.at(-1).downloads.find(d => d.id === "linux_x64");
  assert.ok(data.text.includes(file.sha256));
  assert.equal(data.reply_markup.inline_keyboard[0][0].url, fileURL(manifest, file));
  assert.ok(!data.text.includes("SHA-256 проверен"));
});

test("large ZIP is delegated to Telegram by immutable URL without a Worker buffer", async () => {
  const f = await fixture();
  assert.equal((await f.send(message("/download reserve win"))).status, 200);
  assert.equal(f.calls.filter(c => c.url.includes("raw.githubusercontent.com")).length, 1);
  const data = f.tg.find(t => t.method === "sendDocument").data, file = manifest.projects.at(-1).downloads[0];
  assert.equal(data.document, fileURL(manifest, file));
  assert.ok(data.caption.includes(file.sha256));
  assert.ok(!data.caption.includes("SHA-256 проверен"));
});

test("rejected ZIP transfer falls back to a safe immutable download link", async () => {
  const f = await fixture({ telegram: method => method === "sendDocument" ? json({}, 400) : null });
  assert.equal((await f.send(message("/download reserve win"))).status, 200);
  assert.match(f.tg.at(-1).data.text, /не подтвердил/);
  assert.ok(f.tg.at(-1).data.reply_markup.inline_keyboard[0][0].url.includes(manifest.files_ref));
});

test("stream size limit works without Content-Length and cancels before buffering excess", async () => {
  let cancelled = false;
  const stream = new ReadableStream({ pull(controller) { controller.enqueue(new Uint8Array(600)); }, cancel() { cancelled = true; } });
  await assert.rejects(boundedBytes(new Response(stream), 1000), { status: 413 });
  assert.equal(cancelled, true);
  const f = await fixture({ file: () => new Response("x", { headers: { "Content-Length": String(MAX_ATTACHMENT + 1) } }) });
  assert.equal((await f.send(message("/download limits script"))).status, 200);
  assert.equal(f.tg.at(-1).data.reply_markup, undefined);
});

test("GitHub outage falls back to bundled catalog; invalid paths and metadata are rejected", async () => {
  const f = await fixture({ catalogError: true });
  assert.equal((await f.send(message("/projects"))).status, 200);
  assert.match(f.tg.at(-1).data.text, /B\/S Reserve/);
  for (const path of ["downloads/../token", "downloads//x", "downloads/%2e%2e/x", "https://evil.test/a", "automation/private.txt"]) {
    const bad = structuredClone(manifest); bad.projects[0].downloads[0].path = path;
    assert.throws(() => validateCatalog(bad));
  }
  const bad = structuredClone(manifest); bad.projects[0].downloads[0].sha256 = "bad";
  assert.throws(() => validateCatalog(bad));
});

test("builds show successes without links; failures have evidence and a safe error button", async () => {
  const f = await fixture();
  assert.equal((await f.send(message("/builds"))).status, 200);
  let data = f.tg.at(-1).data;
  assert.match(data.text, /Успешно/);
  assert.match(data.text, /Windows → Compile/);
  assert.ok(!data.text.includes("https://"));
  assert.ok(data.reply_markup.inline_keyboard.every(row => row[0].url.endsWith("/9")));
  assert.equal((await f.send(message("/errors"))).status, 200);
  data = f.tg.at(-1).data;
  assert.ok(!data.text.includes("Успешно"));
  assert.equal((await f.send(message("/status"))).status, 200);
  assert.match(f.tg.at(-1).data.text, /Публикация: 0.2.0/);
});

test("unavailable build history is never misreported as no errors", async () => {
  const f = await fixture({ githubError: true });
  assert.equal((await f.send(message("/errors"))).status, 200);
  assert.match(f.tg.at(-1).data.text, /недоступна/);
  assert.equal((await f.send(message("/status"))).status, 200);
  assert.match(f.tg.at(-1).data.text, /недоступно/);
});

test("webhook waits for reply, coalesces concurrent retries and remembers completed update", async () => {
  let release, reached;
  const sent = new Promise(resolve => { reached = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  const f = await fixture({ telegram: async method => { if (method === "sendMessage") { reached(); return pending; } } });
  const body = message("/start");
  let complete = false;
  const first = f.send(body).then(r => { complete = true; return r; });
  await sent;
  const second = f.send(body);
  await Promise.resolve();
  assert.equal(complete, false);
  release(json({ ok: true, result: { message_id: 1 } }));
  assert.equal((await first).status, 200);
  assert.equal((await second).status, 200);
  assert.equal((await f.send(body)).status, 200);
  assert.equal(f.tg.length, 1);
});

test("reply failures return non-2xx, remain retryable and never expose token-bearing errors", async () => {
  let fail = true;
  const f = await fixture({ telegram: method => {
    if (method === "sendMessage" && fail) throw Error("network " + env.SIDJ_TELEGRAM_BOT_TOKEN);
  } });
  const body = message("/start"), result = await f.send(body);
  assert.equal(result.status, 502);
  assert.ok(!(await result.text()).includes(env.SIDJ_TELEGRAM_BOT_TOKEN));
  fail = false;
  assert.equal((await f.send(body)).status, 200);
  assert.equal(f.tg.length, 2);
});

test("Moscow times use 24-hour format across a date boundary", () => {
  assert.match(timeMSK("2026-10-30T23:15:00Z"), /31\.10\.2026.*02:15/);
  assert.match(timeMSK("2026-10-30T21:15:00Z"), /31\.10\.2026.*00:15/);
});
