# Incident response

## Severity levels

| Level | Example | Response |
|-------|---------|----------|
| S1 | Data breach, ransomware | Immediate; exec + DPO |
| S2 | Auth bypass, tenant leak | < 4 hours |
| S3 | Service outage | Standard ops |

## Breach notification timelines

- **GDPR** — supervisory authority within 72 hours when risk to rights
- **152-FZ** — Roskomnadzor per operator obligations
- **HIPAA** — covered entities notify per BAA; processor assists

## Steps

1. Contain — revoke sessions, rotate keys, block IPs
2. Assess — audit logs, SIEM, `GET /api/admin/audit`
3. Notify — tenants, regulators per legal review
4. Remediate — patch, post-mortem, update control mapping

Runbook owner: platform security team.
