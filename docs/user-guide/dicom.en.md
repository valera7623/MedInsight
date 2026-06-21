# DICOM — Medical Images

## Why DICOM

DICOM is the standard for medical images (CT, MRI, X-ray). MedInsight lets you upload `.dcm` files, view them in the browser, and use metadata in analytics.

## DICOM section

Open **DICOM** in the main menu.

**Screenshot:** grid of study cards with previews, modality (CT/MR), date, and Ready status.

## Uploading a study

1. Click **+ Upload DICOM**.
2. Select a **patient**.
3. Drag a `.dcm` file into the upload zone or choose it in the dialog.
4. Click **Upload**.

!!! info "Processing"
    Large files are processed **asynchronously** (1–5 minutes). Status “Processing” will change to “Ready”. Notification via WebSocket or Telegram.

## Viewing an image

1. In the list, click **View** on a ready study.
2. The **DICOM viewer** opens (`/dicom/viewer/{study_uid}`).

### Viewer tools

| Tool | Purpose |
|------|---------|
| Series (left) | Switch between image series |
| Frame slider | Navigate slices (CT) |
| 🔍+ / 🔍− | Zoom in / out |
| ↻ | Rotate |
| W/L | Brightness/contrast (window/level) |
| Drag | Pan the image |

**Screenshot:** dark viewing area with the image, toolbar at the top, series list on the left, metadata (Modality, Body Part) at the bottom.

## Filters

On the list page:

- **search** by description and modality;
- **modality** filter (CT, MR, US…);
- **status** filter (Ready / Processing / Error).

## Limitations

- Maximum file size is set by the administrator (default 500 MB).
- Study deletion — **administrator** only.

## Security

- Original DICOM is **encrypted** on the server.
- PNG frames are generated for viewing (DICOM is not sent to the browser again).
- Access only to patients in your clinic.
