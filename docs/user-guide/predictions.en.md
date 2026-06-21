# Risk Predictions (AI)

## Why predictions

MedInsight analyzes patient data (documents, diagnoses, medications) and estimates:

- **readmission risk** — probability of repeat hospitalization;
- **complication risk** — probability of adverse outcome.

This is **decision support for clinicians**, not a replacement for clinical judgment.

## Who can run predictions

Doctors, heads of department, administrators — roles with write permission (`WRITE_ROLES`).

## Running a prediction

1. Open the **patient record**.
2. Ensure at least one **parsed document** (`parsed`).
3. Click **Run prediction**.
4. Wait for completion (usually 10–60 seconds).

**Screenshot:** patient record with Run prediction button and “Processing…” indicator.

## Result

On the record you see:

- **probability** of readmission and complications (%);
- **risk level**: low / medium / high;
- **explanation** from GPT (if ProxyAPI is available);
- prediction date.

On the **dashboard**, high-risk patients appear in a separate table.

## Plan limits

Monthly analysis count is limited by plan:

| Plan | Limit (example) |
|------|-----------------|
| Freemium | 5 |
| Pro | 100 |
| Enterprise | unlimited |

Current usage — on the **Subscription** page (`/subscription`).

When the limit is exceeded, the API returns **402 Payment Required**.

## Notifications

When a prediction is ready:

- **WebSocket** — browser update (if open);
- **Email** — if SMTP is configured;
- **Telegram** — if the account is linked.

## Validating predictions

A doctor can **confirm or reject** a prediction (via API `validate-prediction`) — data is used to improve the system.

## If GPT is unavailable

Without a ProxyAPI key or on network failure, the system uses **rule-based fallback** — simplified rule-based calculation without GPT explanation.

## Security

- Patient data does not leave your server except for ProxyAPI requests (if configured).
- Predictions are tied to **tenant_id** — other clinics cannot see them.
