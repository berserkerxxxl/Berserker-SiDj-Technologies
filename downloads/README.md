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


# B/S Reserve — РЕЛИЗ

Версия 0.2.0, билд 20261030.5.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.2.0_build20261030.5_win64.zip](BS_Reserve_0.2.0_build20261030.5_win64.zip) | `5fd4213d340c8947042f12f5c8734ab65f413477d66acf0c34c03a4eaa789746` |
| macOS · Apple Silicon | [BS_Reserve_0.2.0_build20261030.5_macos_arm64.zip](BS_Reserve_0.2.0_build20261030.5_macos_arm64.zip) | `050e13d0b68ad05c4b02de3c09daa632f141184de2ed9cd2f7635d10ed09b1be` |
| macOS · Intel | [BS_Reserve_0.2.0_build20261030.5_macos_x64.zip](BS_Reserve_0.2.0_build20261030.5_macos_x64.zip) | `67b694ed70e2c7d88ceb8cb5aaf1b2b5269f439e4ba185bae6cc431dce812074` |
| Linux x64 | [BS_Reserve_0.2.0_build20261030.5_linux_x64.tar.gz](BS_Reserve_0.2.0_build20261030.5_linux_x64.tar.gz) | `24caf997c05c3e3cb7dfee0a5f9ad52df989c6bdb4d9e43a69ed3b8976cd061a` |
| Linux ARM64 | [BS_Reserve_0.2.0_build20261030.5_linux_arm64.tar.gz](BS_Reserve_0.2.0_build20261030.5_linux_arm64.tar.gz) | `c79a3759d2c7055ea3943499cf6082cc216e8ce6fa2ab94adbfe97a5e2c9cc9a` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Публичный релиз. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
