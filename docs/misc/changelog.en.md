# Changelog

MedInsight version history.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Full MkDocs documentation (`docs/`, `mkdocs.yml`)
- Scripts `docker_cleanup.sh`, `setup_swap.sh`

## [1.0.0] — 2026-06

### Added — Phase 12: DICOM
- Models `DicomStudy`, `DicomSeries`, `DicomFrame`
- DICOM upload, parsing, browser viewing
- Celery task `process_dicom`
- Frontend: `/dicom`, `/dicom/viewer/{study_uid}`
- Migration `014_add_dicom_tables.sql`

### Added — Phase 11: Dark mode
- Theme toggle, `UserPreference`, `DEFAULT_THEME`

### Added — Phase 10: Telegram
- Notification bot, account linking

### Added — Phase 9: Observability
- OpenTelemetry, WebSocket notifications

### Added — Phase 8: Backup
- Automatic Celery Beat backups
- Rotation by days/weeks/months

### Added — Phase 7: Export
- Excel/PDF export

### Added — Phase 6: Email
- SMTP, verification, password reset

### Added — Phase 5: Production hardening
- Rate limiting, graceful shutdown, health checks

### Added — Phase 4: Billing & Webhooks
- Stripe, YooKassa, Freemium/Pro/Enterprise plans
- Outbound webhooks

### Added — Phase 3: Multi-tenancy
- Tenants, age encryption, RBAC (7 roles)

### Added — Phase 2: Async & GPT
- Celery + Redis, ProxyAPI predictions

### Added — Phase 1: Core
- Patients, documents, PDF/DOCX parsing, dashboard

### Fixed
- User deletion (FK constraints, audit)
- Docker build timeout on VPS (`PIP_DEFAULT_TIMEOUT`)
- Department filter on dashboard (UI)
- Subscription page moved to separate route

### Changed
- `UserResponse`: `department_id`, `department_name`
- Registration: all roles + department selection

---

[Unreleased]: https://github.com/valera7623/MedInsight/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/valera7623/MedInsight/releases/tag/v1.0.0
