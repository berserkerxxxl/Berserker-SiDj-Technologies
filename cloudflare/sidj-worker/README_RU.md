# СиДжи — мгновенные ответы через Cloudflare Workers

Этот Worker принимает команды Telegram через Webhook вместо опроса GitHub Actions раз в 5 минут.

## Подключение

1. Cloudflare → Workers & Pages → Create application → GitHub. Разреши доступ **только** к репозиторию `berserkerxxxl/Berserker-SiDj-Technologies`.
2. Выбери ветку `main`, корневую папку проекта `cloudflare/sidj-worker`, имя Worker **`bs-tech-sidj`** (должно совпадать с wrangler.toml). Команда деплоя: `npx wrangler deploy`. Если Cloudflare спрашивает команду сборки, оставь пустой. Подтверди Deploy.
3. После первого развёртывания скопируй точный адрес Worker вида `https://bs-tech-sidj.<аккаунт>.workers.dev`.
4. В Worker → Settings → Variables and Secrets добавь секрет **`SIDJ_TELEGRAM_BOT_TOKEN`** (полный действующий токен из BotFather) и секрет **`SIDJ_TELEGRAM_CHAT_ID`** (свой числовой Telegram chat ID). В виде обычной текстовой переменной добавь **`SIDJ_PUBLIC_URL`** с адресом Worker, включая `https://` и завершающий `/`. Токен никуда в GitHub и чат не вставляй.
5. Нажми Deploy для применения настроек. Открой в браузере `https://<worker-domain>/activate`. Должно появиться «СиДжи подключён к Cloudflare! Webhook активен».
6. Проверка: напиши боту `/projects`, нажми кнопку проекта и попробуй скачать небольшой HTML или JS-файл. После подтверждения выключаем расписание `sidj-telegram-commands.yml` в GitHub.

## Безопасность

- Telegram webhook проверяет заголовок `X-Telegram-Bot-Api-Secret-Token`; значение секретно вычисляется из токена бота и не сохраняется в репозитории.
- Учитываются сообщения только от личного чата, указанного в `SIDJ_TELEGRAM_CHAT_ID`.
- `/activate` всегда направляет Telegram только на закреплённый канонический адрес `SIDJ_PUBLIC_URL`, не на адрес из запроса.
- Файлы разрешены только из каталога `automation/sidj_projects.json` и папок `apps/` или `downloads/`. Для архивов проверяется SHA-256, если опубликован файл `.sha256`.
- Крупные файлы отправляются ссылкой, если их нельзя переслать как вложение.
- Команды доступны без платного постоянно работающего сервера, но действует лимит запросов Cloudflare Free.

Если секреты уже случайно попадали на скриншоты, отзови скомпрометированные токены через BotFather и синхронизируй новый токен с Cloudflare и GitHub.
