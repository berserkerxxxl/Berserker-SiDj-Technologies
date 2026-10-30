// ==UserScript==
// @name         B/S tech-Limits AI — ChatGPT + Gemini
// @namespace    bs-tech-limits-ai
// @version      3.9.0
// @description  B/S tech-Limits AI: единая панель для ChatGPT и Gemini, лимиты Codex, навигация и часы МСК.
// @match        https://chatgpt.com/*
// @match        https://gemini.google.com/*
// @noframes
// @run-at       document-idle
// @grant        none
// ==/UserScript==
function init() {
  'use strict';
  const host = location.hostname;
  const gpt = host === 'chatgpt.com';
  if (!gpt && host !== 'gemini.google.com') return;
  const ID = 'bs-tech-limits-ai-v39';
  if (document.getElementById(ID)) return;
  if (!document.body) { document.addEventListener('DOMContentLoaded', init, {once:true}); return; }
  // Прежние экземпляры от предыдущих редакций
  document.querySelectorAll('#sidj-unified-v31,#bs-tech-limits-ai-v33,#bs-tech-limits-ai-v34,#bs-tech-limits-ai-v35,#bs-tech-limits-ai-v36,#bs-tech-limits-ai-v37,#bs-tech-limits-ai-v38').forEach(node => node.remove());
  const TZ = 'Europe/Moscow';
  const STORE = 'sidj-unified-v31:' + host + ':'; // сохраняем пользовательские настройки
  const get = (k, fallback) => { try { return JSON.parse(localStorage.getItem(STORE + k)) ?? fallback; } catch { return fallback; } };
  const set = (k, v) => { try { localStorage.setItem(STORE + k, JSON.stringify(v)); } catch {} };
  const state = {
    collapsed: get('collapsed', false), navHidden: false,
    auto: get('auto', true), showClock: true,
    position: get('position', null),
    gemFiveMax: Math.max(1, Number(get('gemFiveMax', 50)) || 50),
    gemWeekMax: Math.max(1, Number(get('gemWeekMax', 300)) || 300)
  };
  let navTarget = null, navStyle = null, navPriority = '', navScanPending = false, busy = false;
  const clock = () => new Date().toLocaleTimeString('ru-RU', {timeZone:TZ,hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
  const css = document.createElement('style');
  css.textContent = `
    #${ID} { position:fixed;bottom:76px;right:18px;z-index:2147483640;width:260px;max-width:calc(100vw - 16px);box-sizing:border-box;
      border-radius:13px;border:1px solid rgba(140,140,140,.35);box-shadow:0 5px 22px #0004;
      background:#252830;color:#f4f4f5;padding:9px 10px;font:12px/1.4 system-ui,Arial,sans-serif }
    #${ID}[data-light="1"]{background:#fff;color:#1e232b}
    #${ID} *{box-sizing:border-box}
    #${ID} .su-head{display:flex;justify-content:space-between;align-items:center;gap:4px;user-select:none;min-width:0}
    #${ID} .su-title{flex:1 1 auto;font-size:12px;font-weight:700;cursor:grab;touch-action:none;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    #${ID} .su-brand{flex:1 1 auto;min-width:0}
    #${ID} .su-version{font-size:10px;line-height:1.3;opacity:.75;margin-top:1px}
    #${ID} .su-actions{display:flex;gap:2px;flex:0 0 auto}
    #${ID} button{min-width:23px;min-height:23px;font:inherit;color:inherit;border:1px solid #8885;background:#8882;border-radius:6px;padding:2px 6px;cursor:pointer}
    #${ID} button:hover{background:#8884}
    #${ID} button:focus-visible,#${ID} input:focus-visible{outline:2px solid #7dbcf6;outline-offset:2px}
    #${ID} .su-body{padding-top:7px}
    #${ID} .su-line{display:flex;justify-content:space-between;gap:8px;margin-top:6px}
    #${ID} .su-track{height:5px;border-radius:30px;overflow:hidden;background:#8885;margin-top:3px}
    #${ID} .su-fill{height:100%;width:0;background:#34c88a;transition:width .25s}
    #${ID} .su-muted{font-size:10px;opacity:.72;margin-top:3px}
    #${ID} .su-footer{display:flex;align-items:center;justify-content:flex-end;gap:6px;margin-top:8px;min-width:0}
    #${ID} .su-status{font-size:10px;opacity:.75;text-align:right;overflow-wrap:anywhere;min-width:0}
    #${ID} .su-footer button{font-size:13px;min-width:20px;min-height:20px;padding:0 3px;flex:0 0 auto}
    #${ID}.su-collapsed{width:260px}
    #${ID}.su-collapsed .su-body{display:none}

    @media(max-width:500px){#${ID}{max-width:calc(100vw - 16px)}}
  `;
  (document.head || document.documentElement).append(css);
  const panel = document.createElement('aside');
  panel.id = ID;
  // Fallback styling if Gemini removes an injected stylesheet.
  Object.assign(panel.style, {position:'fixed',right:'18px',bottom:'76px',zIndex:'2147483640'});
  panel.setAttribute('aria-label','B/S tech-Limits AI');
  // Не используем innerHTML: совместимо с Gemini при Trusted Types CSP.
  const node = (tag, className = '', textValue = '', nodeId = '') => {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (nodeId) n.id = nodeId;
    if (textValue) n.textContent = textValue;
    return n;
  };
  const head = node('div', 'su-head');
  const brand = node('div', 'su-brand', '', 'su-drag');
  brand.title = 'Перетащить панель';
  brand.append(node('div', 'su-title', '⚡ B/S tech-Limits AI · ' + (gpt ? 'ChatGPT' : 'Gemini')));
  brand.append(node('div', 'su-version', 'Вер. 3.9'));
  const actions = node('div', 'su-actions');
  const fold = node('button', '', state.collapsed ? '+' : '−', 'su-fold');
  fold.type = 'button'; fold.title = 'Свернуть';
  actions.append(fold); head.append(brand, actions);
  const body = node('div', 'su-body');
  if (gpt) {
    const usageBox = node('div', '', '', 'su-usage');
    for (const [key, label] of [['five', '5 часов'], ['week', 'Неделя']]) {
      const line = node('div', 'su-line');
      line.append(node('span', '', label), node('b', '', '—', `su-${key}-val`));
      const track = node('div', 'su-track');
      track.append(node('div', 'su-fill', '', `su-${key}-bar`));
      usageBox.append(line, track, node('div', 'su-muted', '', `su-${key}-reset`));
    }
    body.append(usageBox);
  } else {
    const usageBox = node('div', '', '', 'su-usage');
    usageBox.append(node('div', 'su-muted', 'Локальный подсчёт · не лимиты Google'));
    for (const [key, label] of [['five', '5 часов'], ['week', 'Неделя']]) {
      const line = node('div', 'su-line');
      line.append(node('span', '', label), node('b', '', '—', `su-${key}-val`));
      const track = node('div', 'su-track');
      track.append(node('div', 'su-fill', '', `su-${key}-bar`));
      usageBox.append(line, track, node('div', 'su-muted', '', `su-${key}-reset`));
    }
    body.append(usageBox);
  }
  const footer = node('div', 'su-footer');
  const reload = node('button', '', '↻', 'su-reload');
  reload.type = 'button'; reload.title = 'Обновить';
  if (!gpt) {
    const config = node('button', '', '⚙', 'su-cfg');
    config.type = 'button'; config.title = 'Настроить локальные пороги';
    footer.append(config);
  }
  footer.append(reload, node('span', 'su-status', 'Готово', 'su-status'));
  body.append(footer); panel.append(head, body);
  (document.body || document.documentElement).append(panel);
  const el = id => panel.querySelector('#' + id);
  const status = msg => { el('su-status').textContent = msg; };
  const place = () => {
    if (state.position && Number.isFinite(state.position.x) && Number.isFinite(state.position.y)) {
      panel.style.left = Math.max(0, Math.min(window.innerWidth - 60, state.position.x)) + 'px';
      panel.style.top = Math.max(0, Math.min(window.innerHeight - 35, state.position.y)) + 'px';
      panel.style.right = 'auto'; panel.style.bottom = 'auto';
    }
  };
  if (state.collapsed) panel.classList.add('su-collapsed');
  const updateClock = () => {};
  const syncTheme = () => {
    const dark = document.documentElement.classList.contains('dark') ||
      (getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)') ||
      (matchMedia('(prefers-color-scheme: dark)').matches && !document.documentElement.classList.contains('light'));
    panel.dataset.light = dark ? '0' : '1';
  };
  syncTheme(); updateClock(); place();
  // Не позволяем сохранённым координатам полностью увести панель за экран.
  const ensureVisible = () => {
    const r=panel.getBoundingClientRect();
    if(r.right<60 || r.left>innerWidth-60 || r.bottom<35 || r.top>innerHeight-35){
      state.position=null;set('position',null);panel.style.left='';panel.style.top='';panel.style.right='18px';panel.style.bottom='76px';
    }
  };
  ensureVisible();

  // Only the ChatGPT origin is queried; tokens are never persisted or logged.
  function jwtClaims(token) {
    try { const p=token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'); return JSON.parse(atob(p+'='.repeat((4-p.length%4)%4))); }
    catch { return {}; }
  }
  async function json(url,options={}) {
    const response=await fetch(url,{credentials:'include',cache:'no-store',...options});
    if(!response.ok) throw Error('HTTP '+response.status);
    return response.json();
  }
  async function usage() {
    const session=await json('/api/auth/session');
    const token=session?.accessToken;
    if(!token) throw Error('Сессия не предоставляет токен');
    const claim=jwtClaims(token)['https://api.openai.com/auth'] || {};
    const account=session?.account?.id || session?.account_id || session?.user?.account_id || claim.chatgpt_account_id;
    if(!account) throw Error('Не определён аккаунт');
    return json('/backend-api/wham/usage',{headers:{Accept:'application/json',Authorization:'Bearer '+token,
      'ChatGPT-Account-Id':account,'OpenAI-Beta':'codex-1',originator:'codex_cli_rs'}});
  }
  function remaining(w) {
    if(!w) return null;
    const used=Number(w.used_percent);
    return Number.isFinite(used) ? Math.round(Math.max(0,Math.min(100,100-used))) : null;
  }
  function resetText(w,short) {
    const epoch=Number(w?.reset_at);
    if(!Number.isFinite(epoch)||epoch<=0) return '';
    const d=new Date(epoch*1000), total=Math.max(0,Math.ceil((d-Date.now())/60000));
    const hh=String(Math.floor((total%1440)/60)).padStart(2,'0');
    const mm=String(total%60).padStart(2,'0');
    if(short) return `Через ${Math.floor(total/60)}:${mm} · ${d.toLocaleTimeString('ru-RU',{timeZone:TZ,hour:'2-digit',minute:'2-digit',hourCycle:'h23'})} МСК`;
    return `Через ${Math.floor(total/1440)} д ${hh}:${mm} · ${d.toLocaleDateString('ru-RU',{timeZone:TZ})}`;
  }
  function draw(w,key,short) {
    const pct=remaining(w);
    el(`su-${key}-val`).textContent=pct===null?'—':pct+'%';
    el(`su-${key}-bar`).style.width=(pct??0)+'%';
    el(`su-${key}-reset`).textContent=pct===null?'':resetText(w,short);
  }
  const FIVE_MS = 5 * 3600000, WEEK_MS = 7 * 86400000;
  function gemTimestamps() {
    const now = Date.now();
    const raw = get('gem_timestamps', []);
    const list = Array.isArray(raw) ? raw.filter(x => Number.isFinite(x) && x <= now && now-x < WEEK_MS).sort((a,b) => a-b) : [];
    if (!Array.isArray(raw) || list.length !== raw.length) set('gem_timestamps', list);
    return list;
  }
  function drawGemini() {
    const now = Date.now(), all = gemTimestamps();
    for (const [key, duration, max, short] of [['five', FIVE_MS, state.gemFiveMax, true], ['week', WEEK_MS, state.gemWeekMax, false]]) {
      const list = all.filter(ts => now-ts < duration);
      const used = list.length;
      const pct = Math.max(0, Math.min(100, Math.round(100 * (1-used/max))));
      el(`su-${key}-val`).textContent = `${pct}% (${used}/${max})`;
      el(`su-${key}-bar`).style.width = pct + '%';
      el(`su-${key}-reset`).textContent = list.length ?
        ('Первый запрос выйдет из окна: ' + resetText({reset_at: Math.floor((list[0]+duration)/1000)},short)) : 'Запросов не зафиксировано';
    }
  }
  function recordGeminiPrompt() {
    const now = Date.now();
    const list = gemTimestamps();
    if (list.length && now-list[list.length-1] < 1200) return; // защита от двойного события
    list.push(now); set('gem_timestamps', list);
    drawGemini(); status('Учтено · ' + clock() + ' МСК');
  }
  // Ловим отправку из редактора Gemini без изменения fetch/XHR и без чтения содержимого сообщений.
  if (!gpt) {
    const isComposer = el => Boolean(el && el.closest && el.closest('rich-textarea, [contenteditable="true"], [role="textbox"], form'));
    document.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && isComposer(e.target)) recordGeminiPrompt();
    }, true);
    document.addEventListener('click', e => {
      const button = e.target.closest?.('button');
      if (!button) return;
      const label = ((button.getAttribute('aria-label') || '')+' '+(button.getAttribute('data-test-id') || '')+' '+(button.getAttribute('title') || '')).toLowerCase();
      if (/send|отправ|submit/.test(label) && button.closest('main, form, [class*="input"], [class*="query"]')) recordGeminiPrompt();
    }, true);
    el('su-cfg').addEventListener('click', () => {
      const a = prompt('Локальный порог за 5 часов (0 — очистить статистику):', String(state.gemFiveMax));
      if (a === null) return;
      if (a.trim() === '0') { set('gem_timestamps', []); drawGemini(); status('Счётчик очищен'); return; }
      const b = prompt('Локальный порог за неделю:', String(state.gemWeekMax));
      if (b === null) return;
      if (!Number.isSafeInteger(Number(a)) || Number(a)<1 || !Number.isSafeInteger(Number(b)) || Number(b)<1) { status('Нужны положительные целые числа'); return; }
      state.gemFiveMax = Number(a); state.gemWeekMax = Number(b);
      set('gemFiveMax', state.gemFiveMax); set('gemWeekMax', state.gemWeekMax); drawGemini();
    });
  }
  async function refresh() {
    if(!gpt) { drawGemini(); status('Обновлено '+clock()+' МСК'); return; }
    if(busy) return;
    busy=true; status('Обновление…');
    try {
      const data=await usage();
      const windows=[data?.rate_limit?.primary_window,data?.rate_limit?.secondary_window].filter(Boolean);
      draw(windows.find(w=>Number(w.limit_window_seconds)>=4*3600 && Number(w.limit_window_seconds)<=12*3600),'five',true);
      draw(windows.find(w=>Number(w.limit_window_seconds)>=2*86400),'week',false);
      status('Обновлено '+clock()+' МСК');
    } catch(e) { status('Лимиты недоступны: '+e.message); }
    finally { busy=false; }
  }
  // Gemini sidebar is distinct from ChatGPT's narrow in-chat navigator.
  function findNav() {
    if(!gpt) return document.querySelector('bard-sidenav,side-navigation,mat-sidenav,[data-test-id="side-nav-container"], [data-testid="side-nav-container"], [aria-label="Боковая панель"], [aria-label="Side navigation"]');
    for(const sel of ['[data-testid*="conversation"][data-testid*="nav"]','[data-testid*="navigator"]',
      '[aria-label*="conversation" i][aria-label*="nav" i]','[aria-label*="navigator" i]','[aria-label*="навига" i]']) {
      const target=document.querySelector(sel);
      if(target instanceof HTMLElement && !target.closest('#'+ID)) return target;
    }
    for(const target of document.querySelectorAll('body *')) {
      if(!(target instanceof HTMLElement) || target.closest('#'+ID)) continue;
      const r=target.getBoundingClientRect(), st=getComputedStyle(target);
      if(r.width<8||r.width>90||r.height<70||r.height>Math.min(innerHeight*.85,700)||r.left<innerWidth-130||
         !['fixed','absolute','sticky'].includes(st.position)||(target.innerText||'').trim().length>40) continue;
      let count=0;
      for(const node of target.querySelectorAll('*')) {
        const d=node.getBoundingClientRect();
        if(d.width>=8&&d.width<=36&&d.height>=1&&d.height<=12) count++;
        if(count>=6) return target;
      }
    }
    return null;
  }
  function restoreNav() {
    if(!navTarget) return;
    if(navTarget.isConnected) {
      if(navStyle) navTarget.style.setProperty('display',navStyle,navPriority);
      else navTarget.style.removeProperty('display');
    }
    navTarget=null; navStyle=null; navPriority='';
  }
  function applyNav() {
    // If shown, restore existing target without rescan; hidden nodes may have no bounding rectangle.
    if(!state.navHidden) { restoreNav(); return; }
    if(navTarget?.isConnected) return;
    restoreNav();
    const found=findNav();
    if(!(found instanceof HTMLElement)) return;
    navTarget=found; navStyle=found.style.getPropertyValue('display');
    navPriority=found.style.getPropertyPriority('display');
    found.style.setProperty('display','none','important');
  }
  function scheduleNav() {
    if(navScanPending) return;
    navScanPending=true;
    requestAnimationFrame(()=>{navScanPending=false;applyNav();});
  }
  el('su-fold').addEventListener('click',()=>{state.collapsed=panel.classList.toggle('su-collapsed');el('su-fold').textContent=state.collapsed?'+':'−';set('collapsed',state.collapsed);});
  el('su-reload').addEventListener('click',()=>{refresh();scheduleNav();});
  // Drag only by title, so switches/buttons remain easy to click.
  let drag=null;
  el('su-drag').addEventListener('pointerdown',e=>{
    if(e.button!==0) return;
    const r=panel.getBoundingClientRect();
    drag={pointer:e.pointerId,dx:e.clientX-r.left,dy:e.clientY-r.top};
    e.currentTarget.setPointerCapture(e.pointerId);
  });
  el('su-drag').addEventListener('pointermove',e=>{
    if(!drag || e.pointerId!==drag.pointer) return;
    const x=Math.max(0,Math.min(innerWidth-panel.offsetWidth,e.clientX-drag.dx));
    const y=Math.max(0,Math.min(innerHeight-panel.offsetHeight,e.clientY-drag.dy));
    panel.style.left=x+'px';panel.style.top=y+'px';panel.style.right='auto';panel.style.bottom='auto';
    state.position={x,y};
  });
  const finishDrag=()=>{if(drag&&state.position)set('position',state.position);drag=null;};
  el('su-drag').addEventListener('pointerup',finishDrag);
  el('su-drag').addEventListener('pointercancel',finishDrag);
  window.addEventListener('resize',()=>{place();ensureVisible();scheduleNav();},{passive:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){updateClock();if(state.auto)refresh();scheduleNav();}});
  setInterval(()=>{updateClock();if(!document.hidden&&state.auto)refresh();},60000);
  scheduleNav(); refresh();
  console.info('[B/S tech-Limits AI] 3.9 initialized on', host);
}
function safeInit() {
  try { init(); }
  catch (error) {
    console.error('[B/S tech-Limits AI] Ошибка запуска:', error);
    if (document.body && !document.getElementById('bs-tech-error')) {
      const box = document.createElement('div');
      box.id = 'bs-tech-error';
      box.textContent = 'B/S tech-Limits AI · ошибка: ' + String(error?.message || error);
      Object.assign(box.style, {position:'fixed',bottom:'80px',right:'18px',padding:'10px',zIndex:'2147483647',background:'#812b2b',color:'#fff',borderRadius:'8px',font:'12px Arial'});
      document.body.append(box);
    }
  }
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', safeInit, {once:true});
else safeInit();
// Gemini is a SPA and sometimes replaces page DOM after userscript initialization.
if (location.hostname === 'gemini.google.com') {
  let retries = 0;
  const retry = setInterval(() => {
    if (document.getElementById('bs-tech-limits-ai-v39') || ++retries >= 12) clearInterval(retry);
    else safeInit();
  }, 1500);
}
