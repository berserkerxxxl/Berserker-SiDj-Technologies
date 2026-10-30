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

Версия 0.1.0-alpha.6, билд 20261030.1.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.6_build20261030.1_win64.zip](BS_Reserve_0.1.0-alpha.6_build20261030.1_win64.zip) | `9265f09995a9d8b268e3aa2ba55ecf7930af14fcca4a37bba5da2665eaa17876` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.6_build20261030.1_macos_arm64.zip](BS_Reserve_0.1.0-alpha.6_build20261030.1_macos_arm64.zip) | `98a14e4ca980154ce64a682a83e9a3832a8e83909b4c53fcbd2e3e3e69832874` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.6_build20261030.1_macos_x64.zip](BS_Reserve_0.1.0-alpha.6_build20261030.1_macos_x64.zip) | `f1bffb7ab488dc9f096098ceed11c20daabad1aa17301831a2ef29d01aecbf2a` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.6_build20261030.1_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.6_build20261030.1_linux_x64.tar.gz) | `2bc20e705185dcfcfb24773f930e0aef23c3e53530f031f99213a4aa4e82a53c` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.6_build20261030.1_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.6_build20261030.1_linux_arm64.tar.gz) | `acea4f9dd0e28c4979ae2348c27491b15d0e9794d420fcc1ebf5e1fd8abd792f` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
