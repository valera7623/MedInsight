# MedInsight Documentation

Полная документация платформы MedInsight — клинической аналитики с поддержкой документов, DICOM, прогнозов GPT и мультитенантности.

## Быстрый старт

```bash
pip install mkdocs-material mkdocs-mermaid2-plugin
mkdocs serve
```

Откройте http://127.0.0.1:8000

## Сборка сайта

```bash
mkdocs build
# Результат: site/
```

## Структура

| Раздел | Аудитория | Описание |
|--------|-----------|----------|
| [user-guide/](user-guide/) | Врачи, медсёстры | Работа с пациентами, документами, DICOM |
| [admin-guide/](admin-guide/) | DevOps, админы | Деплой, конфигурация, бэкапы |
| [developer-guide/](developer-guide/) | Разработчики | Архитектура, БД, агенты |
| [api/](api/) | Интеграторы | REST API с примерами |
| [deployment/](deployment/) | DevOps | Docker, VPS, CI/CD |
| [misc/](misc/) | Все | Changelog, FAQ, глоссарий |

## Интерактивная API-документация

| URL | Описание |
|-----|----------|
| `/docs` | Swagger UI (OpenAPI) |
| `/help/` | Руководства пользователя, админа, разработчика (MkDocs) |

На проде: `https://fileguardian.com.ru/help/`

## Языки

- Основной язык: **русский**
- API-эндпоинты и код: английские идентификаторы (стандарт REST)
