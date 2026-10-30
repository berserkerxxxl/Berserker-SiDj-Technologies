// B/S tech · СиДжи — мгновенный Telegram webhook на Cloudflare Workers.
// Настройки: SIDJ_TELEGRAM_BOT_TOKEN и SIDJ_TELEGRAM_CHAT_ID (Secret),
// SIDJ_PUBLIC_URL (Text, точный адрес Worker в Cloudflare).
const REPO="berserkerxxxl/Berserker-SiDj-Technologies";
const RAW="https://raw.githubusercontent.com/"+REPO+"/main/";
const API="https://api.github.com/repos/"+REPO;
const MAX_FILE=49*1024*1024;
const USERNAME="bs_sidj_bot";
const COMMANDS=[
  ["start","Приветствие и возможности"],
  ["projects","Все программы B/S tech"],
  ["project","Описание выбранной программы"],
  ["download","Скачать программу в Telegram"],
  ["status","Состояние всех проектов"],
  ["builds","Последние сборки программ"],
  ["errors","Ошибки сборок"],
  ["help","Справка на русском"]
].map(([command,description])=>({command,description}));
const HELP="🤖 СиДжи | B/S tech\n\n"
+"/projects — каталог разработок\n"
+"/project — описание программы\n"
+"/download — получить файл\n"
+"/status — состояние проектов\n"
+"/builds — последние сборки\n"
+"/errors — ошибки сборок\n"
+"/help — справка\n\n"
+"⚡ Отвечаю без пятиминутного ожидания.\n🔒 Команды доступны только владельцу.";

function keyRows(projects){return {inline_keyboard:projects.map(p=>[{text:p.name,callback_data:"p:"+p.id}])};}
function isOwner(env,chat){return chat?.type==="private"&&String(chat?.id)===String(env.SIDJ_TELEGRAM_CHAT_ID);}
function okLink(url){return typeof url==="string"&&/^https:\/\/github\.com\/berserkerxxxl\/Berserker-SiDj-Technologies\/actions\/runs\/[0-9]+$/.test(url);}
function timeMSK(s){const d=new Date(s||"");return Number.isNaN(d.getTime())?"неизвестно":new Intl.DateTimeFormat("ru-RU",{timeZone:"Europe/Moscow",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);}
function state(run){return {success:"✅ Успешно",failure:"❌ Ошибка",timed_out:"⏱ Превышено время",cancelled:"⚪ Отменено",skipped:"⏭ Пропущено"}[run.conclusion]||({queued:"🕒 Ожидание",in_progress:"🔄 Выполняется"}[run.status]||"ℹ️ Нет результата");}
function checkEnv(env){return !!(env.SIDJ_TELEGRAM_BOT_TOKEN&&env.SIDJ_TELEGRAM_CHAT_ID);}
async function secretToken(env){const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode("B/S-SiDj-webhook:"+env.SIDJ_TELEGRAM_BOT_TOKEN));return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");}
async function tg(env,method,data) {
  let r;
  try{r=await fetch("https://api.telegram.org/bot"+env.SIDJ_TELEGRAM_BOT_TOKEN+"/"+method,{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)
  });}catch(_){throw Error("Нет связи с Telegram");}
  if(!r.ok)throw Error("Telegram: HTTP "+r.status);
  const v=await r.json();
  if(!v.ok)throw Error("Telegram отклонил запрос "+method);
  return v.result;
}
async function say(env,message,buttons){
  const data={chat_id:env.SIDJ_TELEGRAM_CHAT_ID,text:String(message).slice(0,3900),disable_web_page_preview:true};
  if(buttons)data.reply_markup={inline_keyboard:buttons};
  return tg(env,"sendMessage",data);
}
async function catalog(){
  const r=await fetch(RAW+"automation/sidj_projects.json",{cf:{cacheEverything:true,cacheTtl:60}});
  if(!r.ok)throw Error("Не удалось открыть каталог GitHub");
  const o=await r.json();
  if(!Array.isArray(o.projects))throw Error("Каталог разработок недоступен");
  return o.projects;
}
async function getProject(id){return (await catalog()).find(p=>p.id===id);}
async function showProjects(env){
  const p=await catalog();
  await say(env,"📂 B/S tech — наши разработки\n\n"+p.map(x=>"• "+x.name+" · "+x.version).join("\n")+"\n\nВыбери программу:",keyRows(p).inline_keyboard);
}
async function showProject(env,id){
  const p=await getProject(id);
  if(!p)return showProjects(env);
  const buttons=(p.downloads||[]).map(d=>[{text:"📥 "+d.label,callback_data:"d:"+p.id+":"+d.id}]);
  buttons.push([{text:"◀️ Все проекты",callback_data:"projects"}]);
  await say(env,"📦 "+p.name+" · "+p.version+"\n\n"+p.description+"\n\nℹ️ "+p.notes+"\n\n🌐 "+p.page+"\n\nВыбери файл:",buttons);
}
async function sendFile(env,pid,did){
  const p=await getProject(pid);
  const entry=p?.downloads?.find(d=>d.id===did);
  if(!entry){await say(env,"Файл не найден в каталоге. Открой /projects.");return;}
  const path=entry.path;
  if(!/^(apps|downloads)\/[A-Za-z0-9._/-]+$/.test(path)||path.split("/").some(x=>x===".."||x==="."))throw Error("Некорректный путь файла");
  const url=RAW+path.split("/").map(encodeURIComponent).join("/");
  const filename=path.split("/").at(-1);
  const fallback=[[{text:"⬇️ Скачать из GitHub",url}]];
  let r;
  try{r=await fetch(url);}catch(_){await say(env,"GitHub временно недоступен. Скачай по ссылке:",fallback);return;}
  if(!r.ok){await say(env,"Файл недоступен. Проверь страницу программы:\n"+p.page);return;}
  const size=Number(r.headers.get("content-length")||0);
  if(size>MAX_FILE){await say(env,"Большой файл: используй прямую ссылку.",fallback);return;}
  const bytes=await r.arrayBuffer();
  if(bytes.byteLength>MAX_FILE){await say(env,"Файл превышает лимит отправки в Telegram.",fallback);return;}
  let expected=entry.sha256||"";
  if(!expected && /\.(zip|tar\.gz)$/.test(filename)){
    try{const sha=await fetch(url+".sha256");if(sha.ok)expected=(await sha.text()).trim().split(/\s+/)[0];}
    catch(_){}
  }
  if(expected){
    const digest=await crypto.subtle.digest("SHA-256",bytes);
    const hash=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
    if(hash.toLowerCase()!==expected.toLowerCase()){await say(env,"⛔ Контрольная сумма не совпала. Файл не отправлен.");return;}
  }
  const form=new FormData();
  form.set("chat_id",String(env.SIDJ_TELEGRAM_CHAT_ID));
  form.set("caption","📦 "+p.name+" · "+p.version+"\n"+entry.label);
  form.set("document",new File([bytes],filename,{type:"application/octet-stream"}),filename);
  try{
    const sent=await fetch("https://api.telegram.org/bot"+env.SIDJ_TELEGRAM_BOT_TOKEN+"/sendDocument",{method:"POST",body:form});
    if(!sent.ok||!(await sent.json()).ok)throw Error("Отправка не удалась");
  }catch(_){await say(env,"Не получилось отправить файл вложением. Скачай напрямую:",fallback);}
}
async function gh(path){
  const r=await fetch(API+path,{
    headers:{"Accept":"application/vnd.github+json","User-Agent":"BS-tech-SiDj"},
    cf:{cacheEverything:true,cacheTtl:60}
  });
  if(!r.ok)throw Error("GitHub API: HTTP "+r.status);
  return r.json();
}
async function runs(p,limit=12){
  const w=(p.workflows||[]).filter(x=>/^[A-Za-z0-9._-]+\.ya?ml$/.test(x));
  const all=await Promise.all(w.map(name=>gh("/actions/workflows/"+name+"/runs?per_page="+Math.min(limit,25))));
  return all.flatMap(a=>a.workflow_runs||[]).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))).slice(0,limit);
}
async function reason(run){
  if(run.conclusion==="timed_out")return "Превышено время выполнения";
  if(run.conclusion!=="failure")return "";
  try{
    const o=await gh("/actions/runs/"+run.id+"/jobs?per_page=100");
    const job=(o.jobs||[]).find(j=>j.conclusion==="failure");
    if(!job)return "Один из этапов сборки завершился ошибкой";
    const step=(job.steps||[]).find(x=>x.conclusion==="failure");
    return "Не прошёл этап: "+job.name+(step?" → "+step.name:"");
  }catch(_){return "Один из этапов сборки завершился ошибкой";}
}
async function formatted(run,p){
  const text=p.name+" · "+p.version+": "+state(run)+"\nМосква: "+timeMSK(run.updated_at||run.created_at);
  const why=await reason(run);
  return text+(why?"\nПричина: "+why:"");
}
function errorButtons(entries){
  return entries.filter(([p,r])=>["failure","timed_out"].includes(r.conclusion)&&okLink(r.html_url))
    .map(([p,r])=>[{text:"🔍 Посмотреть ошибку #"+r.run_number,url:r.html_url}]);
}
async function status(env){
  const ps=await catalog();
  const entries=await Promise.all(ps.map(async p=>({p,r:p.workflows?.length?(await runs(p,3))[0]:null})));
  const lines=["📊 B/S tech — состояние проектов"];
  for(const {p,r} of entries){
    if(!p.workflows?.length)lines.push("📦 "+p.name+" · "+p.version+"\nОпубликован. Автосборка не настроена.");
    else if(r)lines.push(await formatted(r,p));
    else lines.push(p.name+": нет данных о сборке.");
  }
  await say(env,lines.join("\n\n"),[
    [{text:"📂 Каталог программ",callback_data:"projects"}],
    ...errorButtons(entries.filter(x=>x.r).map(x=>[x.p,x.r]))
  ]);
}
async function recent(env,onlyErrors){
  const ps=(await catalog()).filter(p=>p.workflows?.length);
  const lists=await Promise.all(ps.map(p=>runs(p,20)));
  const entries=ps.flatMap((p,i)=>lists[i].map(r=>[p,r]));
  const sorted=entries.filter(([p,r])=>!onlyErrors||["failure","timed_out"].includes(r.conclusion))
    .sort((a,b)=>String(b[1].created_at).localeCompare(String(a[1].created_at))).slice(0,5);
  if(!sorted.length){await say(env,onlyErrors?"✅ В доступной истории ошибок нет.":"Сборок пока нет.");return;}
  const contents=await Promise.all(sorted.map(([p,r])=>formatted(r,p)));
  await say(env,(onlyErrors?"🚨 Ошибки сборок":"🔧 Последние сборки")+"\n\n"+contents.join("\n\n"),errorButtons(sorted));
}
async function command(env,txt){
  const words=String(txt||"").trim().split(/\s+/);
  let name=(words[0]||"/help").toLowerCase().split("@");
  if(name.length>1&&name[1]!==USERNAME)return;
  const cmd=name[0];
  if(cmd==="/start"||cmd==="/help")return say(env,HELP,[[{text:"📂 Все проекты",callback_data:"projects"}],[{text:"📥 Скачать",callback_data:"downloads"}]]);
  if(cmd==="/projects")return showProjects(env);
  if(cmd==="/project")return showProject(env,words[1]||"");
  if(cmd==="/download"){
    if(words[1]&&words[2])return sendFile(env,words[1],words[2]);
    if(words[1])return showProject(env,words[1]);
    return say(env,"📥 Выбери программу:",keyRows(await catalog()).inline_keyboard);
  }
  if(cmd==="/status")return status(env);
  if(cmd==="/builds")return recent(env,false);
  if(cmd==="/errors")return recent(env,true);
  return say(env,"Неизвестная команда. Напиши /help");
}
async function update(env,body){
  const callback=body.callback_query;
  if(callback){
    const chat=callback.message?.chat;
    if(!isOwner(env,chat))return;
    await tg(env,"answerCallbackQuery",{callback_query_id:callback.id});
    const data=callback.data||"";
    if(data==="projects")return showProjects(env);
    if(data==="downloads")return say(env,"📥 Выбери программу:",keyRows(await catalog()).inline_keyboard);
    if(/^p:[a-z0-9_]+$/.test(data))return showProject(env,data.split(":")[1]);
    if(/^d:[a-z0-9_]+:[a-z0-9_]+$/.test(data))return sendFile(env,...data.split(":").slice(1));
    return;
  }
  const chat=body.message?.chat;
  if(!isOwner(env,chat))return;
  if(body.message?.text)return command(env,body.message.text);
}
async function activate(env,request){
  if(!checkEnv(env))return new Response("Сначала добавь Telegram Secrets в Cloudflare.",{status:503});
  let configured;
  try{configured=new URL(env.SIDJ_PUBLIC_URL);}catch(_){return new Response("Добавь SIDJ_PUBLIC_URL в Variables (адрес https://...workers.dev).",{status:503});}
  if(configured.protocol!=="https:"||configured.pathname!=="/"||configured.search||configured.hash)return new Response("SIDJ_PUBLIC_URL должен быть HTTPS origin с завершающим /",{status:400});
  if(configured.origin!==new URL(request.url).origin)return new Response("Открывай канонический адрес SIDJ_PUBLIC_URL.",{status:403});
  const target=configured.origin+"/telegram";
  const current=await tg(env,"getWebhookInfo",{});
  const token=await secretToken(env);
  if(current.url!==target){
    await tg(env,"setWebhook",{url:target,secret_token:token,drop_pending_updates:false,allowed_updates:["message","callback_query"]});
  }
  await tg(env,"setMyCommands",{commands:COMMANDS});
  return new Response(current.url===target?"СиДжи уже подключён. Webhook активен.":"СиДжи подключён к Cloudflare! Webhook активен.",{headers:{"Content-Type":"text/plain; charset=utf-8"}});
}
export default {
  async fetch(request,env,ctx){
    const url=new URL(request.url);
    if(url.pathname==="/activate"&&request.method==="GET"){
      try{return await activate(env,request);}
      catch(e){return new Response("Не удалось активировать webhook: "+e.message,{status:502});}
    }
    if(url.pathname==="/telegram"&&request.method==="POST"){
      if(!checkEnv(env))return new Response("Not configured",{status:503});
      const expected=await secretToken(env);
      const actual=request.headers.get("X-Telegram-Bot-Api-Secret-Token")||"";
      if(actual!==expected)return new Response("Forbidden",{status:403});
      let body;
      try{body=await request.json();}
      catch(_){return new Response("Bad request",{status:400});}
      ctx.waitUntil(update(env,body).catch(async e=>{
        try{await say(env,"⚠️ Ошибка обработки: "+String(e.message).slice(0,150));}
        catch(_){}
      }));
      return new Response("OK");
    }
    if(url.pathname==="/"&&request.method==="GET")
      return new Response("🤖 СиДжи | B/S tech\nWorker готов. Для подключения открой /activate после добавления секретов и SIDJ_PUBLIC_URL.",{headers:{"Content-Type":"text/plain; charset=utf-8"}});
    return new Response("Not found",{status:404});
  }
};
