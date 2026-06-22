/** Poll Celery job status for DICOM ZIP processing with progress bar. */

let zipPollTimer = null;

function showDicomZipProgress(totalFiles) {
  const panel = document.getElementById('dicom-zip-progress-panel');
  const bar = document.getElementById('dicom-zip-progress-bar');
  const label = document.getElementById('dicom-zip-progress-label');
  if (!panel) return;
  panel.classList.remove('hidden');
  if (bar) {
    bar.style.width = '0%';
    bar.setAttribute('aria-valuenow', '0');
  }
  if (label) {
    label.textContent = totalFiles
      ? `Обработка ZIP: 0 / ${totalFiles} файлов`
      : 'Обработка ZIP-архива…';
  }
}

function hideDicomZipProgress() {
  const panel = document.getElementById('dicom-zip-progress-panel');
  if (panel) panel.classList.add('hidden');
  if (zipPollTimer) {
    clearInterval(zipPollTimer);
    zipPollTimer = null;
  }
}

function updateDicomZipProgress(processed, total, percent) {
  const bar = document.getElementById('dicom-zip-progress-bar');
  const label = document.getElementById('dicom-zip-progress-label');
  const pct = percent ?? (total ? Math.round((processed / total) * 100) : 0);
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.setAttribute('aria-valuenow', String(pct));
  }
  if (label) {
    label.textContent = total
      ? `Обработка ZIP: ${processed} / ${total} файлов (${pct}%)`
      : `Обработка ZIP… ${pct}%`;
  }
}

function startDicomZipProgressPolling(jobId, studyId, totalFiles, onComplete) {
  showDicomZipProgress(totalFiles);

  const poll = async () => {
    try {
      const params = new URLSearchParams({ study_id: String(studyId) });
      const res = await apiFetch(`/api/dicom/upload-zip/status/${encodeURIComponent(jobId)}?${params}`);
      if (!res.ok) return;
      const data = await res.json();

      updateDicomZipProgress(
        data.processed_files || 0,
        data.total_files || totalFiles || 0,
        data.percent
      );

      if (data.status === 'SUCCESS' || data.status === 'ready') {
        hideDicomZipProgress();
        if (onComplete) onComplete(data);
        return;
      }
      if (data.status === 'FAILURE' || data.status === 'failed') {
        hideDicomZipProgress();
        alert(data.error || 'Ошибка обработки ZIP-архива');
        return;
      }
    } catch (err) {
      console.error('ZIP status poll failed', err);
    }
  };

  poll();
  zipPollTimer = setInterval(poll, 2500);
}
