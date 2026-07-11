# Roadmap

Планы развития MedInsight.

## Q3 2026

### Документация и DX
- [x] MkDocs-сайт документации
- [ ] Английская версия user-guide
- [x] Автогенерация API markdown из OpenAPI

### DICOM
- [x] Поддержка DICOM ZIP (многофайловые исследования)
- [x] Аннотации на снимках
- [x] Интеграция DICOM metadata в GPT-прогнозы

### Безопасность
- [x] Ограничение self-registration (без admin/head_of_department)
- [x] Password reset end-to-end (API + UI)
- [x] FHIR API: JWT + tenant scoping
- [x] Tenant spoofing fix в usage_limit/cache middleware
- [x] XSS hardening в AI/prediction HTML
- [x] Fail-fast на default secrets в production
- [x] JWT refresh tokens (access 1h + refresh 7d)
- [x] Rate limits на upload/predict/admin
- [x] 2FA (TOTP)
- [x] Audit export в SIEM (Phase 13, feature flag)
- [x] PostgreSQL как рекомендуемая БД для prod

## Q4 2026

### Клинические функции
- [x] HL7 FHIR import/export (Phase 14)
- [x] Шаблоны отчётов PDF (Phase 15)
- [x] Календарь приёмов (Phase 16)

### AI
- [ ] Fine-tuned модели на анонимизированных данных
- [x] Объяснимость прогнозов (SHAP, Phase 17)
- [x] RAG по клиническим guidelines (self-healing)

### Инфраструктура
- [ ] Kubernetes Helm chart
- [ ] Multi-region backup (S3)
- [ ] Horizontal scaling Celery workers

## 2027+

- Мобильное приложение (React Native)
- Интеграция с ЕГИСЗ (РФ)
- Offline-first для полевых исследований
- Сертификация как медизделие (если потребуется)

## Как предложить фичу

1. Issue на [GitHub](https://github.com/valera7623/MedInsight/issues)
2. Опишите use case и роль пользователя
3. Приоритет определяется по запросам клиник и безопасности

## Принципы

- **Privacy first** — шифрование, tenant isolation
- **Clinical safety** — AI как decision support, не diagnosis
- **Simple UX** — для врачей без IT-обучения
