import {
  BOT_USERNAME, PublicError, response, checkConfig, canonicalOrigin,
  equalSecret, webhookSecret, boundedJSON, timeMSK,
} from "./security.js";

function setupPage() {
  const nonce = crypto.randomUUID().replaceAll("-", "");
  const html = `<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>СиДжи — подключение Telegram</title>
<style nonce="${nonce}">
body{font:17px/1.55 system-ui;margin:40px auto;padding:0 20px;max-width:760px;background:#101725;color:#edf3ff}
h1{font-size:28px}input{display:block;box-sizing:border-box;width:100%;padding:12px;margin:8px 0 18px;background:#1a263b;color:white;border:1px solid #93a3bd;border-radius:8px}
button{font:inherit;border:0;border-radius:8px;padding:12px 16px;margin:5px 5px 5px 0;cursor:pointer;background:#abd8ff;color:#101725}button:disabled{opacity:.5}
#rollback{background:#f4bf9d}pre{white-space:pre-wrap;word-break:break-word;background:#1a263b;padding:18px;border-radius:8px}small{color:#b8c5da}
</style>
<h1>🤖 СиДжи · B/S tech</h1>
<p>Панель владельца для проверки и переключения Telegram webhook.</p>
<p>Перед подключением добавь в Cloudflare секреты <b>SIDJ_TELEGRAM_BOT_TOKEN</b>, <b>SIDJ_TELEGRAM_CHAT_ID</b>, <b>SIDJ_ADMIN_TOKEN</b> и переменную <b>SIDJ_PUBLIC_URL</b>.</p>
<p>SIDJ_ADMIN_TOKEN — отдельный случайный пароль панели, 32–128 символов: латинские буквы, цифры, дефис, подчёркивание. Токен Telegram в эту форму не вводится.</p>
<label for="admin">Пароль панели (SIDJ_ADMIN_TOKEN)</label>
<input id="admin" type="password" autocomplete="off" spellcheck="false" maxlength="128">
<button id="status" type="button">Проверить подключение</button>
<button id="activate" type="button">Подключить webhook</button>
<button id="commands" type="button">Обновить меню команд</button>
<button id="rollback" type="button">Откатить на опрос</button>
<p><small>«Обновить меню команд» изменяет только список команд Telegram, не переключает webhook.</small></p>
<p><small>Пароль передаётся только этому Worker по HTTPS и очищается из поля после запроса. Браузер не сохраняет его в хранилище страницы.</small></p>
<p>До переключения дождись окончания запущенного опроса GitHub. После подключения проверь команды и кнопки в Telegram; только затем отключай старое расписание. При откате старый workflow должен быть включён.</p>
<pre id="result" role="status" aria-live="polite">Проверка ещё не выполнялась.</pre>
<script nonce="${nonce}">
const field=document.getElementById('admin'),output=document.getElementById('result');
for(const action of ['status','activate','commands','rollback'])document.getElementById(action).addEventListener('click',async()=>{
  if(!/^[A-Za-z0-9_-]{32,128}$/.test(field.value)){output.textContent='Введи пароль панели из Cloudflare (32–128 символов).';return;}
  if(action==='activate'&&!confirm('Подключить webhook? Дождись окончания запущенного опроса GitHub. Очередь Telegram будет сохранена.'))return;
  if(action==='rollback'&&!confirm('Удалить webhook и вернуться к опросу? Сначала убедись, что старый workflow включён. Очередь сохранится.'))return;
  let key=field.value;field.value='';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);output.textContent='Выполняю запрос…';
  try{const r=await fetch('/admin/'+action,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+key},body:JSON.stringify({confirm:action}),credentials:'omit',redirect:'error'});key='';output.textContent=await r.text();}
  catch{key='';output.textContent='Нет подтверждения операции. Проверь подключение перед повтором.';}
  finally{document.querySelectorAll('button').forEach(b=>b.disabled=false);}
});
</script></html>`;
  return response(html, 200, {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": "default-src 'none'; script-src 'nonce-" + nonce + "'; style-src 'nonce-" + nonce + "'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  });
}

async function botIdentity(env, telegram) {
  const me = await telegram(env, "getMe", {});
  if (me.is_bot !== true || me.username?.toLowerCase() !== BOT_USERNAME) {
    throw new PublicError("Секрет относится к другому боту. Webhook не изменён.", 409);
  }
  const owner = await telegram(env, "getChat", { chat_id: env.SIDJ_TELEGRAM_CHAT_ID });
  if (owner.type !== "private" || String(owner.id) !== String(env.SIDJ_TELEGRAM_CHAT_ID)) {
    throw new PublicError("SIDJ_TELEGRAM_CHAT_ID должен указывать на личный чат владельца.", 409);
  }
}

function webhookStatus(info, target) {
  return "Webhook: " + (info.url === target ? "подключён к этому Worker" : info.url ? "подключён к другому адресу" : "не подключён; доступен опрос GitHub") +
    "\nОжидают доставки: " + (Number(info.pending_update_count) || 0) +
    (info.last_error_date ? "\nПоследняя ошибка доставки: " + timeMSK(info.last_error_date * 1000) : "") +
    "\nПроверено: " + timeMSK(new Date().toISOString()) + " МСК";
}

export async function adminRoute(request, env, telegram, commands) {
  const url = new URL(request.url);
  if (url.pathname === "/setup") {
    if (request.method !== "GET") return response("Method not allowed", 405, { Allow: "GET" });
    return setupPage();
  }
  if (!["/admin/status", "/admin/activate", "/admin/commands", "/admin/rollback"].includes(url.pathname)) return response("Not found", 404);
  if (request.method !== "POST") return response("Method not allowed", 405, { Allow: "POST" });
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(env.SIDJ_ADMIN_TOKEN || "")) return response("Панель выключена: настрой SIDJ_ADMIN_TOKEN в Secrets.", 503);
  const bearer = request.headers.get("authorization") || "";
  if (!bearer.startsWith("Bearer ") || !await equalSecret(bearer.slice(7), env.SIDJ_ADMIN_TOKEN)) return response("Forbidden", 403);
  const origin = canonicalOrigin(env);
  if (url.origin !== origin || (request.headers.has("origin") && request.headers.get("origin") !== origin) ||
      request.headers.get("sec-fetch-site") === "cross-site") return response("Forbidden", 403);
  if (!/^application\/json(?:;|$)/i.test(request.headers.get("content-type") || "")) return response("JSON required", 415);
  const input = await boundedJSON(request, 1024), action = url.pathname.split("/").at(-1);
  if (input?.confirm !== action) return response("Операция не подтверждена.", 400);
  checkConfig(env);
  await botIdentity(env, telegram);
  const target = origin + "/telegram", current = await telegram(env, "getWebhookInfo", {});
  if (action === "status") return response(webhookStatus(current, target));
  if (action === "commands") {
    if (current.url !== target) return response("Текущий webhook не принадлежит этому Worker. Меню не изменено.", 409);
    await telegram(env, "setMyCommands", { commands, scope: { type: "chat", chat_id: Number(env.SIDJ_TELEGRAM_CHAT_ID) } });
    return response("✅ Меню Telegram обновлено. Webhook и секреты не изменены.");
  }
  if (action === "rollback") {
    if (current.url && current.url !== target) return response("У бота другой webhook. Откат отменён.", 409);
    await telegram(env, "deleteWebhook", { drop_pending_updates: false });
    const info = await telegram(env, "getWebhookInfo", {});
    if (info.url) throw new PublicError("Telegram не подтвердил удаление webhook.");
    return response("Webhook удалён. Очередь сохранена. Включённый workflow вернётся к опросу.\n" + webhookStatus(info, target));
  }
  if (current.url && current.url !== target) return response("У бота уже есть другой webhook. Переключение отменено для защиты действующего обработчика.", 409);
  // Commands are configured first. setWebhook is the last state-changing step.
  await telegram(env, "setMyCommands", { commands, scope: { type: "chat", chat_id: Number(env.SIDJ_TELEGRAM_CHAT_ID) } });
  // Always refresh secret_token, including when the URL did not change after rotation.
  await telegram(env, "setWebhook", { url: target, secret_token: await webhookSecret(env),
    allowed_updates: ["message", "callback_query"], max_connections: 1, drop_pending_updates: false });
  const info = await telegram(env, "getWebhookInfo", {});
  if (info.url !== target) throw new PublicError("Telegram не подтвердил адрес webhook. Проверь подключение.");
  return response("СиДжи подключён к Cloudflare. Очередь Telegram сохранена.\n" + webhookStatus(info, target) +
    "\nПроверь команды, кнопки и получение файла. После успешной проверки отключи старый workflow опроса.");
}
