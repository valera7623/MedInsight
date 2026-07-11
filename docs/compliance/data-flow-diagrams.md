# Data flow diagrams

## Document upload

```
Clinician → HTTPS → MedInsight API → Parser → Entity extraction
                              ↓
                    Encrypted file storage (age)
                              ↓
                    PostgreSQL metadata (tenant-scoped)
```

## AI analysis (optional)

```
Document text (minimized) → ProxyAPI/OpenAI → Structured JSON → PostgreSQL
```

Disable or restrict AI parsing per tenant when subprocessors are not approved.

## FHIR export

```
Patient record → FHIR R4 bundle → HTTPS download / EHR endpoint
```

## SIEM

```
Audit event → HMAC signature → Batch export / webhook → Customer SIEM
```

PII is redacted in SIEM payloads when `SIEM_EXPORT_ENABLED` formatting is active.
