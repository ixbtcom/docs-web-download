#!/usr/bin/env python3
"""
Скачивание одной веб-страницы и конвертация в Markdown.

Использование:
    python3 fetch_single.py --parser docusaurus --url URL --output file.md
    python3 fetch_single.py --parser raw --url URL --output file.md
    python3 fetch_single.py --parser timeweb --url URL --output file.md
"""

import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_raw(url: str) -> str | None:
    """Скачивает raw markdown."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text.strip()


def fetch_html(url: str, parser_type: str) -> str | None:
    """Скачивает HTML-страницу и конвертирует в markdown."""
    from markdownify import MarkdownConverter

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    h1 = soup.find("h1")
    title = h1.get_text().strip() if h1 else "Untitled"

    # Извлекаем контент в зависимости от парсера
    if parser_type == "timeweb":
        article = soup.find(attrs={"itemprop": "articleBody"})
    else:  # docusaurus
        article = soup.find("article") or soup.find("main")

    if not article:
        print(f"   ⚠️  Контент не найден")
        return None

    # Удаляем мусор
    for tag_name in ["nav", "footer", "aside"]:
        for el in article.find_all(tag_name):
            el.decompose()
    for btn in article.find_all("button"):
        btn.decompose()
    for el in article.find_all(string=re.compile(r"^On this page$")):
        parent = el.parent
        if parent and parent.name in ("div", "span", "aside", "li"):
            parent.decompose()

    # Конвертируем
    md = MarkdownConverter(
        heading_style="ATX", bullets="-", strong_em_symbol="*",
        strip=["script", "style", "noscript", "svg"],
    ).convert(str(article))

    # Чистка
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = "\n".join(line.rstrip() for line in md.split("\n"))
    md = md.strip()

    # Добавляем h1 если нет
    if not md.startswith("# "):
        md = f"# {title}\n\n{md}"

    return md


def main():
    parser = argparse.ArgumentParser(description="Скачать одну веб-страницу в Markdown")
    parser.add_argument("--parser", "-p", required=True,
                        choices=["docusaurus", "timeweb", "raw"],
                        help="Тип парсера")
    parser.add_argument("--url", "-u", required=True, help="URL страницы")
    parser.add_argument("--output", "-o", required=True, help="Путь к выходному .md файлу")
    args = parser.parse_args()

    print(f"📄 Скачиваю: {args.url}")

    try:
        if args.parser == "raw":
            content = fetch_raw(args.url)
        else:
            content = fetch_html(args.url, args.parser)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)

    if not content:
        print("❌ Не удалось извлечь контент")
        sys.exit(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content + "\n", encoding="utf-8")
    print(f"✅ Сохранено: {out_path} ({len(content)} символов)")


if __name__ == "__main__":
    main()
