# B/S Codex Installer — Windows

Версия публикации: 1.0 (26 октября 2026 года).

Файл: `BS_Codex_Installer_1_0_0.exe`  
Размер: 550 651 байт  
SHA-256: `c59ea53da225b8e760a76f180ea05ddb065ac865d3ceba6d76cd61c448619b96`

Помощник для установки официального Codex из Microsoft Store. Сам Codex не включён.
Программа может изменять блокирующие записи Microsoft в файле hosts, выполняет резервное копирование hosts,
очищает DNS-кэш, сбрасывает кэш Microsoft Store и запускает установку через winget.
В меню есть проверка статуса и восстановление ранее отключённых блокирующих записей.

**Важно:** требуются права администратора. Изменения hosts могут влиять на сетевые политики.
Не используйте на корпоративных устройствах без разрешения.
Исполняемый файл не является официальным программным обеспечением OpenAI или Microsoft.
Перед запуском проверяйте контрольную сумму и выполняйте обычную антивирусную проверку.


# B/S Reserve — ALPHA

Версия 0.1.0-alpha.3, билд 20261029.1.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.3_build20261029.1_win64.zip](BS_Reserve_0.1.0-alpha.3_build20261029.1_win64.zip) | `ef44604b8a59f832d54dd3970d959c57482e99ca667c2ef34c933de837854079` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.3_build20261029.1_macos_arm64.zip](BS_Reserve_0.1.0-alpha.3_build20261029.1_macos_arm64.zip) | `3ea34f218ce424bc7d9d74c60df1ea24061c254c599d1adda947213ff4c5372f` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.3_build20261029.1_macos_x64.zip](BS_Reserve_0.1.0-alpha.3_build20261029.1_macos_x64.zip) | `624ae4fc91f22ea4109bc34e56f87b78053332beec7dbe249c10d7b5a464ef64` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.3_build20261029.1_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.3_build20261029.1_linux_x64.tar.gz) | `19def248677590779fb31c06f729260f4bfebc4f8fc1d20ff65d210ded304f34` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.3_build20261029.1_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.3_build20261029.1_linux_arm64.tar.gz) | `b557d7a2fd275a6fd81c72bea1778ae2db429d670bb97add79fbd1417ba0bd74` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
