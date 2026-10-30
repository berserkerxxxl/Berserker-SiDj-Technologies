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

Версия 0.1.0-alpha.7, билд 20261030.2.

| Платформа | Архив | SHA-256 |
| --- | --- | --- |
| Windows x64 | [BS_Reserve_0.1.0-alpha.7_build20261030.2_win64.zip](BS_Reserve_0.1.0-alpha.7_build20261030.2_win64.zip) | `3b6e7aa218cdac68507c8a135d0ecdbd76b5f07a8a3be3047c4fa7356220496d` |
| macOS · Apple Silicon | [BS_Reserve_0.1.0-alpha.7_build20261030.2_macos_arm64.zip](BS_Reserve_0.1.0-alpha.7_build20261030.2_macos_arm64.zip) | `8e54dd9c4868c9fd291cecffc9c33e331b16f38657fb5478462559d68b0b184f` |
| macOS · Intel | [BS_Reserve_0.1.0-alpha.7_build20261030.2_macos_x64.zip](BS_Reserve_0.1.0-alpha.7_build20261030.2_macos_x64.zip) | `77e7fa0b2737e62d6c985b9a67a678f29d3dff679beb189677d74973aa07e0c3` |
| Linux x64 | [BS_Reserve_0.1.0-alpha.7_build20261030.2_linux_x64.tar.gz](BS_Reserve_0.1.0-alpha.7_build20261030.2_linux_x64.tar.gz) | `ca852d23edd29e96086b4d350f37292d04324fbe71740ee729f829383c3d8ebd` |
| Linux ARM64 | [BS_Reserve_0.1.0-alpha.7_build20261030.2_linux_arm64.tar.gz](BS_Reserve_0.1.0-alpha.7_build20261030.2_linux_arm64.tar.gz) | `c70dcd5878df9817bf6466b2228bdd259d6265143d51823419339ee4ac1b5bb8` |

[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).

Экспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.

Предыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.
