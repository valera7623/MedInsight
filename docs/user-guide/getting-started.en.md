# Getting Started

Guide for doctors, nurses, researchers, and viewers.

## Why MedInsight

MedInsight helps you:

- store patient records in one place;
- upload discharge notes and automatically extract diagnoses and medications;
- view DICOM images in the browser;
- receive AI predictions for readmission and complication risks;
- see clinic statistics on the dashboard.

## First login

1. Open your clinic URL, for example: `https://medinsight.fileguardian.info/login`
2. Select your **clinic (subdomain)** from the list.
3. Enter your **email** and **password**.
4. Click **Sign in**.

**Screenshot:** login page with the MedInsight logo, fields for Clinic, Email, Password, and a Sign in button. On the right — theme toggle (☀️/🌙).

## Registration

If you do not have an account:

1. On the login page, click **Register**.
2. Fill in full name, email, and password.
3. Select a **role** (see the table below).
4. For doctor, nurse, or head of department — select a **department**.
5. Click **Create account**.

### Registration roles

| Role | Who it's for | What you can do |
|------|--------------|-----------------|
| **Doctor** | Attending physician | Patients, documents, predictions, DICOM |
| **Nurse** | Nursing staff | Department view, export |
| **Head of department** | Department lead | Full department management |
| **Administrator** | Clinic IT/management | Users, departments, audit |
| **Researcher** | Analytics without PII | View anonymized data |
| **Viewer** | Audit, oversight | View full data, export |

!!! tip "Researcher vs Viewer"
    A **Researcher** sees data **without full name and contact details** (anonymized). A **Viewer** sees **full** records but cannot edit them.

## Main menu

After login, the top bar provides these sections:

| Item | Purpose |
|------|---------|
| **Dashboard** | Statistics, charts, predictions |
| **Patients** | List and records |
| **DICOM** | Medical images |
| **Subscription** | Plan and analysis limits |
| **Admin** | Administrators only |

**Screenshot:** top navigation with Dashboard active; Sign out button and theme toggle on the right.

## User information

On the dashboard, below the heading, a line shows:

> **Ivan Ivanov · Doctor · Therapy**

This is your full name, role, and department (if assigned).

## Dark theme

Click ☀️/🌙 in the top-right corner. Your choice is saved automatically.

## Next steps

- [Working with patients](patients.md)
- [Uploading documents](documents.md)
- [DICOM images](dicom.md)
