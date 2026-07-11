# Subprocessors

| Vendor | Purpose | Data types | Location |
|--------|---------|------------|----------|
| Hosting provider (VPS/cloud) | Infrastructure | All platform data | Configurable region |
| OpenAI via ProxyAPI | Optional AI parsing | Document excerpts | Per ProxyAPI policy |
| Stripe | Card payments (Pro/Enterprise) | Billing metadata | US/EU |
| ЮKassa | RU payments | Billing metadata | RU |
| Telegram | Optional notifications | User IDs, alerts | Global |
| Customer SIEM | Audit export | Redacted audit events | Customer-controlled |

Review and update this list before enterprise contracts. Enable only required integrations per tenant.
