---
name: fetch
description: Download web documentation and convert to markdown. Use when need to fetch docs from websites (Docusaurus, Timeweb Cloud, GitHub raw) and save locally as .md files. Supports batch downloading with pre-configured source profiles and single URL fetching.
disable-model-invocation: true
allowed-tools: Bash(python3 *)
argument-hint: <source-name-or-url> [output-dir]
---

# Web Documentation Fetcher

Скачивает веб-документацию и конвертирует в чистый Markdown для локального использования.

## Поддерживаемые источники

### Предконфигурированные профили (batch)

Скрипт `fetch_docs.py` содержит профили источников в словаре `SOURCES`. Каждый профиль включает:
- Базовый URL сайта
- Тип парсера (timeweb, docusaurus)
- Список URL-ов страниц
- Raw URL-ы (GitHub markdown)
- Выходную директорию

Текущие профили: `timeweb-k8s`, `jitsu`

### Типы парсеров

| Парсер | Сайты | Как извлекает контент |
|--------|-------|-----------------------|
| `timeweb` | timeweb.cloud | `articleBody` + кастомный конвертер |
| `docusaurus` | docs.jitsu.com и т.п. | `<article>` / `<main>` + markdownify |
| `raw` | GitHub raw URLs | Скачивает как есть |

## Использование

### Скачать по профилю (batch)

```bash
# Все настроенные источники
python3 ${CLAUDE_PLUGIN_ROOT}/skills/fetch/scripts/fetch_docs.py

# Конкретный источник
python3 ${CLAUDE_PLUGIN_ROOT}/skills/fetch/scripts/fetch_docs.py jitsu
python3 ${CLAUDE_PLUGIN_ROOT}/skills/fetch/scripts/fetch_docs.py timeweb-k8s
```

### Скачать одну страницу

```bash
# Docusaurus-сайт
python3 ${CLAUDE_PLUGIN_ROOT}/skills/fetch/scripts/fetch_single.py \
  --parser docusaurus \
  --url "https://docs.example.com/getting-started" \
  --output docs/example/getting-started.md

# Raw markdown (GitHub)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/fetch/scripts/fetch_single.py \
  --parser raw \
  --url "https://raw.githubusercontent.com/user/repo/main/README.md" \
  --output docs/readme.md

# Timeweb Cloud
python3 ${CLAUDE_PLUGIN_ROOT}/skills/fetch/scripts/fetch_single.py \
  --parser timeweb \
  --url "https://timeweb.cloud/docs/k8s/helm" \
  --output docs/timeweb/helm.md
```

## Добавление нового источника

Чтобы добавить новый профиль, отредактируй `SOURCES` в `fetch_docs.py`:

```python
SOURCES["my-source"] = {
    "base_url": "https://docs.example.com",
    "parser": "docusaurus",        # или "timeweb"
    "output_dir": "my-source",
    "path_prefix": "/docs",        # общий префикс URL-ов (убирается из slug)
    "index_title": "Docs — My Source",
    "doc_paths": [
        "/docs/getting-started",
        "/docs/configuration",
    ],
    "raw_urls": [
        # (URL, slug-имя)
        ("https://raw.githubusercontent.com/.../README.md", "readme"),
    ],
}
```

## Добавление нового парсера

Для нового типа сайта:
1. Создай класс `XxxMarkdownConverter(MarkdownConverter)` с обработкой `<pre>`, `<code>`, `<img>`, `<h*>`
2. Создай функцию `clean_xxx_article(article: Tag) -> Tag` для удаления мусора
3. Создай функцию `fetch_xxx(doc_path, source_cfg, out_dir, session)` — основной парсер
4. Зарегистрируй в `PARSERS["xxx"] = fetch_xxx`

## Зависимости

```bash
pip install requests beautifulsoup4 lxml markdownify
```

## Аргументы ($ARGUMENTS)

Если передан аргумент `$ARGUMENTS`:
- Если это имя профиля (jitsu, timeweb-k8s) — скачать batch
- Если это URL — скачать одну страницу в текущую директорию
- Если два аргумента — URL и выходной путь
