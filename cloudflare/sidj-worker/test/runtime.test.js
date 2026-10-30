import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

test("workerd performs outbound requests and refuses redirects with credentials", async () => {
  const security = await readFile(new URL("../src/security.js", import.meta.url), "utf8");
  const requests = [];
  const runtime = new Miniflare(convertV4MiniflareOptions({
    modules: true, host: "127.0.0.1", port: 0,
    compatibilityDate: "2026-10-30", telemetry: { enabled: false },
    script: security.replace(/^export /gm, "") + `\nexport default { async fetch(request) {
      try {
        return await fetchSafe("https://upstream.example" + new URL(request.url).pathname,
          { headers: { Authorization: "Bearer runtime-test-only" } });
      } catch { return new Response("rejected", { status: 502 }); }
    } };`,
    outboundService: async request => {
      requests.push(request.url);
      assert.equal(request.headers.get("authorization"), "Bearer runtime-test-only");
      return new URL(request.url).pathname === "/redirect"
        ? new Response(null, { status: 302, headers: { Location: "https://untrusted.example/" } })
        : new Response("upstream reached");
    },
  }));
  try {
    const ok = await runtime.dispatchFetch("https://worker.example/ok");
    assert.equal(ok.status, 200);
    assert.equal(await ok.text(), "upstream reached");
    const redirect = await runtime.dispatchFetch("https://worker.example/redirect");
    assert.equal(redirect.status, 502);
    assert.equal(await redirect.text(), "rejected");
    assert.deepEqual(requests, ["https://upstream.example/ok", "https://upstream.example/redirect"]);
  } finally { await runtime.dispose(); }
});
