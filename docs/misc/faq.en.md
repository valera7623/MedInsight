# FAQ

Frequently asked questions about MedInsight.

## General

### What is MedInsight?

A platform for storing patient records, analyzing medical documents, viewing DICOM, and AI risk predictions.

### Is internet required?

Yes, for the web UI and GPT predictions. Documents and DICOM are processed on your server.

### Does it support multiple clinics?

Yes, via **multi-tenancy** — each clinic has its own subdomain.

## Login and roles

### Forgot password

Use “Forgot password” on the login page (if SMTP is enabled). Otherwise contact an administrator.

### I don't see the Admin section

Available only for **admin** role.

### How is a researcher different from a viewer?

A **Researcher** sees anonymized data. A **Viewer** sees full data but cannot edit.

## Documents

### Which formats are supported?

PDF and DOCX.

### Status stuck on “processing”

Usually 1–2 minutes. If >10 min — check Celery worker (administrator).

### Is it safe to store discharge notes?

Files are encrypted with **age** on the server. Access via RBAC and tenant isolation.

## DICOM

### What is the maximum file size?

Default 500 MB (`DICOM_MAX_FILE_SIZE_MB`).

### Can I upload a folder of series?

Single `.dcm` upload and **DICOM ZIP** (multi-file studies) are supported.

## Predictions

### How accurate are predictions?

This is **decision support**, not a diagnosis. Accuracy depends on document completeness and the GPT model.

### What if GPT is unavailable?

Rule-based fallback runs without text explanation.

### Analysis limit exceeded

Upgrade your plan on the **Subscription** page or set `BILLING_ENABLED=false` (testing).

## Administration

### How do I update the system?

Push to `main` → GitHub Actions deploy. Or `./deploy.sh production` on VPS.

### How do I back up?

See [Backup](../admin-guide/backup.md). Auto backup when `BACKUP_ENABLED=true`.

### Error when deleting a user

Update to the latest version — FK constraints were fixed.

## Technical

### Where is Swagger API?

`/docs` on a running server.

### SQLite or PostgreSQL?

SQLite by default. PostgreSQL recommended for high load.

### How do I run documentation locally?

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

### Where is production documentation?

| Language | URL |
|----------|-----|
| Russian | `https://fileguardian.com.ru/help/` |
| English | `https://fileguardian.com.ru/help/en/` |

Use the language switcher in the docs header, or let the site auto-detect your browser language on first visit. API Swagger — `/docs`.

## Contacts

- GitHub Issues: [valera7623/MedInsight](https://github.com/valera7623/MedInsight/issues)
- Clinic administrator email — for access and password reset
