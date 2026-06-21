# Changelog

История версий MedInsight.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

## [Unreleased]

### Added
- Полная документация MkDocs (`docs/`, `mkdocs.yml`)
- Скрипты `docker_cleanup.sh`, `setup_swap.sh`

## [1.0.0] — 2026-06

### Added — Phase 12: DICOM
- Модели `DicomStudy`, `DicomSeries`, `DicomFrame`
- Загрузка, парсинг, просмотр DICOM в браузере
- Celery-задача `process_dicom`
- Frontend: `/dicom`, `/dicom/viewer/{study_uid}`
- Миграция `014_add_dicom_tables.sql`

### Added — Phase 11: Dark mode
- Переключатель темы, `UserPreference`, `DEFAULT_THEME`

### Added — Phase 10: Telegram
- Бот уведомлений, привязка аккаунта

### Added — Phase 9: Observability
- OpenTelemetry, WebSocket notifications

### Added — Phase 8: Backup
- Автоматические бэкапы Celery Beat
- Ротация по дням/неделям/месяцам

### Added — Phase 7: Export
- Excel/PDF экспорт

### Added — Phase 6: Email
- SMTP, верификация, сброс пароля

### Added — Phase 5: Production hardening
- Rate limiting, graceful shutdown, health checks

### Added — Phase 4: Billing & Webhooks
- Stripe, ЮKassa, тарифы Freemium/Pro/Enterprise
- Исходящие webhooks

### Added — Phase 3: Multi-tenancy
- Tenants, шифрование age, RBAC (7 ролей)

### Added — Phase 2: Async & GPT
- Celery + Redis, ProxyAPI прогнозы

### Added — Phase 1: Core
- Пациенты, документы, парсинг PDF/DOCX, дашборд

### Fixed
- Удаление пользователей (FK constraints, audit)
- Docker build timeout на VPS (`PIP_DEFAULT_TIMEOUT`)
- Фильтр отделений на дашборде (UI)
- Страница подписки вынесена отдельно

### Changed
- `UserResponse`: `department_id`, `department_name`
- Регистрация: все роли + выбор отделения

---

[Unreleased]: https://github.com/valera7623/MedInsight/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/valera7623/MedInsight/releases/tag/v1.0.0
