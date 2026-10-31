import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { allowRate, diagnostic, githubJSON } from "../src/resilience.js";
import { webhookSecret } from "../src/security.js";

const realFetch = globalThis.fetch;
const origin = "https://bs-tech-sidj.example.workers.dev";
const env = {
  SIDJ_PUBLIC_URL: origin + "/",
  SIDJ_TELEGRAM_BOT_TOKEN: "12345:" + "x".repeat(35),
  SIDJ_TELEGRAM_CHAT_ID: "42", SIDJ_ADMIN_TOKEN: "a".repeat(48),
};
test.afterEach(() => { globalThis.fetch = realFetch; });

test("per-isolate rate window is bounded, expires and never requires external storage", () => {
  const key = "unit-test-unique-key";
  assert.equal(allowRate(key, 2, 1000, 100), true);
  assert.equal(allowRate(key, 2, 1000, 101), true);
  assert.equal(allowRate(key, 2, 1000, 102), false);
  assert.equal(allowRate(key, 2, 1000, 1100), true);
});

test("structured diagnostics contain only allowlisted fields, never owner data", () => {
  const lines = [];
  diagnostic("token-secret-chat-123", 502, Date.now() - 17, line => lines.push(line));
  const entry = JSON.parse(lines[0]);
  assert.deepEqual(Object.keys(entry), ["event", "kind", "status", "elapsed_ms"]);
  assert.equal(entry.kind, "other");
  assert.equal(entry.status, 502);
  assert.ok(entry.elapsed_ms >= 0);
  assert.ok(!lines[0].includes("token-secret-chat-123"));
});

test("read-only GitHub GET retries 503 and 429, with bounded backoff", async () => {
  const statuses = [503, 429, 200], delays = [];
  let requests = 0;
  globalThis.fetch = async (_url, init) => {
    assert.equal(init.redirect, "manual");
    const status = statuses[requests++];
    return new Response(JSON.stringify({ ok: true }), { status });
  };
  const data = await githubJSON("https://api.github.com/repos/test/test", {}, 1024,
    delay => { delays.push(delay); });
  assert.deepEqual(data, { ok: true });
  assert.equal(requests, 3);
  assert.deepEqual(delays, [150, 300]);
});

test("GitHub 403 is not retried; 503 stops after three reads", async () => {
  let requests = 0, delays = 0;
  globalThis.fetch = async () => { requests++; return new Response("{}", { status: 403 }); };
  await assert.rejects(githubJSON("https://api.github.com/limits", {}, 1024, () => { delays++; }), /HTTP 403/);
  assert.equal(requests, 1);
  assert.equal(delays, 0);
  globalThis.fetch = async () => { requests++; return new Response("{}", { status: 503 }); };
  await assert.rejects(githubJSON("https://api.github.com/limits", {}, 1024, () => { delays++; }), /HTTP 503/);
  assert.equal(requests, 4);
  assert.equal(delays, 2);
});

test("GitHub redirects and malformed successful JSON are never retried", async () => {
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    return new Response("{", { status: 200 });
  };
  await assert.rejects(githubJSON("https://api.github.com/test", {}, 1024, () => {}), /Некорректный JSON/);
  assert.equal(requests, 1);
  globalThis.fetch = async () => {
    requests++;
    return new Response("", { status: 302, headers: { Location: "https://other.example/" } });
  };
  await assert.rejects(githubJSON("https://api.github.com/test", {}, 1024, () => {}), /Сервис временно недоступен/);
  assert.equal(requests, 2);
});

test("admin brute-force cap rejects bursts before reaching Telegram", async () => {
  let network = 0;
  globalThis.fetch = async () => { network++; throw Error("Must not call external API"); };
  for (let i = 0; i < 31; i++) {
    const response = await worker.fetch(new Request(origin + "/admin/status", {
      method: "POST", headers: { "CF-Connecting-IP": "192.0.2.170",
        "Content-Type": "application/json", Authorization: "Bearer bad" },
      body: JSON.stringify({ confirm: "status" }),
    }), env);
    assert.equal(response.status, i < 30 ? 403 : 429);
    if (i === 30) assert.equal(response.headers.get("Retry-After"), "60");
  }
  assert.equal(network, 0);
});

test("owner command cap leaves retries of completed updates working; Telegram send is never retried", async () => {
  let sent = 0;
  globalThis.fetch = async (url, init) => {
    assert.equal(init.redirect, "manual");
    if (String(url).includes("api.telegram.org")) {
      sent++;
      return new Response(JSON.stringify({ ok: true, result: { message_id: sent } }),
        { headers: { "Content-Type": "application/json" } });
    }
    throw Error("Unexpected network request");
  };
  const secret = await webhookSecret(env);
  const headers = { "Content-Type": "application/json",
    "X-Telegram-Bot-Api-Secret-Token": secret, "CF-Connecting-IP": "192.0.2.171" };
  const makeRequest = (id, text = "/start") => new Request(origin + "/telegram", {
    method: "POST", headers, body: JSON.stringify({ update_id: id,
      message: { from: { id: 42, is_bot: false }, chat: { id: 42, type: "private" }, text } }),
  });
  for (let i = 0; i < 90; i++) assert.equal((await worker.fetch(makeRequest(60000 + i), env)).status, 200);
  const limited = await worker.fetch(makeRequest(60100), env);
  assert.equal(limited.status, 429);
  assert.equal(limited.headers.get("Retry-After"), "60");
  assert.equal((await worker.fetch(makeRequest(60000), env)).status, 200);
  assert.equal(sent, 90);
});
