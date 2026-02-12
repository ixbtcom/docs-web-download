# docs-get-web

Плагин Claude Code для скачивания веб-документации и конвертации в Markdown.

## Возможности

- Batch-скачивание целых разделов документации по преднастроенным профилям
- Скачивание отдельных страниц с конвертацией HTML → Markdown
- Поддержка нескольких типов сайтов:
  - **Docusaurus** — docs.jitsu.com и аналогичные
  - **Timeweb Cloud** — timeweb.cloud/docs
  - **Raw Markdown** — GitHub raw файлы и прямые .md ссылки
- Скачивание изображений в локальную папку
- Генерация index.md с оглавлением

## Установка

### Требования

Python 3.11+ и зависимости:

```bash
pip install requests beautifulsoup4 lxml markdownify
```

### Установка плагина в Claude Code

```bash
# Из локальной директории (для разработки)
claude --plugin-dir /path/to/docs-web-download

# Или через marketplace (после публикации)
/plugin marketplace add https://github.com/ixbtcom/docs-web-download
/plugin install docs-get-web@ixbtcom/docs-web-download
```

## Использование

### В Claude Code

```
/docs-get-web:fetch jitsu
/docs-get-web:fetch timeweb-k8s
```

### Через CLI напрямую

#### Batch-скачивание по профилю

```bash
# Все источники → ./docs/
python3 skills/fetch/scripts/fetch_docs.py

# Конкретный источник
python3 skills/fetch/scripts/fetch_docs.py jitsu

# С указанием выходной папки
python3 skills/fetch/scripts/fetch_docs.py jitsu --output /path/to/docs
```

#### Скачивание одной страницы

```bash
# Docusaurus-сайт
python3 skills/fetch/scripts/fetch_single.py \
  --parser docusaurus \
  --url "https://docs.jitsu.com/self-hosting/configuration" \
  --output docs/jitsu-config.md

# Raw markdown (GitHub)
python3 skills/fetch/scripts/fetch_single.py \
  --parser raw \
  --url "https://raw.githubusercontent.com/user/repo/main/README.md" \
  --output docs/readme.md

# Timeweb Cloud
python3 skills/fetch/scripts/fetch_single.py \
  --parser timeweb \
  --url "https://timeweb.cloud/docs/k8s/helm" \
  --output docs/helm.md
```

## Профили источников

Профили настраиваются в `skills/fetch/scripts/fetch_docs.py` в словаре `SOURCES`:

| Профиль | Сайт | Парсер | Страниц |
|---------|------|--------|---------|
| `timeweb-k8s` | timeweb.cloud/docs/k8s | timeweb | 33 |
| `jitsu` | docs.jitsu.com/self-hosting | docusaurus + raw | 6 |

### Добавление нового профиля

```python
SOURCES["my-source"] = {
    "base_url": "https://docs.example.com",
    "parser": "docusaurus",        # timeweb | docusaurus
    "output_dir": "my-source",     # подпапка в docs/
    "path_prefix": "/docs",        # убирается из slug-имени файла
    "index_title": "My Source — Docs",
    "doc_paths": [
        "/docs/getting-started",
        "/docs/configuration",
    ],
    "raw_urls": [
        ("https://raw.githubusercontent.com/.../config.md", "config"),
    ],
}
```

## Добавление нового парсера

Для поддержки нового типа сайта:

1. Создай класс `XxxMarkdownConverter(MarkdownConverter)` с обработкой:
   - `convert_pre` — блоки кода
   - `convert_code` — инлайн-код
   - `convert_img` — изображения
   - `convert_h*` — заголовки

2. Создай функцию `clean_xxx_article(article: Tag) -> Tag` для удаления навигации и мусора

3. Создай функцию `fetch_xxx(doc_path, source_cfg, out_dir, session)` — основной парсер

4. Зарегистрируй: `PARSERS["xxx"] = fetch_xxx`

## Структура проекта

```
docs-web-download/
├── .claude-plugin/
│   └── plugin.json              # Манифест плагина
├── skills/
│   └── fetch/
│       ├── SKILL.md             # Описание skill для Claude Code
│       └── scripts/
│           ├── fetch_docs.py    # Batch-скачивание по профилям
│           └── fetch_single.py  # Скачивание одной страницы
├── requirements.txt
└── README.md
```

## Лицензия

MIT
