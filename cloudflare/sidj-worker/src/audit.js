// B/S tech · owner-only, read-only audit dispatch. Never embed GitHub credentials.
import { fetchSafe } from "./security.js";

export const AUDIT_PROJECTS = Object.freeze([
  ["sidj","B/S SiDj — Telegram-бот"],
  ["agent","B/S SiDj — ИИ-разработчик"],
  ["reserve","B/S Reserve"],
  ["toolkit","B/S Excel Toolkit"],
  ["limits","B/S tech-Limits AI"],
  ["site","Сайт B/S tech"],
  ["codex","B/S Codex Installer"],
  ["gf_owner","G/F Storm ID — моя копия"],
  ["gf_alex","G/F Storm ID — копия Алексея"],
]);
const ALL=(1<<AUDIT_PROJECTS.length)-1;
const BS=(1<<7)-1;
const GF=ALL ^ BS;
const MAIN="berserkerxxxl/Berserker-SiDj-Technologies";
const NAME=/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/;
const selected=mask=>AUDIT_PROJECTS.flatMap(([id,label],i)=>mask&(1<<i)?[[id,label]]:[]);
const validMask=value=>/^(?:0|[1-9][0-9]{0,3})$/.test(value)&&Number(value)<=ALL?Number(value):null;

export function auditMenu(env,mask,say){
  if(!Number.isSafeInteger(mask)||mask<0||mask>ALL) mask=0;
  const rows=[];
  for(let i=0;i<AUDIT_PROJECTS.length;i+=2){
    rows.push(AUDIT_PROJECTS.slice(i,i+2).map(([id,label],j)=>{
      const k=i+j;
      return {text:(mask&(1<<k)?"☑️ ":"▫️ ")+label.slice(0,29),callback_data:"a:t:"+k+":"+mask};
    }));
  }
  rows.push([{text:"✅ Все 9",callback_data:"a:s:"+ALL},
    {text:"B/S tech (7)",callback_data:"a:s:"+BS},
    {text:"G/F (2)",callback_data:"a:s:"+GF}]);
  rows.push([{text:"🧹 Снять выбор",callback_data:"a:s:0"},
    {text:"🎓 Проверить выбранные ("+selected(mask).length+")",callback_data:"a:c:"+mask}]);
  return say(env,"🎓 Профессор · выборочный ИИ-аудит\nВыбрано: "+selected(mask).length+
    " из "+AUDIT_PROJECTS.length+
    "\n\nМожно выбрать отдельные программы или все. Две копии G/F проверяются независимо."+
    "\n🔒 Приватный код обрабатывается OpenRouter только после настройки отдельных ключей."+
    "\n📌 Проверяются фрагменты исходников, не весь проект целиком.",rows);
}

async function dispatch(repo,token,workflow,inputs){
  if(!token||!repo||!NAME.test(repo)||repo.includes("..")) return "не настроен (ключ или репозиторий)";
  const url="https://api.github.com/repos/"+repo+"/actions/workflows/"+workflow+"/dispatches";
  try{
    const r=await fetchSafe(url,{method:"POST",headers:{
      Authorization:"Bearer "+token,Accept:"application/vnd.github+json",
      "X-GitHub-Api-Version":"2022-11-28",
      "User-Agent":"BS-tech-SiDj-owner-audit",
      "Content-Type":"application/json"},
      body:JSON.stringify({ref:"main",inputs})},6000);
    await r.body?.cancel();
    return r.status===204?"запрос отправлен в GitHub Actions":
      "не запущен (GitHub HTTP "+r.status+")";
  }catch{
    return "не запущен (сеть или GitHub недоступны)";
  }
}

async function auditRun(env,mask,say) {
  const chosen=selected(mask);
  if(!chosen.length) return auditMenu(env,0,say);
  const codes=chosen.filter(([id])=>!id.startsWith("gf_")).map(([id])=>id);
  const groups=[
    ...(codes.length?[["B/S tech",MAIN,env.SIDJ_AUDIT_PUBLIC_TOKEN,"sidj-portfolio-ai-review.yml",{projects:codes.join(",")}]]:[]),
    ...(mask&(1<<7)?[["G/F — моя копия",env.SIDJ_AUDIT_OWNER_REPO,env.SIDJ_AUDIT_OWNER_TOKEN,"professor.yml",{scope:"source"}]]:[]),
    ...(mask&(1<<8)?[["G/F — Алексей",env.SIDJ_AUDIT_ALEX_REPO,env.SIDJ_AUDIT_ALEX_TOKEN,"professor.yml",{scope:"source"}]]:[])
  ];
  const results=await Promise.all(groups.map(async ([name,repo,token,workflow,inputs])=>{
    const outcome=await dispatch(repo,token,workflow,inputs);
    return {name,outcome,url:outcome.includes("запрос отправлен")?"https://github.com/"+repo+"/actions/workflows/"+workflow:null};
  }));
  const links=results.filter(r=>r.url).map(r=>[{text:"📋 "+r.name,url:r.url}]);
  return say(env,"🎓 Профессор · результаты запуска\n\n"+
    results.map(r=>r.name+": "+r.outcome).join("\n")+
    "\n\nЗапрос отправлен ≠ аудит завершён. Отказы OpenRouter не означают ошибки программ."+
    "\n🔒 Ни деплоя, ни правок исходников.",links);
}

export function auditAction(env,data,say){
  if(data==="audit") return auditMenu(env,0,say);
  const toggle=/^a:t:([0-8]):([0-9]{1,4})$/.exec(data);
  if(toggle){const mask=validMask(toggle[2]);return mask===null?auditMenu(env,0,say):auditMenu(env,mask^(1<<Number(toggle[1])),say);}
  const select=/^a:s:([0-9]{1,4})$/.exec(data);
  if(select){const mask=validMask(select[1]);return auditMenu(env,mask===null?0:mask,say);}
  const confirmation=/^a:c:([0-9]{1,4})$/.exec(data);
  if(confirmation){
    const mask=validMask(confirmation[1]);
    if(!mask) return auditMenu(env,0,say);
    return say(env,"🎓 Запустить аудит для "+selected(mask).length+" проектов?"+
      "\nБудут выполнены только разрешённые GitHub Actions. Приватные проекты передают фрагмент кода OpenRouter, если подключён ключ.",[
      [{text:"✅ Да, запустить",callback_data:"a:go:"+mask}],
      [{text:"↩️ Изменить выбор",callback_data:"a:s:"+mask}]
    ]);
  }
  const go=/^a:go:([0-9]{1,4})$/.exec(data);
  if(go){const mask=validMask(go[1]);if(mask) return auditRun(env,mask,say);}
  return say(env,"Некорректный выбор. Открой /audit.");
}
