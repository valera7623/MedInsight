# Control mapping (SOC 2 / HIPAA / GDPR)

| Control | Standard | Implementation |
|---------|----------|----------------|
| Access control | SOC2 CC6, HIPAA §164.312(a) | RBAC, JWT, optional SSO/MFA |
| Encryption at rest | SOC2 CC6, HIPAA §164.312(a)(2)(iv) | age file encryption; optional PHI field encryption |
| Audit logging | SOC2 CC7, HIPAA §164.312(b) | Signed append-only audit log |
| Tenant isolation | GDPR Art. 32 | App-layer + optional PostgreSQL RLS |
| Session management | SOC2 CC6 | Redis session store, logout, revoke |
| Password policy | SOC2 CC6 | Min length, complexity, optional HIBP |
| Backup & recovery | SOC2 A1 | pg_dump, S3, restore API |
| Monitoring | SOC2 CC7 | Prometheus, OTEL, health probes |
| DSAR | GDPR Art. 15–17 | DSAR export/erase API |
| Vendor management | SOC2 CC9 | Subprocessors list |

Evidence: CI test results, audit exports, access reviews (quarterly).
