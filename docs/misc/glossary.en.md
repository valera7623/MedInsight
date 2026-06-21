# Glossary

| Term | Definition |
|------|------------|
| **MedInsight** | Clinical analytics platform |
| **Tenant** | Clinic/organization in multi-tenant system |
| **Subdomain** | Unique clinic identifier at login |
| **RBAC** | Role-Based Access Control |
| **JWT** | JSON Web Token — API authorization token |
| **Celery** | Background task queue (parsing, DICOM, predictions) |
| **Redis** | In-memory store — Celery broker and cache |
| **age** | Modern file encryption (PGP alternative) |
| **DICOM** | Digital Imaging and Communications in Medicine — medical imaging standard |
| **Modality** | DICOM study type: CT, MR, US, XR… |
| **Study / Series / Frame** | DICOM hierarchy: study → series → frame |
| **ProxyAPI** | Proxy to OpenAI API (Russia) |
| **GPT** | Generative Pre-trained Transformer — language model for predictions |
| **Readmission** | Repeat hospitalization |
| **Complication risk** | Risk of complications |
| **Parsed data** | Diagnoses and medications extracted from documents |
| **Webhook** | HTTP callback on system events |
| **WebSocket** | Bidirectional channel for real-time notifications |
| **Freemium / Pro / Enterprise** | Subscription plans |
| **Self-healing** | Auto-recovery on Redis/Celery failures |
| **Audit log** | Log of user actions |
| **Anonymization** | De-identification of PII for researcher role |
| **OpenAPI** | REST API specification (Swagger) |
| **MkDocs** | Static documentation site generator |
| **VPS** | Virtual Private Server |
| **CI/CD** | Continuous Integration / Deployment |
| **OTEL** | OpenTelemetry — distributed tracing |
| **FHIR** | Fast Healthcare Interoperability Resources (exchange standard) |
| **ICD-10** | International Classification of Diseases |
| **W/L (Window/Level)** | Brightness and contrast of DICOM images |
| **SPA** | Single Page Application |
| **ORM** | Object-Relational Mapping (SQLAlchemy) |

## Role codes

| Code | English name |
|------|--------------|
| `admin` | Administrator |
| `head_of_department` | Head of department |
| `doctor` | Doctor |
| `nurse` | Nurse |
| `researcher` | Researcher |
| `viewer` | Viewer |
| `superadmin` | Platform superadmin |
