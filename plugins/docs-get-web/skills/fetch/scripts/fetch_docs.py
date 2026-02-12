#!/usr/bin/env python3
"""
Универсальный скрипт для скачивания документации и конвертации в Markdown.

Поддерживаемые источники:
  - timeweb-k8s  — Timeweb Cloud Kubernetes docs
  - jitsu         — Jitsu self-hosting docs (Docusaurus + GitHub raw)

Использование:
    python3 fetch_docs.py                          # все источники → ./docs/
    python3 fetch_docs.py jitsu                    # только Jitsu → ./docs/
    python3 fetch_docs.py --output /path/to/docs   # с указанием выходной папки
    python3 fetch_docs.py jitsu --output /tmp/docs # комбинация

Результат:
    {output}/{source}/*.md — сконвертированные страницы
    {output}/{source}/images/{slug}/ — скачанные изображения
    {output}/{source}/index.md — оглавление
"""

import os
import re
import sys
import time
import hashlib
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

# ─── Общие настройки ───────────────────────────────────────────────────────────

DOCS_DIR = Path.cwd() / "docs"  # по умолчанию — ./docs в текущей директории
DELAY = 1.0  # секунды между запросами

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ─── Профили источников ────────────────────────────────────────────────────────

SOURCES = {
    "timeweb-k8s": {
        "base_url": "https://timeweb.cloud",
        "parser": "timeweb",
        "output_dir": "timeweb-kubernetes",
        "path_prefix": "/docs/k8s",
        "index_title": "Документация Timeweb Cloud — Kubernetes",
        "doc_paths": [
            "/docs/k8s",
            "/docs/k8s/create-cluster",
            "/docs/k8s/manage-cluster",
            "/docs/k8s/container-registry",
            "/docs/k8s/cluster-connection",
            "/docs/k8s/cluster-connection/kubectl",
            "/docs/k8s/cluster-connection/lens",
            "/docs/k8s/cluster-connection/freelens",
            "/docs/k8s/kubernetes-load-balancer",
            "/docs/k8s/kubernetes-autoscaling",
            "/docs/k8s/kubernetes-autoscaling/kubernetes-autoscaler",
            "/docs/k8s/kubernetes-autoscaling/autoscaling-to-zero-nodes",
            "/docs/k8s/network-drives-connection",
            "/docs/k8s/connect-oidc-provider-to-cluster",
            "/docs/k8s/helm",
            "/docs/k8s/helm-chart-creation",
            "/docs/k8s/network-plugins",
            "/docs/k8s/addons",
            "/docs/k8s/addons/nginx-ingress",
            "/docs/k8s/addons/openfaas",
            "/docs/k8s/addons/minio-operator",
            "/docs/k8s/addons/dbaas-operator",
            "/docs/k8s/addons/cert-manager",
            "/docs/k8s/addons/cert-manager-webhook",
            "/docs/k8s/addons/traefik",
            "/docs/k8s/addons/fluent-operator",
            "/docs/k8s/addons/velero",
            "/docs/k8s/addons/externaldns",
            "/docs/k8s/addons/grafana-loki",
            "/docs/k8s/addons/victoriametrics-operator",
            "/docs/k8s/addons/vault",
            "/docs/k8s/addons/wordpress",
            "/docs/k8s/addons/twc-alert-bot",
            "/docs/k8s/addons/apache-pulsar",
            "/docs/k8s/addons/cpa",
            "/docs/k8s/addons/csi-s3",
        ],
        "raw_urls": [],
    },
    "jitsu": {
        "base_url": "https://docs.jitsu.com",
        "parser": "docusaurus",
        "output_dir": "jitsu",
        "path_prefix": "",
        "index_title": "Документация Jitsu — Self-Hosting",
        "doc_paths": [
            "/self-hosting",
            "/self-hosting/quick-start",
            "/self-hosting/quick-start/syncs",
            "/self-hosting/production-deployment",
            "/self-hosting/configuration",
        ],
        "raw_urls": [
            # (URL, slug-имя файла)
            (
                "https://raw.githubusercontent.com/jitsucom/bulker/main/.docs/server-config.md",
                "bulker-server-config",
            ),
        ],
    },
}

# ─── Утилиты ───────────────────────────────────────────────────────────────────


def path_to_slug(doc_path: str, path_prefix: str) -> str:
    """Конвертирует URL path в имя файла.
    /docs/k8s/addons/nginx-ingress  (prefix=/docs/k8s) -> addons--nginx-ingress
    /self-hosting/configuration     (prefix=)           -> self-hosting--configuration
    """
    relative = doc_path.removeprefix(path_prefix).strip("/")
    if not relative:
        # Корневая страница — используем последний сегмент prefix или путь
        fallback = path_prefix.strip("/").split("/")[-1] if path_prefix else doc_path.strip("/")
        return fallback.replace("/", "--")
    return relative.replace("/", "--")


def download_image(img_url: str, slug: str, images_dir: Path,
                   base_url: str, session: requests.Session) -> str | None:
    """Скачивает изображение и возвращает относительный путь."""
    try:
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        elif img_url.startswith("/"):
            img_url = base_url + img_url

        parsed = urllib.parse.urlparse(img_url)
        path_part = parsed.path.rstrip("/")
        filename = os.path.basename(path_part)
        if not filename or filename == "assets":
            filename = hashlib.md5(img_url.encode()).hexdigest()[:12]
        if "." not in filename:
            filename += ".png"

        img_dir = images_dir / slug
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / filename

        if img_path.exists():
            return f"images/{slug}/{filename}"

        resp = session.get(img_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        img_path.write_bytes(resp.content)
        print(f"    📷 {filename} ({len(resp.content) // 1024} KB)")
        return f"images/{slug}/{filename}"

    except Exception as e:
        print(f"    ⚠️  Ошибка загрузки {img_url}: {e}")
        return None


def clean_markdown(md_content: str) -> str:
    """Общая чистка сконвертированного Markdown."""
    md_content = re.sub(r"\n{3,}", "\n\n", md_content)
    md_content = "\n".join(line.rstrip() for line in md_content.split("\n"))
    md_content = md_content.strip()
    return md_content


def generate_index(pages: list[tuple[str, str]], title: str) -> str:
    """Генерирует index.md с оглавлением."""
    lines = [f"# {title}", "", "Оглавление всех страниц документации.", ""]

    sections: dict[str, list[tuple[str, str]]] = {}
    for slug, page_title in pages:
        parts = slug.split("--")
        section = parts[0] if len(parts) > 1 else ""
        sections.setdefault(section, []).append((slug, page_title))

    if "" in sections:
        for slug, page_title in sections[""]:
            lines.append(f"- [{page_title}]({slug}.md)")
        lines.append("")

    for section in sorted(sections.keys()):
        if section == "":
            continue
        lines.append(f"### {section.replace('-', ' ').title()}")
        lines.append("")
        for slug, page_title in sections[section]:
            lines.append(f"- [{page_title}]({slug}.md)")
        lines.append("")

    return "\n".join(lines) + "\n"


# ─── Парсер: Timeweb Cloud ─────────────────────────────────────────────────────


class TwcMarkdownConverter(MarkdownConverter):
    """Кастомный конвертер для HTML Timeweb Cloud."""

    def __init__(self, slug: str, images_dir: Path, base_url: str,
                 session: requests.Session, **kwargs):
        self.slug = slug
        self.images_dir = images_dir
        self.base_url = base_url
        self.session = session
        super().__init__(**kwargs)

    def convert_pre(self, el, text, **kwargs):
        code_el = el.find("code", attrs={"data-highlighted": "yes"})
        if not code_el:
            code_el = el.find("code")
        if not code_el:
            return f"\n```\n{text.strip()}\n```\n\n"

        lang = ""
        classes = code_el.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        for cls in classes:
            if cls.startswith("language-"):
                lang = cls.removeprefix("language-")
                break

        code_text = code_el.get_text().replace("\xa0", " ")
        lines = [line.rstrip() for line in code_text.split("\n")]
        code_text = "\n".join(lines).strip()
        return f"\n```{lang}\n{code_text}\n```\n\n"

    def convert_code(self, el, text, **kwargs):
        parent = el.parent
        while parent:
            if parent.name == "pre":
                return text
            parent = parent.parent

        img = el.find("img")
        if img:
            return self.convert_img(img, "", **kwargs)

        code_text = el.get_text().replace("\xa0", " ").strip()
        if not code_text:
            return ""
        if "`" in code_text:
            return f"`` {code_text} ``"
        return f"`{code_text}`"

    def convert_img(self, el, text, **kwargs):
        src = el.get("src", "")
        alt = el.get("alt", "")
        if not src:
            return ""

        width = el.get("width")
        height = el.get("height")
        if width and height:
            try:
                if int(width) <= 100 and int(height) <= 100:
                    return ""
            except ValueError:
                pass

        local_path = download_image(src, self.slug, self.images_dir,
                                    self.base_url, self.session)
        if local_path:
            return f"![{alt}]({local_path})\n\n"
        return f"![{alt}]({src})\n\n"

    def convert_h2(self, el, text, **kwargs):
        return self._convert_heading(el, 2)

    def convert_h3(self, el, text, **kwargs):
        return self._convert_heading(el, 3)

    def convert_h4(self, el, text, **kwargs):
        return self._convert_heading(el, 4)

    def _convert_heading(self, el, level):
        for a in el.find_all("a", recursive=True):
            a.decompose()
        for svg in el.find_all("svg", recursive=True):
            svg.decompose()
        for div in el.find_all("div", recursive=True):
            div.decompose()

        text = el.get_text().strip()
        if not text:
            return ""
        hashes = "#" * level
        return f"\n{hashes} {text}\n\n"


def clean_twc_article(article_div: Tag) -> Tag:
    """Удаляет ненужные элементы из articleBody (Timeweb)."""
    for btn in article_div.find_all("div", class_=lambda c: c and "copyButton" in c):
        btn.decompose()
    for qr in article_div.find_all("div", class_=lambda c: c and "qr" in str(c).lower()):
        qr.decompose()
    for el in article_div.find_all(string=re.compile(r"Была ли статья полезна")):
        node = el.parent
        while node and node != article_div:
            classes = " ".join(node.get("class", []))
            if "twCard" in classes or (node.name == "section" and node.parent == article_div):
                node.decompose()
                break
            node = node.parent
        else:
            h5 = el.find_parent("h5")
            if h5:
                for sibling in list(h5.find_next_siblings()):
                    sibling.decompose()
                h5.decompose()
    return article_div


def fetch_timeweb(doc_path: str, source_cfg: dict,
                  out_dir: Path, session: requests.Session) -> tuple[str, str] | None:
    """Скачивает и конвертирует страницу Timeweb Cloud."""
    base_url = source_cfg["base_url"]
    url = base_url + doc_path
    slug = path_to_slug(doc_path, source_cfg["path_prefix"])
    images_dir = out_dir / "images"

    print(f"\n📄 {slug} — {url}")

    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"   ❌ Ошибка загрузки: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    h1 = soup.find("h1")
    title = h1.get_text().strip() if h1 else slug

    article = soup.find(attrs={"itemprop": "articleBody"})
    if not article:
        print(f"   ⚠️  articleBody не найден, пропускаем")
        return None

    article = clean_twc_article(article)

    converter = TwcMarkdownConverter(
        slug=slug, images_dir=images_dir, base_url=base_url, session=session,
        heading_style="ATX", bullets="-", strong_em_symbol="*",
        strip=["script", "style", "svg", "noscript"],
    )
    md_content = converter.convert(str(article))
    md_content = clean_markdown(md_content)
    md_content = re.sub(r"\n*Пока нет комментариев\s*$", "", md_content)
    md_content = md_content.strip()

    return slug, f"# {title}\n\n{md_content}\n"


# ─── Парсер: Docusaurus ────────────────────────────────────────────────────────


class DocusaurusMarkdownConverter(MarkdownConverter):
    """Конвертер для Docusaurus-сайтов (docs.jitsu.com и т.п.)."""

    def __init__(self, slug: str, images_dir: Path, base_url: str,
                 session: requests.Session, **kwargs):
        self.slug = slug
        self.images_dir = images_dir
        self.base_url = base_url
        self.session = session
        super().__init__(**kwargs)

    def convert_pre(self, el, text, **kwargs):
        code_el = el.find("code")
        if not code_el:
            return f"\n```\n{text.strip()}\n```\n\n"

        lang = ""
        classes = code_el.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        for cls in classes:
            if cls.startswith("language-"):
                lang = cls.removeprefix("language-")
                break

        code_text = code_el.get_text().replace("\xa0", " ")
        lines = [line.rstrip() for line in code_text.split("\n")]
        code_text = "\n".join(lines).strip()
        return f"\n```{lang}\n{code_text}\n```\n\n"

    def convert_code(self, el, text, **kwargs):
        parent = el.parent
        while parent:
            if parent.name == "pre":
                return text
            parent = parent.parent

        code_text = el.get_text().replace("\xa0", " ").strip()
        if not code_text:
            return ""
        if "`" in code_text:
            return f"`` {code_text} ``"
        return f"`{code_text}`"

    def convert_img(self, el, text, **kwargs):
        src = el.get("src", "")
        alt = el.get("alt", "")
        if not src:
            return ""

        local_path = download_image(src, self.slug, self.images_dir,
                                    self.base_url, self.session)
        if local_path:
            return f"![{alt}]({local_path})\n\n"
        return f"![{alt}]({src})\n\n"

    def convert_h1(self, el, text, **kwargs):
        return self._convert_heading(el, 1)

    def convert_h2(self, el, text, **kwargs):
        return self._convert_heading(el, 2)

    def convert_h3(self, el, text, **kwargs):
        return self._convert_heading(el, 3)

    def convert_h4(self, el, text, **kwargs):
        return self._convert_heading(el, 4)

    def _convert_heading(self, el, level):
        # Удаляем anchor-ссылки Docusaurus
        for a in el.find_all("a", class_=lambda c: c and "hash-link" in c):
            a.decompose()
        for a in el.find_all("a", attrs={"aria-hidden": "true"}):
            a.decompose()
        for svg in el.find_all("svg", recursive=True):
            svg.decompose()

        text = el.get_text().strip()
        if not text:
            return ""
        hashes = "#" * level
        return f"\n{hashes} {text}\n\n"


def clean_docusaurus_article(article: Tag) -> Tag:
    """Удаляет навигацию и служебные элементы Docusaurus."""
    # Удаляем "On this page" ToC-заголовок (обычно в aside или отдельном div)
    for el in article.find_all(string=re.compile(r"^On this page$")):
        parent = el.parent
        if parent and parent.name in ("div", "span", "aside", "li"):
            parent.decompose()
        elif parent:
            el.extract()
    # Удаляем навигацию prev/next
    for nav in article.find_all("nav", class_=lambda c: c and "pagination" in str(c)):
        nav.decompose()
    # Удаляем кнопки "Edit this page"
    for a in article.find_all("a", string=re.compile(r"Edit this page|Редактировать")):
        parent = a.parent
        if parent and parent.name in ("div", "footer"):
            parent.decompose()
        else:
            a.decompose()
    # Удаляем кнопки копирования в блоках кода
    for btn in article.find_all("button", class_=lambda c: c and "copy" in str(c).lower()):
        btn.decompose()
    # Удаляем breadcrumbs
    for bc in article.find_all("nav", attrs={"aria-label": "Breadcrumbs"}):
        bc.decompose()
    # Удаляем ToC sidebar если попал в article
    for toc in article.find_all("div", class_=lambda c: c and "tableOfContents" in str(c)):
        toc.decompose()
    # Удаляем footer
    for footer in article.find_all("footer"):
        footer.decompose()
    return article


def fetch_docusaurus(doc_path: str, source_cfg: dict,
                     out_dir: Path, session: requests.Session) -> tuple[str, str] | None:
    """Скачивает и конвертирует страницу Docusaurus."""
    base_url = source_cfg["base_url"]
    url = base_url + doc_path
    slug = path_to_slug(doc_path, source_cfg["path_prefix"])
    images_dir = out_dir / "images"

    print(f"\n📄 {slug} — {url}")

    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"   ❌ Ошибка загрузки: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Извлекаем заголовок
    h1 = soup.find("h1")
    title = h1.get_text().strip() if h1 else slug

    # Ищем контент: <article>, или <main>, или .docMainContainer
    article = soup.find("article")
    if not article:
        article = soup.find("main")
    if not article:
        article = soup.find("div", class_=lambda c: c and "docMainContainer" in str(c))
    if not article:
        print(f"   ⚠️  Контент не найден, пропускаем")
        return None

    article = clean_docusaurus_article(article)

    converter = DocusaurusMarkdownConverter(
        slug=slug, images_dir=images_dir, base_url=base_url, session=session,
        heading_style="ATX", bullets="-", strong_em_symbol="*",
        strip=["script", "style", "noscript"],
    )
    md_content = converter.convert(str(article))
    md_content = clean_markdown(md_content)

    # Удаляем дублированный h1 (Docusaurus иногда рендерит его дважды)
    lines = md_content.split("\n")
    if len(lines) > 2 and lines[0].startswith("# ") and lines[2].startswith("# "):
        lines = lines[2:]
        md_content = "\n".join(lines)

    # Если h1 уже есть в контенте, не дублируем
    first_line = md_content.split("\n")[0].strip() if md_content else ""
    if first_line.startswith("# "):
        return slug, f"{md_content}\n"

    return slug, f"# {title}\n\n{md_content}\n"


# ─── Парсер: Raw Markdown (GitHub и т.п.) ──────────────────────────────────────


def fetch_raw_markdown(url: str, slug: str,
                       session: requests.Session) -> tuple[str, str] | None:
    """Скачивает raw Markdown файл."""
    print(f"\n📄 {slug} — {url}")

    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"   ❌ Ошибка загрузки: {e}")
        return None

    md_content = resp.text.strip()
    return slug, f"{md_content}\n"


# ─── Диспетчер парсеров ────────────────────────────────────────────────────────

PARSERS = {
    "timeweb": fetch_timeweb,
    "docusaurus": fetch_docusaurus,
}


# ─── Основная логика ───────────────────────────────────────────────────────────


def fetch_source(source_name: str) -> None:
    """Скачивает всю документацию для одного источника."""
    cfg = SOURCES[source_name]
    parser_fn = PARSERS[cfg["parser"]]
    out_dir = DOCS_DIR / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(exist_ok=True)

    session = requests.Session()
    pages: list[tuple[str, str]] = []
    doc_paths = cfg["doc_paths"]
    raw_urls = cfg.get("raw_urls", [])
    total = len(doc_paths) + len(raw_urls)

    print(f"\n🚀 [{source_name}] Скачивание {total} страниц → {out_dir}/\n")

    # HTML-страницы
    for i, doc_path in enumerate(doc_paths):
        result = parser_fn(doc_path, cfg, out_dir, session)
        if result:
            slug, md_content = result
            title = md_content.split("\n")[0].removeprefix("# ").strip()
            pages.append((slug, title))

            md_path = out_dir / f"{slug}.md"
            md_path.write_text(md_content, encoding="utf-8")
            print(f"   ✅ Сохранено: {md_path.name} ({len(md_content)} символов)")

        if i < len(doc_paths) - 1:
            time.sleep(DELAY)

    # Raw Markdown URL-ы
    for raw_url, slug in raw_urls:
        if doc_paths:
            time.sleep(DELAY)
        result = fetch_raw_markdown(raw_url, slug, session)
        if result:
            slug, md_content = result
            title = md_content.split("\n")[0].removeprefix("# ").strip()
            pages.append((slug, title))

            md_path = out_dir / f"{slug}.md"
            md_path.write_text(md_content, encoding="utf-8")
            print(f"   ✅ Сохранено: {md_path.name} ({len(md_content)} символов)")

    # Генерируем index
    if pages:
        index_content = generate_index(pages, cfg["index_title"])
        index_path = out_dir / "index.md"
        index_path.write_text(index_content, encoding="utf-8")
        print(f"\n📋 Оглавление: {index_path}")

    # Подсчёт изображений
    images_dir = out_dir / "images"
    img_count = sum(1 for _ in images_dir.rglob("*") if _.is_file()) if images_dir.exists() else 0

    print(f"\n✨ [{source_name}] Готово!")
    print(f"   📄 Страниц: {len(pages)}/{total}")
    print(f"   🖼️  Изображений: {img_count}")
    print(f"   📁 Результат: {out_dir}")


def main():
    global DOCS_DIR

    args = sys.argv[1:]
    names = []

    # Парсим аргументы
    i = 0
    while i < len(args):
        if args[i] == "--output" and i + 1 < len(args):
            DOCS_DIR = Path(args[i + 1])
            i += 2
        elif args[i].startswith("--"):
            print(f"❌ Неизвестный флаг: {args[i]}")
            sys.exit(1)
        else:
            names.append(args[i])
            i += 1

    # Валидация имён источников
    for name in names:
        if name not in SOURCES:
            print(f"❌ Неизвестный источник: {name}")
            print(f"   Доступные: {', '.join(SOURCES.keys())}")
            sys.exit(1)

    if not names:
        names = list(SOURCES.keys())

    for name in names:
        fetch_source(name)


if __name__ == "__main__":
    main()
