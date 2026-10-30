# Подключение Cloudflare через GitHub Actions

Запасной путь, когда вход в Cloudflare из облачного браузера не завершается. Cloudflare API используется только после ручного запуска workflow; расписания и автоматического переключения webhook здесь нет.

## Что один раз делает владелец

1. В своём обычном браузере войти в Cloudflare. Проверить **Workers Free** и наличие поддомена `workers.dev` в разделе Workers & Pages. Если поддомен ещё не выбран, завершить бесплатное начальное подключение Workers в интерфейсе Cloudflare. Соглашения принимает сам владелец.
2. В профиле Cloudflare открыть **API Tokens → Create Token → Create Custom Token**. Название: `BS-tech-SiDj-deploy`. Право: **Account → Workers Scripts → Edit**. В Account Resources выбрать **Include → Specific account** и свой аккаунт. Для этого Worker без доменных routes, KV, R2 и баз данных соответствующие дополнительные права не нужны. Токен позволяет изменять Workers выбранного аккаунта; это не доступ только к одному файлу. Желательно ограничить срок, например семью днями на настройку. Не использовать Global API Key.
3. Сохранить токен непосредственно в GitHub: репозиторий → **Settings → Secrets and variables → Actions → New repository secret**. Значение в чат не отправлять. Добавить записи:

| GitHub Actions Secret | Что указать |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Созданный ограниченный токен Cloudflare |
| `CLOUDFLARE_ACCOUNT_ID` | 32-символьный Account ID своего аккаунта Cloudflare |
| `SIDJ_ADMIN_TOKEN` | Необязательно: собственный пароль панели, если нужен ручной доступ через `/setup` |
| `SIDJ_TELEGRAM_BOT_TOKEN` | Уже настроенный действующий токен бота — сохранить существующий |
| `SIDJ_TELEGRAM_CHAT_ID` | Уже настроенный ID личного чата — сохранить существующий |

Обязательны только две новые записи: `CLOUDFLARE_API_TOKEN` и `CLOUDFLARE_ACCOUNT_ID`. Если `SIDJ_ADMIN_TOKEN` не задан, workflow вычисляет отдельный служебный ключ HMAC-SHA256 из токена бота с меткой `B/S-SiDj-admin:v1`, сохраняет его в Secret Worker и использует для операций из GitHub. Ключ отличается от секрета входящих Telegram-запросов и не выводится в журналы. Ручная панель `/setup` при этом не нужна. Для доступа к ней можно заранее задать собственный `SIDJ_ADMIN_TOKEN` (32–128 символов `A-Z a-z 0-9 _ -`); после изменения нужен повторный `deploy` для синхронизации. Пароль Cloudflare или Google для этого не используется.

После настройки временный токен Cloudflare можно отозвать: работа webhook-бота от него не зависит, но будущим развёртываниям снова потребуется доступ.

## Порядок запуска

Открыть **Actions → SiDj Cloudflare - manual operations → Run workflow**, ветка **main**. Проверить тариф и отметить подтверждение **Workers Free**. Без этого облачные операции не выполняются.

1. `deploy` — проверяет код, разворачивает `bs-tech-sidj`, вычисляет его HTTPS-адрес по поддомену аккаунта, применяет три секрета Worker через stdin. **Webhook пока не меняется.** Адрес Worker появится в журнале; секретные значения туда не выводятся.
2. `status` — проверяет личный чат, имя Telegram-бота и текущее подключение webhook.
3. `activate` — сначала проверяет HTTP 403 для неподписанного входящего запроса и проверяет панель владельца, затем включает webhook с сохранением очереди. Эта операция и старый опрос используют одну группу concurrency, поэтому запущенный job опроса сначала закончится.
4. Проверить настоящие команды, нажатия кнопок, файлы, SHA-256, фактическую скорость и метрики Cloudflare. Только после успеха отключить старый workflow `sidj-telegram-commands.yml`. Workflow уведомлений оставить включённым.

`rollback` удаляет только webhook этого Worker без сброса очереди. Перед откатом старый workflow опроса должен быть включён. При отсутствии подтверждения сетевой операции сначала выполнить `status`, а не многократно повторять `activate`.

Доступ только к выбранному аккаунту и проверка Workers Free задаются владельцем: workflow не читает платёжные данные, не изменяет тариф и не создаёт платные очереди/хранилища. Наличие файлов workflow в GitHub не означает, что Cloudflare уже подключён. Нужны реальные секреты и успешный запуск.

## Проверка без доступа к Cloudflare

```bash
python3 -m unittest discover -s automation -p 'test_sidj_cloudflare.py' -v
```

Тесты проверяют отсутствие секретов в аргументах/выводе, передачу secret bulk через stdin, отказ от перенаправлений с Authorization, ограничения адреса, явное подтверждение тарифа, подготовку активации и отсутствие переключения webhook на этапе deploy. Реальные права токена, тариф и доставку Telegram подтверждают после ввода секретов.

Официальные источники: [Cloudflare API Tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/), [получение поддомена Workers и требуемое право Workers Scripts](https://developers.cloudflare.com/api/resources/workers/subresources/subdomains/methods/get/), [группы concurrency GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
