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

Версия 0.1.0-alpha.5, билд 20261029.3.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.5_build20261029.3_win64.zip](BS_Reserve_0.1.0-alpha.5_build20261029.3_win64.zip) | `80de3369aa1f079b46057c8a404ce9b6f1e5a5b87feb6b91bdb9a4a459537606` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.5_build20261029.3_macos_arm64.zip](BS_Reserve_0.1.0-alpha.5_build20261029.3_macos_arm64.zip) | `3b7dda23e87d8b128547ab572ebdea1a2b59b5013f8fa343797d247ab5b630c7` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.5_build20261029.3_macos_x64.zip](BS_Reserve_0.1.0-alpha.5_build20261029.3_macos_x64.zip) | `8e090333eebbfbf36cf025f9b567905db18e22e4a78d42d5dbff945ac44bd753` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.5_build20261029.3_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.5_build20261029.3_linux_x64.tar.gz) | `5450674be92e4d9c5ef055a2af8ba8933bdb0a30aad97f1d101656798b8549ec` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.5_build20261029.3_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.5_build20261029.3_linux_arm64.tar.gz) | `49c55e4e9bda66cbb09d0126cba37d25c4d3a65af93472f2e56ef76edd512f5d` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
