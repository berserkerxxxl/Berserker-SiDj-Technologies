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

Версия 0.1.0-alpha.4, билд 20261029.2.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.4_build20261029.2_win64.zip](BS_Reserve_0.1.0-alpha.4_build20261029.2_win64.zip) | `58d79a604b06c6eab99943099b94fde7d30a80c8172f6efe182f3f8904febc81` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.4_build20261029.2_macos_arm64.zip](BS_Reserve_0.1.0-alpha.4_build20261029.2_macos_arm64.zip) | `ba5923c8a46731185353bd5f852e28be098c2268c174c2098d92680e60d3bced` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.4_build20261029.2_macos_x64.zip](BS_Reserve_0.1.0-alpha.4_build20261029.2_macos_x64.zip) | `1fa94cab484fe1918f2a3243abdc8c9529b4edcfa080979b866f6200a2b0c542` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.4_build20261029.2_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.4_build20261029.2_linux_x64.tar.gz) | `724dc17a9d0cc259fad914f031ac8ff577dd7f75a30cbd27dc6127793a1ddfae` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.4_build20261029.2_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.4_build20261029.2_linux_arm64.tar.gz) | `ae757887792834fc44c7e32270585c81143078c8c25b0fde3803a18cfccfee75` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
