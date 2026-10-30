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

Версия 0.1.0-alpha.8, билд 20261030.3.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.8_build20261030.3_win64.zip](BS_Reserve_0.1.0-alpha.8_build20261030.3_win64.zip) | `8075e59f6dfeebbaa2132952625ab0f11ffafdb627d2b91ce76710c9a11b2b23` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.8_build20261030.3_macos_arm64.zip](BS_Reserve_0.1.0-alpha.8_build20261030.3_macos_arm64.zip) | `67b9692e83069cfe03df79a11fb0a0a37c7840a64046af823565c282e6fffbf3` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.8_build20261030.3_macos_x64.zip](BS_Reserve_0.1.0-alpha.8_build20261030.3_macos_x64.zip) | `fbdf386a8fb46fb4a34df3d5e8ce31d6553a900a1ecbff500fa27061f17f7801` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.8_build20261030.3_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.8_build20261030.3_linux_x64.tar.gz) | `89dabc8343d16bba0b390f2e3668d927b058d6e95191129e12fed0a9acaac129` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.8_build20261030.3_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.8_build20261030.3_linux_arm64.tar.gz) | `043b3f01c000508d91686e2d0ef159433823c7b21949463718dad771923c7be7` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
