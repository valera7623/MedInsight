let dicomPage = 1;
let dicomPollTimer = null;
const DICOM_POLL_KEY = 'dicomProcessingStudyId';

function stopDicomStatusPoll() {
  if (dicomPollTimer) {
    clearInterval(dicomPollTimer);
    dicomPollTimer = null;
  }
}

function startDicomStatusPoll(studyId) {
  if (!studyId) return;
  sessionStorage.setItem(DICOM_POLL_KEY, String(studyId));
  stopDicomStatusPoll();
  const panel = document.getElementById('dicom-processing-panel');
  const label = document.getElementById('dicom-processing-label');
  if (panel) panel.classList.remove('hidden');
  if (label) label.textContent = 'Обработка DICOM…';

  const poll = async () => {
    try {
      const res = await apiFetch(`/api/dicom/upload/status/${studyId}`);
      if (res.status === 404) {
        stopDicomStatusPoll();
        sessionStorage.removeItem(DICOM_POLL_KEY);
        loadDicomStudies(dicomPage);
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      if (label && data.num_instances) {
        label.textContent = `Обработка DICOM… (${data.num_instances} кадров)`;
      }
      if (data.status === 'ready' || data.status === 'failed') {
        stopDicomStatusPoll();
        sessionStorage.removeItem(DICOM_POLL_KEY);
        if (panel) panel.classList.add('hidden');
        if (data.status === 'failed') {
          alert(data.error_message || 'Ошибка обработки DICOM');
        }
        loadDicomStudies(dicomPage);
      }
    } catch (err) {
      console.error('DICOM status poll failed', err);
    }
  };

  poll();
  dicomPollTimer = setInterval(poll, 2000);
}

async function resumeDicomProcessingPolls() {
  const storedId = sessionStorage.getItem(DICOM_POLL_KEY);
  if (storedId) {
    startDicomStatusPoll(Number(storedId));
    return;
  }
  try {
    const res = await apiFetch('/api/dicom/studies?status=processing&limit=5');
    if (!res.ok) return;
    const data = await res.json();
    const processing = (data.items || []).find(s => s.status === 'processing');
    if (processing?.id) {
      startDicomStatusPoll(processing.id);
    }
  } catch (err) {
    console.error('Failed to resume DICOM polls', err);
  }
}

async function deleteDicomStudy(studyUid, label) {
  const name = label || studyUid;
  if (!confirm(`Удалить DICOM-исследование «${name}»? Файлы и кадры будут удалены безвозвратно.`)) {
    return;
  }
  try {
    const res = await apiFetch(`/api/dicom/studies/${encodeURIComponent(studyUid)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(formatApiError(data.detail) || `Ошибка удаления (${res.status})`);
    }
    loadDicomStudies(dicomPage);
  } catch (err) {
    alert(err.message || 'Ошибка удаления');
  }
}

async function downloadDicomArchive(studyUid, filename) {
  try {
    const res = await apiFetch(`/api/dicom/studies/${encodeURIComponent(studyUid)}/archive`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(formatApiError(data.detail) || 'Не удалось скачать архив');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `${studyUid}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert(err.message || 'Ошибка скачивания');
  }
}

function formatStudyDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleDateString('ru-RU');
  } catch {
    return value;
  }
}

function statusBadge(status) {
  const map = {
    ready: 'badge-success',
    processing: 'badge-warning',
    failed: 'badge-danger',
    uploaded: 'badge-secondary',
  };
  const cls = map[status] || 'badge-secondary';
  const labels = {
    ready: 'Готово',
    processing: 'Обработка',
    failed: 'Ошибка',
    uploaded: 'Загружено',
  };
  return `<span class="badge ${cls}">${labels[status] || status}</span>`;
}

async function loadDicomStudies(page = 1) {
  dicomPage = page;
  const search = document.getElementById('dicom-search')?.value.trim() || '';
  const modality = document.getElementById('dicom-modality')?.value || '';
  const studyStatus = document.getElementById('dicom-status')?.value || '';
  const limit = document.getElementById('dicom-limit')?.value || '20';

  const params = new URLSearchParams({ page: String(page), limit });
  if (search) params.set('search', search);
  if (modality) params.set('modality', modality);
  if (studyStatus) params.set('status', studyStatus);

  const res = await apiFetch(`/api/dicom/studies?${params.toString()}`);
  if (!res.ok) {
    console.error('Failed to load DICOM studies');
    return;
  }
  const data = await res.json();
  renderDicomGrid(data.items || []);
  updatePagination(data);
}

function renderDicomGrid(items) {
  const grid = document.getElementById('dicom-grid');
  if (!grid) return;

  if (!items.length) {
    grid.innerHTML = '<p class="text-muted" style="padding:2rem;text-align:center">Нет DICOM-исследований</p>';
    return;
  }

  grid.innerHTML = items.map(study => {
    const thumb = study.thumbnail_url
      ? `<img src="${study.thumbnail_url}" alt="" class="dicom-thumb" loading="lazy">`
      : '<div class="dicom-thumb dicom-thumb-placeholder">🩻</div>';
    const canView = study.status === 'ready';
    const viewBtn = canView
      ? `<a href="/dicom/viewer/${encodeURIComponent(study.study_uid)}" class="btn btn-primary btn-sm">Просмотр</a>`
      : '';
    const deleteBtn = study.can_delete
      ? `<button type="button" class="btn btn-danger btn-sm" data-delete-uid="${study.study_uid}" data-delete-label="${(study.study_description || study.modality || 'DICOM').replace(/"/g, '&quot;')}">Удалить</button>`
      : '';
    return `
      <article class="dicom-card">
        ${thumb}
        <div class="dicom-card-body">
          <div class="dicom-card-header">
            <strong>${study.modality || 'DICOM'}</strong>
            ${statusBadge(study.status)}
          </div>
          <p class="dicom-card-desc">${study.study_description || 'Без описания'}</p>
          <p class="text-muted dicom-card-meta">
            ${study.patient_name_dicom || ''} · ${formatStudyDate(study.study_date)}
            · ${study.body_part || '—'}
          </p>
          <p class="text-muted" style="font-size:0.8rem">
            Кадров: ${study.num_instances}
            ${study.total_files ? ` · Файлов в архиве: ${study.total_files}` : ''}
            · Пациент #${study.patient_id}
          </p>
          ${study.has_zip_archive && study.status === 'ready'
            ? `<button type="button" class="btn btn-secondary btn-sm" data-archive-uid="${study.study_uid}">Скачать ZIP</button>`
            : ''}
          <div class="dicom-card-actions">${viewBtn}${deleteBtn}</div>
        </div>
      </article>`;
  }).join('');

  grid.querySelectorAll('[data-archive-uid]').forEach(btn => {
    btn.addEventListener('click', () => downloadDicomArchive(btn.dataset.archiveUid));
  });
  grid.querySelectorAll('[data-delete-uid]').forEach(btn => {
    btn.addEventListener('click', () => deleteDicomStudy(btn.dataset.deleteUid, btn.dataset.deleteLabel));
  });
}

function updatePagination(data) {
  const prev = document.getElementById('prev-page');
  const next = document.getElementById('next-page');
  const info = document.getElementById('page-info');
  if (prev) prev.disabled = !data.prev_page;
  if (next) next.disabled = !data.next_page;
  if (info) info.textContent = `Страница ${data.page} из ${data.pages || 1} (${data.total} всего)`;
}

function setupDicomDropzone() {
  const zone = document.getElementById('dicom-dropzone');
  const input = document.getElementById('dicom-file');
  const nameEl = document.getElementById('dicom-file-name');
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

function setupDicomUploadForm(onSuccess) {
  const form = document.getElementById('dicom-upload-form');
  if (!form) return;

  setupDicomDropzone();

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const errEl = document.getElementById('dicom-upload-error');
    const progressEl = document.getElementById('dicom-upload-progress');
    errEl.classList.add('hidden');

    const fileInput = document.getElementById('dicom-file');
    const patientId = document.getElementById('dicom-patient')?.value;
    if (!patientId) {
      errEl.textContent = 'Выберите пациента';
      errEl.classList.remove('hidden');
      return;
    }
    if (!fileInput.files?.length) {
      errEl.textContent = 'Выберите DICOM-файл';
      errEl.classList.remove('hidden');
      return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('patient_id', patientId);

    progressEl.classList.remove('hidden');
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const res = await apiFetch('/api/dicom/upload', {
        method: 'POST',
        body: formData,
        headers: {},
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(formatApiError(data.detail) || `Ошибка загрузки (${res.status})`);

      document.getElementById('dicom-upload-modal').classList.add('hidden');
      form.reset();
      document.getElementById('dicom-file-name').textContent = '';
      progressEl.classList.add('hidden');
      loadDicomStudies(dicomPage);
      if (data.study_id && data.status === 'processing') {
        startDicomStatusPoll(data.study_id);
      }
      if (onSuccess) onSuccess(data);
    } catch (err) {
      progressEl.classList.add('hidden');
      errEl.textContent = err.message || 'Ошибка загрузки';
      errEl.classList.remove('hidden');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
}

function setupDicomControls() {
  let searchTimer;
  document.getElementById('dicom-search')?.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadDicomStudies(1), 350);
  });
  ['dicom-modality', 'dicom-status', 'dicom-limit'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => loadDicomStudies(1));
  });
}

function initDicomPage() {
  if (!requireAuth()) return;
  setupLogout();
  setupModals();
  setupDicomUploadForm(() => loadDicomStudies(dicomPage));
  setupDicomControls();
  initDicomZipUpload(() => loadDicomStudies(dicomPage));

  document.getElementById('upload-dicom-btn')?.addEventListener('click', async () => {
    await loadPatientsForSelect('dicom-patient');
    openModal('dicom-upload-modal');
  });
  document.getElementById('prev-page')?.addEventListener('click', () => loadDicomStudies(dicomPage - 1));
  document.getElementById('next-page')?.addEventListener('click', () => loadDicomStudies(dicomPage + 1));

  fetchCurrentUser()
    .then(() => {
      showAdminNav();
      return loadDicomStudies();
    })
    .then(() => resumeDicomProcessingPolls())
    .catch(err => console.error(err));

  window.addEventListener('pagehide', stopDicomStatusPoll);

  if (typeof MedInsightSocket !== 'undefined') {
    const socket = new MedInsightSocket({
      events: ['dicom.ready'],
      onEvent: () => loadDicomStudies(dicomPage),
    });
    socket.connect();
  }
}
