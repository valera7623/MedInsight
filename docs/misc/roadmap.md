# Roadmap

Планы развития MedInsight.

## Q3 2026

### Документация и DX
- [x] MkDocs-сайт документации
- [ ] Английская версия user-guide
- [ ] Автогенерация API markdown из OpenAPI

### DICOM
- [ ] Поддержка DICOM ZIP (многофайловые исследования)
- [ ] Аннотации на снимках
- [ ] Интеграция DICOM metadata в GPT-прогнозы

### Безопность
- [ ] 2FA (TOTP)
- [ ] Audit export в SIEM
- [ ] PostgreSQL как рекомендуемая БД для prod

## Q4 2026

### Клинические функции
- [ ] HL7 FHIR import/export
- [ ] Шаблоны отчётов PDF
- [ ] Календарь приёмов

### AI
- [ ] Fine-tuned модели на анонимизированных данных
- [ ] Объяснимость прогнозов (SHAP-like)
- [ ] RAG по клиническим guidelines

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
