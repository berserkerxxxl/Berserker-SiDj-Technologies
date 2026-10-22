// ==UserScript==
// @name         ChatGPT — лимиты Work/Codex + навигатор 2.7 Mini
// @namespace    jon-chatgpt
// @version      2.7
// @description  Мини-панель лимитов с часами и датой сброса (МСК), переключатель НАВ
// @match        https://chatgpt.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    const PANEL_ID = 'jon-usage-panel';
    const UPDATE_INTERVAL = 60 * 1000;
    const DISPLAY_TIME_ZONE = 'Europe/Moscow'; // Дата и время сброса по Москве

    const NAV_STORAGE_KEY = 'jon-chat-navigator-hidden';
    const NAV_MARK_ATTR = 'data-jon-chat-navigator';

    function decodeJwt(token) {
        try {
            const part = token.split('.')[1]
                .replace(/-/g, '+')
                .replace(/_/g, '/');

            const padded = part + '='.repeat((4 - part.length % 4) % 4);
            return JSON.parse(atob(padded));
        } catch {
            return {};
        }
    }

    async function getAuth() {
        const r = await fetch('/api/auth/session', {
            credentials: 'include',
            cache: 'no-store'
        });

        if (!r.ok)
            throw new Error('Сессия: HTTP ' + r.status);

        const s = await r.json();
        const token = s.accessToken;

        if (!token)
            throw new Error('Не найден accessToken');

        const jwt = decodeJwt(token);

        const authClaim =
            jwt['https://api.openai.com/auth'] || {};

        const accountId =
            s?.account?.id ||
            s?.account_id ||
            s?.user?.account_id ||
            authClaim.chatgpt_account_id;

        if (!accountId)
            throw new Error('Не найден Account ID');

        return { token, accountId };
    }

    async function getUsage() {
        const { token, accountId } = await getAuth();

        const r = await fetch('/backend-api/wham/usage', {
            method: 'GET',
            credentials: 'include',
            cache: 'no-store',
            headers: {
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + token,
                'ChatGPT-Account-Id': accountId,
                'OpenAI-Beta': 'codex-1',
                'originator': 'codex_cli_rs'
            }
        });

        if (!r.ok)
            throw new Error('Usage: HTTP ' + r.status);

        return await r.json();
    }

    function remaining(windowData) {
        if (!windowData)
            return null;

        const used = Number(windowData.used_percent);

        if (!Number.isFinite(used))
            return null;

        return Math.max(
            0,
            Math.min(100, Math.round(100 - used))
        );
    }

    function resetText(windowData, prefix) {
        const resetAt = Number(windowData?.reset_at);
        if (!Number.isFinite(resetAt) || resetAt <= 0)
            return '';

        const resetDate = new Date(resetAt * 1000);
        const diff = resetDate.getTime() - Date.now();

        if (diff <= 0)
            return 'Сброс скоро';

        const totalMinutes = Math.ceil(diff / 60000);
        const pad2 = (n) => String(n).padStart(2, '0');

        if (prefix === 'ju-5') {
            const hours = Math.floor(totalMinutes / 60);
            const minutes = totalMinutes % 60;
            const resetTime = resetDate.toLocaleTimeString('ru-RU', {
                timeZone: DISPLAY_TIME_ZONE,
                hour: '2-digit',
                minute: '2-digit',
                hourCycle: 'h23'
            });

            return `Сброс через ${hours}:${pad2(minutes)} · в ${resetTime}`;
        }

        // Недельный лимит: дни + часы:минуты и календарная дата сброса.
        const days = Math.floor(totalMinutes / (24 * 60));
        const hours = Math.floor(totalMinutes % (24 * 60) / 60);
        const minutes = totalMinutes % 60;
        const resetDay = resetDate.toLocaleDateString('ru-RU', {
            timeZone: DISPLAY_TIME_ZONE,
            day: '2-digit',
            month: '2-digit',
            year: '2-digit'
        });

        return `Сброс через ${days} д ${hours}:${pad2(minutes)} · ${resetDay}`;
    }

    function isNavigatorHidden() {
        try {
            return localStorage.getItem(NAV_STORAGE_KEY) === '1';
        } catch {
            return false;
        }
    }

    function setNavigatorHidden(hidden) {
        try {
            localStorage.setItem(NAV_STORAGE_KEY, hidden ? '1' : '0');
        } catch {}

        applyNavigatorState();
        updateNavigatorButton();
    }

    function updateNavigatorButton() {
        const toggle = document.getElementById('ju-nav-toggle');
        if (!toggle)
            return;

        toggle.checked = !isNavigatorHidden();
    }

    function looksLikeConversationNavigator(el) {
        if (!(el instanceof HTMLElement))
            return false;

        if (el.id === PANEL_ID || el.closest('#' + PANEL_ID))
            return false;

        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);

        if (
            rect.width < 8 ||
            rect.width > 90 ||
            rect.height < 70 ||
            rect.height > Math.min(window.innerHeight * 0.85, 700)
        ) {
            return false;
        }

        if (rect.left < window.innerWidth - 130)
            return false;

        if (
            style.position !== 'fixed' &&
            style.position !== 'absolute' &&
            style.position !== 'sticky'
        ) {
            return false;
        }

        const text = (el.innerText || '').trim();
        if (text.length > 40)
            return false;

        const parts = [...el.querySelectorAll('*')].filter(node => {
            if (!(node instanceof HTMLElement))
                return false;

            const r = node.getBoundingClientRect();
            const s = getComputedStyle(node);

            if (s.display === 'none' || s.visibility === 'hidden')
                return false;

            return (
                r.width >= 8 &&
                r.width <= 36 &&
                r.height >= 1 &&
                r.height <= 12
            );
        });

        return parts.length >= 6;
    }

    function findConversationNavigator() {
        // Сначала пробуем более стабильные семантические признаки,
        // если ChatGPT их предоставляет.
        const semanticSelectors = [
            '[data-testid*="conversation"][data-testid*="nav"]',
            '[data-testid*="navigator"]',
            '[aria-label*="conversation" i][aria-label*="nav" i]',
            '[aria-label*="navigator" i]',
            '[aria-label*="навига" i]'
        ];

        for (const selector of semanticSelectors) {
            const el = document.querySelector(selector);
            if (el instanceof HTMLElement)
                return el;
        }

        // Запасной вариант: узнаём компактную вертикальную колонку
        // коротких полосок у правого края окна.
        const all = [...document.body.querySelectorAll('body *')];

        let best = null;
        let bestScore = -1;

        for (const el of all) {
            if (!looksLikeConversationNavigator(el))
                continue;

            const rect = el.getBoundingClientRect();
            const score =
                (window.innerWidth - rect.right <= 35 ? 3 : 0) +
                Math.min(20, el.children.length);

            if (score > bestScore) {
                best = el;
                bestScore = score;
            }
        }

        return best;
    }

    function applyNavigatorState() {
        const hidden = isNavigatorHidden();

        document.querySelectorAll('[' + NAV_MARK_ATTR + '="1"]').forEach(el => {
            if (el instanceof HTMLElement) {
                el.style.removeProperty('display');
                el.removeAttribute(NAV_MARK_ATTR);
            }
        });

        const nav = findConversationNavigator();
        if (!nav)
            return;

        nav.setAttribute(NAV_MARK_ATTR, '1');

        if (hidden)
            nav.style.setProperty('display', 'none', 'important');
        else
            nav.style.removeProperty('display');
    }

    function createPanel() {
        if (document.getElementById(PANEL_ID))
            return;

        const panel = document.createElement('div');

        panel.id = PANEL_ID;

        panel.innerHTML = `
            <div class="ju-head">
                <b>📊 Лимиты</b>

                <div class="ju-buttons">
                    <label class="ju-nav-switch" title="Показать или скрыть правый навигатор длинного чата">
                        <span>НАВ</span>
                        <input id="ju-nav-toggle" type="checkbox" checked>
                        <span class="ju-slider"></span>
                    </label>
                    <button id="ju-refresh" title="Обновить лимиты">↻</button>
                    <button id="ju-collapse" title="Свернуть панель">−</button>
                </div>
            </div>

            <div id="ju-body">

                <div class="ju-row">
                    <span>5 часов</span>
                    <b id="ju-5-value">—</b>
                </div>

                <div class="ju-bar">
                    <div id="ju-5-bar"></div>
                </div>

                <div class="ju-reset"
                     id="ju-5-reset"></div>


                <div class="ju-row second">
                    <span>Неделя</span>
                    <b id="ju-week-value">—</b>
                </div>

                <div class="ju-bar">
                    <div id="ju-week-bar"></div>
                </div>

                <div class="ju-reset"
                     id="ju-week-reset"></div>


                <div id="ju-status">
                    загрузка…
                </div>

            </div>
        `;

        document.body.appendChild(panel);

        const style = document.createElement('style');

        style.textContent = `
            #${PANEL_ID} {
                position: fixed;
                right: 18px;
                bottom: 80px;

                width: 210px;

                z-index: 999999;

                padding: 7px 8px;

                border-radius: 12px;

                border:
                    1px solid rgba(128,128,128,.30);

                background:
                    var(--main-surface-primary,#fff);

                color:
                    var(--text-primary,#111);

                box-shadow:
                    0 5px 20px rgba(0,0,0,.16);

                font-family:
                    "Segoe UI",
                    Arial,
                    sans-serif;

                font-size: 11px;
            }


            #${PANEL_ID} .ju-head {
                display: flex;
                justify-content: space-between;
                align-items: center;

                gap: 2px;

                margin-bottom: 7px;
            }


            #${PANEL_ID} .ju-buttons {
                display: flex;
                gap: 3px;
            }



            #${PANEL_ID} .ju-nav-switch {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                font-size: 10px;
                font-weight: 600;
                white-space: nowrap;
                cursor: pointer;
                user-select: none;
            }

            #${PANEL_ID} .ju-nav-switch input {
                display: none;
            }

            #${PANEL_ID} .ju-slider {
                position: relative;
                width: 28px;
                height: 15px;
                border-radius: 999px;
                background: rgba(128,128,128,.28);
                border: 1px solid rgba(128,128,128,.30);
                transition: background .15s ease;
                flex: 0 0 auto;
            }

            #${PANEL_ID} .ju-slider::after {
                content: '';
                position: absolute;
                top: 2px;
                left: 2px;
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: #fff;
                box-shadow: 0 1px 2px rgba(0,0,0,.25);
                transition: transform .15s ease;
            }

            #${PANEL_ID} .ju-nav-switch input:checked + .ju-slider {
                background: #22c55e;
                border-color: #22c55e;
            }

            #${PANEL_ID} .ju-nav-switch input:checked + .ju-slider::after {
                transform: translateX(13px);
            }


            #${PANEL_ID} button {

                padding:
                    3px 6px;

                border-radius:
                    6px;

                border:
                    1px solid rgba(128,128,128,.30);

                background:
                    rgba(128,128,128,.08);

                color:
                    inherit;

                cursor:
                    pointer;

                font-size:
                    9px;

                font-family:
                    inherit;

                transition:
                    background .15s ease,
                    transform .10s ease;
            }


            #${PANEL_ID} button:hover {

                background:
                    rgba(128,128,128,.18);
            }


            #${PANEL_ID} button:active {

                transform:
                    scale(.96);
            }


            #${PANEL_ID} .ju-row {

                display:
                    flex;

                justify-content:
                    space-between;

                align-items:
                    center;
            }


            #${PANEL_ID} .ju-bar {

                height:
                    4px;

                margin-top:
                    3px;

                background:
                    rgba(128,128,128,.22);

                border-radius:
                    8px;

                overflow:
                    hidden;
            }


            #${PANEL_ID} .ju-bar div {

                height:
                    100%;

                width:
                    0%;

                background:
                    currentColor;

                transition:
                    width .3s ease;
            }


            #${PANEL_ID} .ju-reset {

                font-size:
                    9px;

                opacity:
                    .65;

                margin-top:
                    2px;
            }


            #${PANEL_ID} .second {

                margin-top:
                    8px;
            }


            #ju-status {

                text-align:
                    right;

                font-size:
                    10px;

                opacity:
                    .55;

                margin-top:
                    5px;
            }


            #${PANEL_ID}.collapsed {

                width:
                    auto;
            }


            #${PANEL_ID}.collapsed #ju-body {

                display:
                    none;
            }


            #${PANEL_ID}.collapsed .ju-head {

                margin-bottom:
                    0;
            }
        `;

        document.head.appendChild(style);


        document
            .getElementById('ju-refresh')
            .addEventListener('click', refresh);


        document
            .getElementById('ju-nav-toggle')
            .addEventListener('change', (e) => {
                setNavigatorHidden(!e.target.checked);
            });

        updateNavigatorButton();
        applyNavigatorState();

        document
            .getElementById('ju-collapse')
            .addEventListener('click', () => {

                const collapsed =
                    panel.classList.toggle('collapsed');

                document
                    .getElementById('ju-collapse')
                    .textContent =
                        collapsed
                        ? '+'
                        : '−';

                document
                    .getElementById('ju-collapse')
                    .title =
                        collapsed
                        ? 'Развернуть панель'
                        : 'Свернуть панель';
            });
    }


    function renderWindow(data, prefix) {

        const value =
            remaining(data);

        const valueEl =
            document.getElementById(prefix + '-value');

        const bar =
            document.getElementById(prefix + '-bar');

        const reset =
            document.getElementById(prefix + '-reset');


        if (value === null) {

            valueEl.textContent = '—';
            bar.style.width = '0%';
            reset.textContent = '';

            return;
        }


        valueEl.textContent =
            value + '%';

        bar.style.width =
            value + '%';

        reset.textContent =
            resetText(data, prefix);
    }


    async function refresh() {

        const status =
            document.getElementById('ju-status');


        try {

            status.textContent =
                'Обновляю…';


            const data =
                await getUsage();


            const windows = [

                data?.rate_limit?.primary_window,

                data?.rate_limit?.secondary_window

            ].filter(Boolean);


            let five = null;
            let week = null;


            for (const w of windows) {

                const seconds =
                    Number(w.limit_window_seconds);


                if (
                    seconds >= 4 * 3600 &&
                    seconds <= 12 * 3600
                ) {
                    five = w;
                }


                if (
                    seconds >= 2 * 24 * 3600
                ) {
                    week = w;
                }
            }


            five ??=
                data?.rate_limit?.primary_window;


            week ??=
                data?.rate_limit?.secondary_window;


            renderWindow(
                five,
                'ju-5'
            );


            renderWindow(
                week,
                'ju-week'
            );


            status.textContent =
                'Обновлено ' +
                new Date()
                    .toLocaleTimeString(
                        'ru-RU',
                        {
                            hour:
                                '2-digit',

                            minute:
                                '2-digit'
                        }
                    );


        } catch (e) {

            status.textContent =
                '⚠ ' + e.message;

            console.warn(
                '[Usage widget]',
                e
            );
        }
    }


    createPanel();

    refresh();

    const navObserver = new MutationObserver(() => {
        if (isNavigatorHidden())
            applyNavigatorState();
    });

    navObserver.observe(document.body, {
        childList: true,
        subtree: true
    });

    window.addEventListener('resize', () => {
        if (isNavigatorHidden())
            applyNavigatorState();
    });


    setInterval(() => {

        if (!document.hidden)
            refresh();

    }, UPDATE_INTERVAL);


    document.addEventListener(
        'visibilitychange',
        () => {

            if (!document.hidden)
                refresh();
        }
    );

})();
