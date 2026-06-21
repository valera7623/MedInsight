# Patients

## Why this section matters

A patient record is the central hub: documents, predictions, DICOM studies, and history are all linked to it.

## Patient list

1. Open **Patients** in the menu.
2. Use **search** by full name, phone, or email.
3. Switch pages with **Back** / **Forward**.

**Screenshot:** table with columns ID, Full name, date of birth, gender, phone, email, and a Record button.

!!! note "Who you see"
    The list depends on your role: a doctor sees their own patients and patients in their department; an administrator sees everyone in the clinic.

## Creating a patient

1. Click **+ New patient**.
2. Fill required fields: full name, date of birth, gender, phone, **department**.
3. Click **Save**.

**Why department matters:** it determines which staff can see the record.

## Patient record

Click **Record** in the list or go to `/patient/{id}`.

On the record you can:

- view basic patient data;
- see uploaded documents;
- use **Upload document**, **Run prediction**, **Export PDF**;
- view prediction history.

**Screenshot:** record with a Documents block, file table, and action buttons.

## Export

- **PDF** — report for a single patient (button on the record).
- **Excel** — list of all accessible patients (button on the Patients page).

## Deletion

Only **administrators** can delete patients. Deleting a patient also removes all their documents.

## FAQ

**I don't see the patient I need** — check department and role. Contact an administrator to assign a department or the “see all patients” flag.

**Researcher sees odd names** — this is expected: data is anonymized (`P-123 ANON`).
