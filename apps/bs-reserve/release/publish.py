"""Render the download page from the hashes of the actual CI-built archives."""
import html
import json
import os
from pathlib import Path
import re

from build import CONFIG, PROJECT, REPO, SOURCE


def main():
    manifest = json.loads((PROJECT / "releases" / (CONFIG["version"] + ".json")).read_text())
    cards = []
    for entry in manifest["targets"]:
        name = html.escape(entry["name"], quote=True)
        size = f"{entry['bytes'] / 1048576:.1f}".replace(".", ",") + " МиБ"
        cards.append(f'''<article class="download-card" data-platform="{entry['target']}">
<h3>{html.escape(entry['label'])}</h3><p class="meta">{html.escape(entry['requirements'])} · {size}</p>
<div class="actions"><a class="button primary" href="../../downloads/{name}" download="{name}">↓ Скачать {html.escape(entry['label'])}</a></div>
<small>SHA-256 архива</small><code class="hash">{entry['sha256']}</code>
<small><a href="../../downloads/{name}.sha256">Файл контрольной суммы</a></small></article>''')
    template = (PROJECT / "release/page.template.html").read_text()
    assert template.count("__DOWNLOAD_CARDS__") == 1
    (PROJECT / "index.html").write_text(template.replace("__DOWNLOAD_CARDS__", "\n".join(cards)))
    for name in ["README_RU.md", "ALPHA_FEEDBACK_RU.md", "TEST_REPORT_RU.md"]:
        text = (SOURCE / name).read_text()
        if name == "TEST_REPORT_RU.md" and os.getenv("GITHUB_RUN_ID"):
            url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            text += "\n## Нативная проверка выпуска на GitHub Actions\n\n"
            text += "Публикация файлов выполняется только после успешных проверок всех пяти целей: Windows x64, macOS Intel и Apple Silicon, Linux x64 и ARM64. На каждой цели запускаются тесты Go, go vet и скомпилированная программа с полным циклом restic. На Linux x64 включён детектор гонок; на Windows проверены DPAPI и создание/изменение временной задачи с выбранным временем.\n\n"
            text += f"[Протокол сборки и тестов]({url}). В Windows дополнительно проверяются видимость системного диалога, его положение поверх обычных окон и отмена; при отсутствии интерактивного рабочего стола пропуск явно указан в логе. Первый пользовательский запуск с браузером, Finder/Gatekeeper и реальный аккаунт ChatGPT требуют отдельной проверки.\n"
        (PROJECT / name).write_text(text)

    index = REPO / "index.html"
    content = index.read_text()
    start = content.index('<article class="mini-product reserve-alpha"')
    end = content.index("</article>", start) + len("</article>")
    card = content[start:end]
    card = re.sub(r'<div class="mini-tag">.*?</div>', '<div class="mini-tag">Windows · macOS · Linux · 0.1.0-alpha.6</div>', card, count=1)
    card = re.sub(r'<a class="mini-download"[^>]*>.*?</a>', '<a class="mini-download" href="apps/bs-reserve/#downloads">↓ Скачать для своей ОС</a>', card, count=1)
    card = card.replace("Работа на пользовательских ПК Windows 11", "Работа на пользовательских компьютерах")
    card = re.sub(r'<p class="mini-disclaimer">.*?</p>', '<p class="mini-disclaimer">Билд 20261030.1 · Заметные кнопки скачивания и просмотра; ошибки по-русски с подсказками и техническими подробностями в журнале. Рабочая Data открытая; шифруются репозитории.</p>', card, count=1)
    index.write_text(content[:start] + card + content[end:])

    readme = REPO / "README.md"
    text = readme.read_text()
    start = text.index("## B/S Reserve")
    end = text.index("## О сайте", start)
    section = "## B/S Reserve · 0.1.0-alpha.6\n\n**Открытая альфа. Билд 20261030.1. Windows x64, macOS Apple Silicon/Intel, Linux x64/ARM64.**\n\nЛокальный архив готовых выгрузок ChatGPT, памяти, инструкций, файлов и разработок. Версии, поиск, имена файлов по карте выгрузки, вложения в чатах, шифрованные снимки restic и проверка восстановления.\n\n"
    section += "- [Страница и выбор скачивания](https://berserkerxxxl.github.io/Berserker-SiDj-Technologies/apps/bs-reserve/)\n- [Инструкция](apps/bs-reserve/README_RU.md) · [Протокол](apps/bs-reserve/TEST_REPORT_RU.md)\n- [Исходники](apps/bs-reserve/source) · [Манифест SHA-256](apps/bs-reserve/releases/0.1.0-alpha.6.json)\n\n"
    section += "macOS 13+: сборки без Developer ID и нотариализации Apple. В macOS/Linux пароль вводится вручную; хранение ключа и встроенное расписание пока только Windows. Автоматический приём Inbox работает на всех платформах. Начните с вымышленных примеров; не используйте как единственную копию. Рабочая Data открытая; шифруются отдельные репозитории. Проверка на пользовательских компьютерах и реальных данных продолжается.\n\n"
    readme.write_text(text[:start] + section + text[end:])

    downloads = REPO / "downloads/README.md"
    text = downloads.read_text()
    start = text.index("# B/S Reserve — ALPHA")
    section = "# B/S Reserve — ALPHA\n\nВерсия 0.1.0-alpha.6, билд 20261030.1.\n\n| Платформа | Архив | SHA-256 |\n| --- | --- | --- |\n"
    for entry in manifest["targets"]:
        section += f"| {entry['label']} | [{entry['name']}]({entry['name']}) | `{entry['sha256']}` |\n"
    section += "\n[Описание и ограничения](../apps/bs-reserve/README_RU.md) · [Тестирование](../apps/bs-reserve/ALPHA_FEEDBACK_RU.md).\n\nЭкспериментальная альфа. Начните с вымышленных примеров и копий файлов; не используйте как единственную резервную копию. Рабочая Data не шифруется приложением; шифруются репозитории restic. macOS: без Developer ID/нотариализации. macOS/Linux: ручной пароль и ручное шифрованное копирование; встроенное расписание и запоминание ключа пока только Windows.\n\nПредыдущая Windows-альфа 0.1.0-alpha.1, билд 20261028.2 остаётся доступна в downloads; новые пакеты её не заменяют.\n"
    downloads.write_text(text[:start] + section)
    print("Rendered download page and documentation from verified release manifest")


if __name__ == "__main__":
    main()
