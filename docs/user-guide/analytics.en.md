# Analytics and Dashboard

## Why the dashboard

The dashboard gives a clinic overview: patient and document counts, common diagnoses and medications, and DICOM studies.

## Opening

After login you land on the **Dashboard** (`/`).

**Screenshot:** top row with user full name; cards for Patients, Documents, Diagnoses; two Chart.js charts.

## Department filter

In the dashboard header, select a **department** from the dropdown or “All departments”.

**Why:** view statistics for your department only or the whole clinic (if you have permission).

## Dashboard blocks

### Summary numbers

| Card | Content |
|------|---------|
| Patients | Count of accessible patients |
| Documents | Uploaded and parsed |
| Diagnoses | Unique diagnoses in data |

### Charts

- **Top 5 diagnoses** — bar chart.
- **Top 5 medications** — bar chart.

Charts automatically adapt to **dark theme**.

### Predictions and risks

- count of patients with **high risk**;
- risk charts by department and month;
- table of high-risk patients.

More detail: [Predictions](predictions.md).

### Webhooks

Block for **outbound integrations** (advanced users). Usually configured by an administrator.

### Recent patients

Quick links to recently added records.

## DICOM in analytics

The dashboard includes DICOM metadata:

- study count;
- distribution by **modality** (CT, MR…);
- distribution by **body region**.

## Data export

- **Excel** — patient, document, and prediction lists (buttons on respective pages).
- **PDF** — report for a single patient.

## Data refresh

The dashboard updates on page reload. New documents and predictions appear after Celery parsing/processing completes.
