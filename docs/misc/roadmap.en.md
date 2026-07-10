# Roadmap

MedInsight development plans.

## Q3 2026

### Documentation and DX
- [x] MkDocs documentation site
- [ ] English user-guide version
- [x] Auto-generate API markdown from OpenAPI

### DICOM
- [x] DICOM ZIP support (multi-file studies)
- [x] Image annotations
- [x] DICOM metadata integration in GPT predictions

### Security
- [x] Restrict self-registration (no admin/head_of_department)
- [x] Password reset end-to-end (API + UI)
- [x] FHIR API: JWT + tenant scoping
- [x] Tenant spoofing fix in usage_limit/cache middleware
- [x] XSS hardening in AI/prediction HTML
- [x] Fail-fast on default secrets in production
- [x] JWT refresh tokens (1h access + 7d refresh)
- [x] Rate limits on upload/predict/admin
- [ ] 2FA (TOTP)
- [x] Audit export to SIEM (Phase 13, feature flag)
- [x] PostgreSQL as recommended production DB

## Q4 2026

### Clinical features
- [x] HL7 FHIR import/export (Phase 14)
- [x] PDF report templates (Phase 15)
- [x] Appointments calendar (Phase 16)

### AI
- [ ] Fine-tuned models on anonymized data
- [x] Prediction explainability (SHAP, Phase 17)
- [x] RAG on clinical guidelines (self-healing)

### Infrastructure
- [ ] Kubernetes Helm chart
- [ ] Multi-region backup (S3)
- [ ] Horizontal scaling Celery workers

## 2027+

- Mobile app (React Native)
- EGISZ integration (Russia)
- Offline-first for field research
- Medical device certification (if required)

## How to suggest a feature

1. Open an issue on [GitHub](https://github.com/valera7623/MedInsight/issues)
2. Describe the use case and user role
3. Priority is driven by clinic demand and security

## Principles

- **Privacy first** — encryption, tenant isolation
- **Clinical safety** — AI as decision support, not diagnosis
- **Simple UX** — for clinicians without IT training
