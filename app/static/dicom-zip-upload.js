/** DICOM ZIP archive upload modal and API integration. */

function openDicomZipModal() {
  const modal = document.getElementById('dicom-zip-upload-modal');
  if (modal) modal.classList.remove('hidden');
}

function closeDicomZipModal() {
  const modal = document.getElementById('dicom-zip-upload-modal');
  if (modal) modal.classList.add('hidden');
  const form = document.getElementById('dicom-zip-upload-form');
  if (form) form.reset();
  const nameEl = document.getElementById('dicom-zip-file-name');
  if (nameEl) nameEl.textContent = '';
  const errEl = document.getElementById('dicom-zip-upload-error');
  if (errEl) errEl.classList.add('hidden');
  hideDicomZipProgress();
}

function setupDicomZipDropzone() {
  const zone = document.getElementById('dicom-zip-dropzone');
  const input = document.getElementById('dicom-zip-file');
  const nameEl = document.getElementById('dicom-zip-file-name');
  if (!zone || !input) return;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('dicom-dropzone-active');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dicom-dropzone-active'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dicom-dropzone-active');
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      nameEl.textContent = e.dataTransfer.files[0].name;
    }
  });
  input.addEventListener('change', () => {
    nameEl.textContent = input.files[0]?.name || '';
  });
}

function setupDicomZipUpload(onSuccess) {
  const form = document.getElementById('dicom-zip-upload-form');
  if (!form) return;

  setupDicomZipDropzone();

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const errEl = document.getElementById('dicom-zip-upload-error');
    errEl.classList.add('hidden');

    const fileInput = document.getElementById('dicom-zip-file');
    const patientId = document.getElementById('dicom-zip-patient')?.value;
    if (!patientId) {
      errEl.textContent = 'Выберите пациента';
      errEl.classList.remove('hidden');
      return;
    }
    if (!fileInput.files?.length) {
      errEl.textContent = 'Выберите ZIP-архив';
      errEl.classList.remove('hidden');
      return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.zip')) {
      errEl.textContent = 'Только .zip архивы';
      errEl.classList.remove('hidden');
      return;
    }

    const formData = new FormData();
    formData.append('zip_file', file);
    formData.append('patient_id', patientId);

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const res = await apiFetch('/api/dicom/upload-zip', {
        method: 'POST',
        body: formData,
        headers: {},
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(formatApiError(data.detail) || `Ошибка загрузки ZIP (${res.status})`);

      closeDicomZipModal();

      if (data.job_id) {
        startDicomZipProgressPolling(data.job_id, data.study_id, data.total_files, onSuccess);
      } else if (onSuccess) {
        onSuccess(data);
      }
    } catch (err) {
      errEl.textContent = err.message || 'Ошибка загрузки';
      errEl.classList.remove('hidden');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  document.querySelectorAll('#dicom-zip-upload-modal .modal-close').forEach(btn => {
    btn.addEventListener('click', closeDicomZipModal);
  });
}

function initDicomZipUpload(onSuccess) {
  document.getElementById('upload-dicom-zip-btn')?.addEventListener('click', async () => {
    await loadPatientsForSelect('dicom-zip-patient');
    openDicomZipModal();
  });
  setupDicomZipUpload(onSuccess);
}
