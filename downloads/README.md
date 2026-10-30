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


# B/S Reserve — BETA

Версия 0.2.0-beta.1, билд 20261030.5.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.2.0-beta.1_build20261030.5_win64.zip](BS_Reserve_0.2.0-beta.1_build20261030.5_win64.zip) | `576122321be65459546ac8d7f9aa40ff7acfbabaac60aba2864bb9f332df34de` |
| macOS · Apple Silicon | [BS_Reserve_0.2.0-beta.1_build20261030.5_macos_arm64.zip](BS_Reserve_0.2.0-beta.1_build20261030.5_macos_arm64.zip) | `55535ec6ad0f295c673ea975e36bf53bd9d4a8f68c8779453f95030d96808940` |
| macOS · Intel | [BS_Reserve_0.2.0-beta.1_build20261030.5_macos_x64.zip](BS_Reserve_0.2.0-beta.1_build20261030.5_macos_x64.zip) | `d9704ee58091f264f175e0125a2eff7d17a2953567e23cb0bf1e845821900264` |
| Linux x64 | [BS_Reserve_0.2.0-beta.1_build20261030.5_linux_x64.tar.gz](BS_Reserve_0.2.0-beta.1_build20261030.5_linux_x64.tar.gz) | `f07d70cbd434dc045c1883d933041ad9f600093d15c2a7c2169049893e60528f` |
| Linux ARM64 | [BS_Reserve_0.2.0-beta.1_build20261030.5_linux_arm64.tar.gz](BS_Reserve_0.2.0-beta.1_build20261030.5_linux_arm64.tar.gz) | `a4779a428110caecb537901d2a63c1e6e2868ffa3c79c6cad989ff06032d0466` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная бета. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
