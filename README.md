# docs-web-download

Marketplace для Claude Code плагина **docs-get-web** — скачивание веб-документации и конвертация в Markdown.

## Установка в Claude Code

```
/plugin marketplace add https://github.com/ixbtcom/docs-web-download
/plugin install docs-get-web@ixbtcom/docs-web-download
```

## Зависимости Python

```bash
pip install requests beautifulsoup4 lxml markdownify
```

## Использование

После установки доступна команда `/docs-get-web:fetch`.

Подробная документация: [plugins/docs-get-web/README.md](plugins/docs-get-web/README.md)
