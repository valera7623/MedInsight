# Documents

## Why upload documents

MedInsight automatically extracts from discharge notes:

- diagnoses;
- prescribed medications;
- text for AI predictions.

Without documents, predictions will be less accurate.

## Supported formats

| Format | Extension |
|--------|-----------|
| PDF | `.pdf` |
| Word | `.docx` |

## Upload from the dashboard

1. On the **Dashboard**, click **Upload document**.
2. Select a **patient** from the list.
3. Choose **document type**: discharge, laboratory, medical history.
4. Select a file or drag and drop it.
5. Click **Upload**.

**Screenshot:** “Upload document” modal with patient dropdown and file picker.

## What happens after upload

1. The file is **encrypted** and saved on the server.
2. Celery queues a **parsing** task (usually a few seconds).
3. Document status changes: `uploaded` → `processing` → `parsed`.
4. When ready, a notification arrives (WebSocket / Telegram, if configured).

## Viewing parsing results

1. Open the **patient record**.
2. In the documents table, find the file.
3. Status **parsed** means extraction is complete.

Extracted data is used on the dashboard (top diagnoses/medications) and in predictions.

## Downloading the original

Via API (for integrators): `GET /api/documents/{id}/download` — decryption happens in memory; the file is not written to disk in plaintext.

## Security

- Documents are stored **encrypted** (age).
- Access only for users in your clinic with permission to view the patient.
- All uploads are recorded in the **audit log**.

## Errors

| Status | What to do |
|--------|------------|
| `processing` | Wait 1–2 minutes |
| `failed` | Check file format; upload again |
| Error 403 | No permission for the patient |
