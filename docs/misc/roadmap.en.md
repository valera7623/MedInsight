# Roadmap

MedInsight development plans.

## Q3 2026

### Documentation and DX
- [x] MkDocs documentation site
- [ ] English user-guide version
- [ ] Auto-generate API markdown from OpenAPI

### DICOM
- [ ] DICOM ZIP support (multi-file studies)
- [ ] Image annotations
- [ ] DICOM metadata integration in GPT predictions

### Security
- [ ] 2FA (TOTP)
- [ ] Audit export to SIEM
- [ ] PostgreSQL as recommended prod DB

## Q4 2026

### Clinical features
- [ ] HL7 FHIR import/export
- [ ] PDF report templates
- [ ] Appointment calendar

### AI
- [ ] Fine-tuned models on anonymized data
- [ ] Prediction explainability (SHAP-like)
- [ ] RAG over clinical guidelines

### Infrastructure
- [ ] Kubernetes Helm chart
- [ ] Multi-region backup (S3)
- [ ] Horizontal scaling Celery workers

## 2027+

- Mobile app (React Native)
- Integration with EGISZ (Russia)
- Offline-first for field studies
- Medical device certification (if required)

## How to suggest a feature

1. Open an issue on [GitHub](https://github.com/valera7623/MedInsight/issues)
2. Describe the use case and user role
3. Priority is set by clinic requests and security needs

## Principles

- **Privacy first** — encryption, tenant isolation
- **Clinical safety** — AI as decision support, not diagnosis
- **Simple UX** — for clinicians without IT training
