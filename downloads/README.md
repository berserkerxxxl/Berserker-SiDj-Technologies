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

Версия 0.1.0-alpha.2, билд 20261028.3.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.2_build20261028.3_win64.zip](BS_Reserve_0.1.0-alpha.2_build20261028.3_win64.zip) | `84e6c62be9c4cdb5d9070c8d85eadf5de4bb643d6d29e1056b4b690ed34c91d3` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.2_build20261028.3_macos_arm64.zip](BS_Reserve_0.1.0-alpha.2_build20261028.3_macos_arm64.zip) | `1d1487fdf9497610f12b5c91e5b8de448cdf81a232b02c1052a4a29938e11c34` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.2_build20261028.3_macos_x64.zip](BS_Reserve_0.1.0-alpha.2_build20261028.3_macos_x64.zip) | `c7f65cf25725fd743ce2775437a71e1800ef8f4e5f5af76caf84187dd591d53b` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.2_build20261028.3_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.2_build20261028.3_linux_x64.tar.gz) | `874f6a727081b3626e5f23d43f68617abe35e3bfc0cebd34685ddcdd143d7b89` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.2_build20261028.3_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.2_build20261028.3_linux_arm64.tar.gz) | `ac7917991e93a1c03652534573d8b3f02d927b1c68c0d47ade216e828c1cbc21` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
