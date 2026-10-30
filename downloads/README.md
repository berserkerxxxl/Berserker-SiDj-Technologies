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

Версия 0.1.0-alpha.9, билд 20261030.4.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.9_build20261030.4_win64.zip](BS_Reserve_0.1.0-alpha.9_build20261030.4_win64.zip) | `cbc0ea5e194b09d174fe365e688b8a09b8c90263194d17c39c8c96e929ae75e8` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.9_build20261030.4_macos_arm64.zip](BS_Reserve_0.1.0-alpha.9_build20261030.4_macos_arm64.zip) | `67a095bca2740aa6c6c57765256e76e6e82199295678792fdc901bfd2726e663` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.9_build20261030.4_macos_x64.zip](BS_Reserve_0.1.0-alpha.9_build20261030.4_macos_x64.zip) | `683322dde4018e908ec04453bf9317ebbed745cef36e26f9a24a4f71a72ea69e` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.9_build20261030.4_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.9_build20261030.4_linux_x64.tar.gz) | `56b1e1cdd819d0cf35fc6245ebcae20ebcaabdda2d763806f00978d20785ce1c` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.9_build20261030.4_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.9_build20261030.4_linux_arm64.tar.gz) | `c8853ab06bd70886a5a73107a65c118170ef96bd578cf07545650c87a09560c4` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
