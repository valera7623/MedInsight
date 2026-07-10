/** Annotation export helpers (JSON, GeoJSON, PDF, batch ZIP). */

const AnnotationExport = {
  async downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },

  async _fetchExport(path, filename, contentType) {
    const res = await apiFetch(path);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      notifyError(formatApiError(err.detail) || 'Export failed');
      return;
    }
    const blob = await res.blob();
    await this.downloadBlob(blob, filename);
  },

  exportJson(frameId, anonymize = false) {
    const q = anonymize ? '?anonymize=true' : '';
    return this._fetchExport(
      `/api/dicom/annotations/export/json/${frameId}${q}`,
      `annotations_frame_${frameId}.json`,
      'application/json'
    );
  },

  exportGeoJson(frameId) {
    return this._fetchExport(
      `/api/dicom/annotations/export/geojson/${frameId}`,
      `annotations_frame_${frameId}.geojson`,
      'application/geo+json'
    );
  },

  exportPdf(frameId) {
    return this._fetchExport(
      `/api/dicom/annotations/export/pdf/${frameId}`,
      `annotations_frame_${frameId}.pdf`,
      'application/pdf'
    );
  },

  async exportBatch(frameIds, format = 'json') {
    const res = await apiFetch('/api/dicom/annotations/export/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frame_ids: frameIds, format, zip: true }),
    });
    if (!res.ok) {
      notifyError('Batch export failed');
      return;
    }
    const blob = await res.blob();
    await this.downloadBlob(blob, `annotations_${format}.zip`);
  },
};

window.AnnotationExport = AnnotationExport;
