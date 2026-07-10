const API = '';

let currentUser = null;

function getToken() {
  return localStorage.getItem('token');
}

function getTenantId() {
  return localStorage.getItem('tenant_id');
}

function setSession(token, tenantId, role) {
  localStorage.setItem('token', token);
  if (tenantId != null) localStorage.setItem('tenant_id', String(tenantId));
  if (role) localStorage.setItem('role', role);
}

function clearSession() {
  localStorage.removeItem('token');
  localStorage.removeItem('tenant_id');
  localStorage.removeItem('role');
  currentUser = null;
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const tenantId = getTenantId();
  if (tenantId) headers['X-Tenant-ID'] = tenantId;
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearSession();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}

async function parseApiResponse(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(text.slice(0, 120) || `HTTP ${res.status}`);
  }
}

function setupLogout() {
  const btn = document.getElementById('logout-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      clearSession();
      window.location.href = '/login';
    });
  }
}

function setupNav() {
  const toggle = document.getElementById('nav-toggle');
  const navbar = document.querySelector('.navbar');
  if (!toggle || !navbar) return;

  const close = () => {
    navbar.classList.remove('nav-open');
    toggle.setAttribute('aria-expanded', 'false');
  };

  toggle.addEventListener('click', () => {
    const open = navbar.classList.toggle('nav-open');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  navbar.querySelectorAll('.nav-links a').forEach((a) => a.addEventListener('click', close));
}

document.addEventListener('DOMContentLoaded', setupNav);

function formatApiError(detail) {
  if (detail == null || detail === '') return '';
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
  }
  if (typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }
  return String(detail);
}

async function fetchCurrentUser() {
  const res = await apiFetch('/api/auth/me');
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка загрузки профиля');
  currentUser = data;
  if (data.tenant_id != null) {
    localStorage.setItem('tenant_id', String(data.tenant_id));
  }
  localStorage.setItem('role', data.role);
  if (data.demo_mode) {
    localStorage.setItem('demo_mode', 'true');
    if (window.MedInsightDemo) window.MedInsightDemo.apply();
  }
  renderUserSessionInfo(currentUser);
  applyWriteRestrictions();
  return currentUser;
}

const ROLE_LABELS = {
  super_admin: 'Суперадмин',
  admin: 'Администратор',
  head_of_department: 'Зав. отделением',
  doctor: 'Врач',
  nurse: 'Медсестра',
  researcher: 'Исследователь',
  viewer: 'Наблюдатель',
};

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderUserSessionInfo(user) {
  const el = document.getElementById('user-session-info');
  if (!el || !user) return;
  const roleLabel = ROLE_LABELS[user.role] || user.role;
  const parts = [
    `<strong>${escapeHtml(user.full_name)}</strong>`,
    escapeHtml(roleLabel),
  ];
  if (user.department_name) {
    parts.push(escapeHtml(user.department_name));
  }
  el.innerHTML = parts.join(' · ');
  el.classList.remove('hidden');
}

function isAdmin() {
  return currentUser?.role === 'admin' || currentUser?.role === 'super_admin';
}

function canDeleteDocument() {
  const role = currentUser?.role;
  return role === 'super_admin' || role === 'admin' || role === 'head_of_department';
}

function isViewer() {
  return currentUser?.role === 'viewer' || currentUser?.role === 'researcher';
}

function isReadOnly() {
  return isViewer();
}

function applyWriteRestrictions() {
  if (!isReadOnly()) return;
  document.querySelectorAll('[data-write-only]').forEach((el) => {
    el.classList.add('hidden');
    el.setAttribute('aria-hidden', 'true');
  });
  document.querySelectorAll('[data-write-action]').forEach((el) => {
    el.disabled = true;
    el.title = 'Недоступно для вашей роли';
  });
}

function showToast(message, type = 'info') {
  let host = document.getElementById('app-toasts');
  if (!host) {
    host = document.createElement('div');
    host.id = 'app-toasts';
    host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:360px';
    document.body.appendChild(host);
  }
  const colors = { info: '#1565c0', error: '#b91c1c', success: '#15803d' };
  const toast = document.createElement('div');
  toast.setAttribute('role', 'status');
  toast.style.cssText = `background:${colors[type] || colors.info};color:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:14px`;
  toast.textContent = message;
  host.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function connectWebSocket(onEvent) {
  if (typeof MedInsightSocket === 'undefined') return null;
  const socket = new MedInsightSocket({ onEvent: onEvent || (() => {}) });
  socket.connect();
  return socket;
}

let dashboardSocket = null;

function setupDashboardWebSocket() {
  if (dashboardSocket) return;
  dashboardSocket = connectWebSocket((payload) => {
    if (payload.event === 'prediction.ready' || payload.event === 'document.parsed') {
      loadDashboard({ cacheBust: true });
    }
    if (payload.event === 'limit.exceeded') {
      showToast('Месячный лимит анализов исчерпан', 'error');
    }
  });
}

function showAdminNav() {
  if (!isAdmin()) return;
  document.querySelectorAll('.nav-admin-link').forEach(el => {
    el.classList.remove('hidden');
  });
}

function renderPatientActions(patientId, patientName = '') {
  let html = `<button class="btn btn-secondary btn-sm export-btn" data-id="${patientId}">PDF</button>`;
  if (isAdmin()) {
    const safeName = patientName.replace(/"/g, '&quot;');
    html += ` <button class="btn btn-danger btn-sm delete-btn" data-id="${patientId}" data-name="${safeName}">Удалить</button>`;
  }
  return html;
}

function bindPatientActionButtons(onDelete) {
  document.querySelectorAll('.export-btn').forEach(btn => {
    btn.addEventListener('click', () => exportPatientPdf(btn.dataset.id));
  });
  document.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', () => deletePatient(btn.dataset.id, onDelete));
  });
}

async function deletePatient(patientId, onSuccess) {
  const btn = document.querySelector(`.delete-btn[data-id="${patientId}"]`);
  const name = btn?.dataset.name;
  const message = name
    ? `Удалить пациента «${name}»? Все документы пациента также будут удалены.`
    : 'Удалить пациента? Все документы пациента также будут удалены.';
  if (!confirm(message)) return;

  try {
    const res = await apiFetch(`/api/patients/${patientId}`, { method: 'DELETE' });
    if (!res.ok) {
      if (res.status === 404) {
        // Stale list after a prior successful delete — refresh without alarming the user.
        if (onSuccess) onSuccess(true);
        return;
      }
      const data = await parseApiResponse(res).catch(() => ({}));
      alert(formatApiError(data.detail) || 'Ошибка удаления');
      return;
    }
    if (onSuccess) onSuccess(true);
  } catch (err) {
    alert(err.message || 'Ошибка удаления');
  }
}

function setupModals() {
  document.querySelectorAll('.modal').forEach((modal) => {
    if (!modal.getAttribute('role')) modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
  });

  document.querySelectorAll('.modal-close, .modal-backdrop').forEach(el => {
    el.addEventListener('click', () => {
      const modal = el.closest('.modal');
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
      if (modal?.id === 'patient-modal') {
        resetPatientForm();
      }
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.modal:not(.hidden)').forEach((modal) => {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    });
  });
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  modal.querySelectorAll('.error-message').forEach(el => {
    el.textContent = '';
    el.classList.add('hidden');
  });
  const focusable = modal.querySelector('input, select, textarea, button');
  if (focusable) focusable.focus();
}

function resetPatientForm() {
  const form = document.getElementById('patient-form');
  if (!form) return;
  form.reset();

  const gender = document.getElementById('p-gender');
  if (gender) gender.value = 'M';

  const department = document.getElementById('p-department');
  if (department) department.value = '';

  const errEl = document.getElementById('patient-error');
  if (errEl) {
    errEl.textContent = '';
    errEl.classList.add('hidden');
  }
}

async function openNewPatientModal() {
  resetPatientForm();
  await loadDepartments('p-department');
  openModal('patient-modal');
}

async function loadDepartments(selectId, { includeAll = false } = {}) {
  const select = document.getElementById(selectId);
  if (!select) return [];
  try {
    const res = await apiFetch('/api/admin/departments');
    const data = await res.json();
    if (!res.ok) return [];
    const head = includeAll
      ? '<option value="">Все отделения</option>'
      : '<option value="">— Выберите отделение —</option>';
    select.innerHTML = head + data.map((d) => `<option value="${d.id}">${d.name}</option>`).join('');
    return data;
  } catch (e) {
    console.error('departments', e);
    return [];
  }
}

function setupPatientForm(onSuccess) {
  const form = document.getElementById('patient-form');
  if (!form || form.dataset.bound === '1') return;
  form.dataset.bound = '1';

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('patient-error');
    errEl.classList.add('hidden');

    const departmentId = document.getElementById('p-department').value;
    if (!departmentId) {
      errEl.textContent = 'Выберите отделение';
      errEl.classList.remove('hidden');
      return;
    }

    const payload = {
      first_name: document.getElementById('p-first-name').value,
      last_name: document.getElementById('p-last-name').value,
      birth_date: document.getElementById('p-birth-date').value,
      gender: document.getElementById('p-gender').value,
      phone: document.getElementById('p-phone').value,
      department_id: parseInt(departmentId, 10),
    };
    const middleName = document.getElementById('p-middle-name').value.trim();
    if (middleName) payload.middle_name = middleName;
    const email = document.getElementById('p-email').value;
    if (email) payload.email = email;

    try {
      const res = await apiFetch('/api/patients', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка создания пациента');

      document.getElementById('patient-modal').classList.add('hidden');
      resetPatientForm();
      if (onSuccess) onSuccess(data);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    }
  });
}

const GENDER_LABELS = { M: 'М', F: 'Ж', O: '—' };

const DOCUMENT_STATUS_LABELS = {
  uploaded: 'загружен',
  processing: 'обработка',
  parsed: 'обработан',
  failed: 'ошибка',
};

function documentStatusLabel(status) {
  return DOCUMENT_STATUS_LABELS[status] || status;
}

function formatParseError(parsedData) {
  const err = parsedData?.error;
  if (!err) return '';
  const text = String(err);
  return text.length > 120 ? `${text.slice(0, 117)}…` : text;
}

function renderDocumentItem(doc) {
  const safeName = escapeHtml(doc.filename);
  const safeAttrName = safeName.replace(/"/g, '&quot;');
  const parseError = doc.status === 'failed' ? formatParseError(doc.parsed_data) : '';
  const errorNote = parseError
    ? `<span class="document-error" title="${escapeHtml(doc.parsed_data?.error || '')}">${escapeHtml(parseError)}</span>`
    : '';
  const reparseBtn = doc.status === 'failed'
    ? `<button type="button" class="btn btn-secondary btn-sm doc-reparse-btn" data-id="${doc.id}">Повторить</button>`
    : '';
  const deleteBtn = canDeleteDocument()
    ? `<button type="button" class="btn btn-danger btn-sm doc-delete-btn" data-id="${doc.id}" data-filename="${safeAttrName}">Удалить</button>`
    : '';
  return `
    <li class="document-item">
      <div class="document-item-main">
        <strong>${safeName}</strong>
        <span class="document-meta">${documentStatusLabel(doc.status)} · ${escapeHtml(doc.document_type || 'документ')} · ${new Date(doc.created_at).toLocaleDateString('ru-RU')}</span>
        ${errorNote}
      </div>
      <div class="document-item-actions">
        <button type="button" class="btn btn-secondary btn-sm doc-open-btn" data-id="${doc.id}" data-filename="${safeAttrName}">Открыть</button>
        <button type="button" class="btn btn-secondary btn-sm doc-download-btn" data-id="${doc.id}" data-filename="${safeAttrName}">Скачать</button>
        ${reparseBtn}
        ${deleteBtn}
      </div>
    </li>
  `;
}

const MIME_BY_EXT = {
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

function documentExtension(filename) {
  const parts = (filename || '').split('.');
  return parts.length > 1 ? parts.pop().toLowerCase() : '';
}

function canPreviewDocumentInline(filename, mimeType) {
  const ext = documentExtension(filename);
  if (ext === 'pdf') return true;
  return mimeType === 'application/pdf';
}

function blobWithFilenameType(blob, filename) {
  const ext = documentExtension(filename);
  const mime = MIME_BY_EXT[ext];
  if (!mime || (blob.type && blob.type !== 'application/octet-stream')) {
    return blob;
  }
  return new Blob([blob], { type: mime });
}

async function fetchDocumentBlob(documentId, inline = false) {
  const query = inline ? '?inline=1' : '';
  const res = await apiFetch(`/api/documents/${documentId}/download${query}`);
  if (!res.ok) {
    const data = await parseApiResponse(res);
    throw new Error(formatApiError(data.detail) || 'Не удалось получить файл');
  }
  return res.blob();
}

async function downloadPatientDocument(documentId, filename) {
  const blob = await fetchDocumentBlob(documentId, false);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || `document_${documentId}`;
  a.click();
  URL.revokeObjectURL(url);
}

async function openPatientDocument(documentId, filename) {
  const blob = await fetchDocumentBlob(documentId, true);
  const typedBlob = blobWithFilenameType(blob, filename);
  const url = URL.createObjectURL(typedBlob);
  const a = document.createElement('a');
  a.href = url;
  a.rel = 'noopener noreferrer';
  if (canPreviewDocumentInline(filename, typedBlob.type)) {
    a.target = '_blank';
  } else {
    a.download = filename || `document_${documentId}`;
  }
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

async function deletePatientDocument(documentId, filename) {
  const message = filename
    ? `Удалить документ «${filename}»?`
    : 'Удалить документ?';
  if (!confirm(message)) return;

  const res = await apiFetch(`/api/documents/${documentId}`, { method: 'DELETE' });
  if (!res.ok) {
    const data = await parseApiResponse(res).catch(() => ({}));
    throw new Error(formatApiError(data.detail) || 'Ошибка удаления');
  }

  const docsEl = document.getElementById('documents-list');
  const patientId = docsEl?.dataset.patientId;
  if (patientId) {
    await loadPatientDetail(parseInt(patientId, 10));
  }
}

function setupDocumentActions() {
  const docsEl = document.getElementById('documents-list');
  if (!docsEl || docsEl.dataset.bound === '1') return;
  docsEl.dataset.bound = '1';

  docsEl.addEventListener('click', async (event) => {
    const openBtn = event.target.closest('.doc-open-btn');
    const downloadBtn = event.target.closest('.doc-download-btn');
    const reparseBtn = event.target.closest('.doc-reparse-btn');
    const deleteBtn = event.target.closest('.doc-delete-btn');
    const button = openBtn || downloadBtn || reparseBtn || deleteBtn;
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();

    const documentId = button.dataset.id;
    const filename = button.dataset.filename;
    button.disabled = true;

    try {
      if (deleteBtn) {
        await deletePatientDocument(documentId, filename);
      } else if (reparseBtn) {
        await reparsePatientDocument(documentId);
      } else if (openBtn) {
        await openPatientDocument(documentId, filename);
      } else {
        await downloadPatientDocument(documentId, filename);
      }
    } catch (err) {
      alert(err.message || 'Ошибка работы с документом');
    } finally {
      button.disabled = false;
    }
  });
}

async function reparsePatientDocument(documentId) {
  const res = await apiFetch(`/api/documents/${documentId}/reparse`, { method: 'POST' });
  const data = await parseApiResponse(res);
  if (!res.ok) throw new Error(formatApiError(data.detail) || 'Не удалось повторить обработку');

  const patientId = document.getElementById('documents-list')?.dataset.patientId;
  if (patientId) {
    await loadPatientDetail(parseInt(patientId, 10));
  }
}

const DICOM_STATUS_LABELS = {
  ready: 'готово',
  processing: 'обработка',
  failed: 'ошибка',
  uploaded: 'загружено',
};

function formatDicomStudyDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('ru-RU');
}

function renderPatientDicomItem(study) {
  const title = escapeHtml(study.study_description || study.modality || 'DICOM');
  const modality = escapeHtml(study.modality || '—');
  const status = DICOM_STATUS_LABELS[study.status] || study.status;
  const canView = study.status === 'ready';
  const viewBtn = canView
    ? `<a href="/dicom/viewer/${encodeURIComponent(study.study_uid)}" class="btn btn-primary btn-sm">Просмотр</a>`
    : '';
  const deleteBtn = study.can_delete
    ? `<button type="button" class="btn btn-danger btn-sm patient-dicom-delete-btn" data-id="${study.id}" data-label="${title.replace(/"/g, '&quot;')}">Удалить</button>`
    : '';
  return `
    <li class="document-item">
      <div class="document-item-main">
        <strong>${title}</strong>
        <span class="document-meta">${status} · ${modality} · ${formatDicomStudyDate(study.study_date)} · кадров: ${study.num_instances}</span>
      </div>
      <div class="document-item-actions">
        ${viewBtn}
        ${deleteBtn}
      </div>
    </li>
  `;
}

async function loadPatientDicomStudies(patientId) {
  const listEl = document.getElementById('dicom-studies-list');
  const section = document.getElementById('dicom-section');
  if (!listEl || !section) return;

  const res = await apiFetch(`/api/dicom/studies?patient_id=${patientId}&limit=20`);
  if (res.status === 503) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  const data = await parseApiResponse(res);
  if (!res.ok) {
    listEl.innerHTML = '<li style="color:#64748b">Не удалось загрузить DICOM-исследования</li>';
    return;
  }

  const items = data.items || [];
  listEl.dataset.patientId = String(patientId);
  listEl.innerHTML = items.length
    ? items.map(renderPatientDicomItem).join('')
    : '<li style="color:#64748b">DICOM-исследования не загружены</li>';
}

function setupPatientDicomSection(patientId) {
  const section = document.getElementById('dicom-section');
  if (!section) return;

  const patientField = document.getElementById('dicom-patient');
  if (patientField) patientField.value = String(patientId);

  const allLink = document.getElementById('patient-dicom-all-link');
  if (allLink) allLink.href = `/dicom?patient_id=${patientId}`;

  if (typeof setDicomRefreshCallback === 'function') {
    setDicomRefreshCallback(() => loadPatientDicomStudies(patientId));
  }

  if (section.dataset.bound !== '1') {
    section.dataset.bound = '1';
    setupModals();
    if (typeof setupDicomDropzone === 'function') setupDicomDropzone();
    if (typeof setupDicomUploadForm === 'function') setupDicomUploadForm();

    document.getElementById('patient-upload-dicom-btn')?.addEventListener('click', () => {
      openModal('dicom-upload-modal');
    });

    document.getElementById('dicom-studies-list')?.addEventListener('click', async (event) => {
      const deleteBtn = event.target.closest('.patient-dicom-delete-btn');
      if (!deleteBtn || typeof deleteDicomStudy !== 'function') return;
      event.preventDefault();
      await deleteDicomStudy(Number(deleteBtn.dataset.id), deleteBtn.dataset.label);
    });
  }

  if (typeof resumeDicomProcessingPolls === 'function') {
    resumeDicomProcessingPolls();
  }
}

function formatFullName(p) {
  const parts = [p.last_name, p.first_name];
  if (p.middle_name) parts.push(p.middle_name);
  return parts.join(' ');
}

let diagnosesChart = null;
let medicationsChart = null;
let deptRiskChart = null;
let trendsChart = null;
let lastBarChartData = { diagnoses: null, medications: null };
let lastDeptRiskData = null;
let lastTrendsData = null;

function chartColors() {
  if (window.ThemeManager) return window.ThemeManager.chartColors();
  return {
    text: '#64748b',
    grid: '#e2e8f0',
    bar: 'rgba(37, 99, 235, 0.7)',
    barBorder: 'rgba(37, 99, 235, 1)',
    danger: 'rgba(220, 38, 38, 0.7)',
    dangerLine: 'rgba(220, 38, 38, 1)',
    primaryLine: 'rgba(37, 99, 235, 1)',
  };
}

function chartScaleOptions(extra = {}) {
  const c = chartColors();
  let scales;
  if (window.ThemeManager) {
    scales = { ...window.ThemeManager.chartScaleOptions() };
  } else {
    scales = {
      x: { ticks: { color: c.text, maxRotation: 45 }, grid: { color: c.grid } },
      y: { beginAtZero: true, ticks: { color: c.text }, grid: { color: c.grid } },
    };
  }
  if (extra.yMax !== undefined) {
    scales.y = { ...scales.y, max: extra.yMax };
  }
  if (extra.yStep !== undefined) {
    scales.y = {
      ...scales.y,
      ticks: { ...(scales.y?.ticks || {}), stepSize: extra.yStep },
    };
  }
  return scales;
}

function refreshChartsForTheme() {
  if (lastBarChartData.diagnoses) {
    renderBarChart('diagnoses-chart', lastBarChartData.diagnoses, diagnosesChart, (c) => { diagnosesChart = c; });
  }
  if (lastBarChartData.medications) {
    renderBarChart('medications-chart', lastBarChartData.medications, medicationsChart, (c) => { medicationsChart = c; });
  }
  if (lastDeptRiskData) renderDeptRiskChart(lastDeptRiskData);
  if (lastTrendsData) renderTrendsChart(lastTrendsData);
}

window.addEventListener('themechange', refreshChartsForTheme);

function riskLevel(value) {
  if (value < 40) return 'low';
  if (value < 70) return 'medium';
  return 'high';
}

function riskBadge(value) {
  const level = riskLevel(value);
  const labels = { low: 'Низкий', medium: 'Средний', high: 'Высокий' };
  return `<span class="risk-badge risk-badge-${level}">${labels[level]} (${value}%)</span>`;
}

function riskClass(value) {
  return `risk-${riskLevel(value)}`;
}

function currentDeptFilter() {
  const el = document.getElementById('dept-filter');
  return el && el.value ? `?department_id=${el.value}` : '';
}

function dashboardUrl(cacheBust = false) {
  const params = new URLSearchParams();
  const dept = document.getElementById('dept-filter');
  if (dept && dept.value) params.set('department_id', dept.value);
  if (cacheBust) params.set('_', String(Date.now()));
  const qs = params.toString();
  return `/api/analytics/dashboard${qs ? `?${qs}` : ''}`;
}

async function loadDashboard({ cacheBust = false } = {}) {
  const res = await apiFetch(dashboardUrl(cacheBust));
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки дашборда');

  document.getElementById('stat-patients').textContent = data.total_patients;
  document.getElementById('stat-documents').textContent = data.total_documents;
  document.getElementById('stat-diagnoses').textContent = Object.keys(data.diagnoses).length;

  renderBarChart('diagnoses-chart', data.diagnoses, diagnosesChart, (c) => { diagnosesChart = c; });
  renderBarChart('medications-chart', data.medications, medicationsChart, (c) => { medicationsChart = c; });
  lastBarChartData.diagnoses = data.diagnoses;
  lastBarChartData.medications = data.medications;

  const tbody = document.querySelector('#recent-patients-table tbody');
  tbody.innerHTML = '';
  data.recent_patients.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${formatFullName(p)}</td>
      <td>${p.birth_date}</td>
      <td>${GENDER_LABELS[p.gender] || p.gender}</td>
      <td>${new Date(p.created_at).toLocaleDateString('ru-RU')}</td>
      <td>
        <a href="/patient/${p.id}" class="btn btn-secondary btn-sm">Карточка</a>
        ${renderPatientActions(p.id, formatFullName(p))}
      </td>
    `;
    tbody.appendChild(tr);
  });

  bindPatientActionButtons(() => loadDashboard());
  loadPredictionsDashboard();
  loadWebhooks();
}

// --- Phase 4: Webhooks ---

async function loadWebhooks() {
  const tbody = document.querySelector('#webhooks-table tbody');
  if (!tbody) return;
  try {
    const res = await apiFetch('/api/webhooks');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка вебхуков');
    tbody.innerHTML = data.length
      ? ''
      : '<tr><td colspan="5" class="text-center-muted">Вебхуки не настроены</td></tr>';
    data.forEach((w) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis">${w.url}</td>
        <td>${(w.events || []).join(', ')}</td>
        <td>${w.is_active ? 'активен' : 'отключён'}</td>
        <td>${w.failure_count}</td>
        <td>
          <button class="btn btn-secondary btn-sm wh-test" data-id="${w.id}">Тест</button>
          <button class="btn btn-danger btn-sm wh-del" data-id="${w.id}">Удалить</button>
        </td>`;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll('.wh-test').forEach((b) => b.addEventListener('click', () => testWebhook(b.dataset.id)));
    tbody.querySelectorAll('.wh-del').forEach((b) => b.addEventListener('click', () => deleteWebhook(b.dataset.id)));
  } catch (err) {
    console.error('Webhooks error:', err);
  }
}

function setupWebhookForm() {
  const addBtn = document.getElementById('add-webhook-btn');
  const form = document.getElementById('webhook-form');
  if (!addBtn || !form) return;
  addBtn.addEventListener('click', () => form.classList.toggle('hidden'));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = document.getElementById('webhook-url').value;
    const secret = document.getElementById('webhook-secret').value;
    try {
      const res = await apiFetch('/api/webhooks/register', {
        method: 'POST',
        body: JSON.stringify({ url, secret: secret || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка регистрации');
      form.reset();
      form.classList.add('hidden');
      loadWebhooks();
    } catch (err) {
      alert(err.message);
    }
  });
}

async function testWebhook(id) {
  const res = await apiFetch(`/api/webhooks/${id}/test`, { method: 'POST' });
  const data = await res.json();
  alert(data.delivered ? 'Вебхук доставлен ✓' : 'Доставка не удалась (проверьте URL)');
  loadWebhooks();
}

async function deleteWebhook(id) {
  if (!confirm('Удалить вебхук?')) return;
  await apiFetch(`/api/webhooks/${id}`, { method: 'DELETE' });
  loadWebhooks();
}

async function loadPredictionsDashboard() {
  const statEl = document.getElementById('stat-high-risk');
  if (!statEl) return;

  try {
    const res = await apiFetch(`/api/analytics/dashboard/predictions${currentDeptFilter()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки прогнозов');

    statEl.textContent = data.high_risk_patients.length;

    const tbody = document.querySelector('#high-risk-table tbody');
    if (tbody) {
      tbody.innerHTML = '';
      if (data.high_risk_patients.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center-muted">Нет данных — сгенерируйте прогнозы для пациентов</td></tr>';
      }
      data.high_risk_patients.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${p.name}</td>
          <td>${riskBadge(Math.round(p.readmission_risk))}</td>
          <td>${riskBadge(Math.round(p.complication_risk))}</td>
          <td>${new Date(p.last_prediction_at).toLocaleDateString('ru-RU')}</td>
          <td><a href="/patient/${p.id}" class="btn btn-secondary btn-sm">Открыть</a></td>
        `;
        tbody.appendChild(tr);
      });
    }

    renderDeptRiskChart(data.risk_by_department);
    renderTrendsChart(data.monthly_trends);
    lastDeptRiskData = data.risk_by_department;
    lastTrendsData = data.monthly_trends;
  } catch (err) {
    console.error('Predictions dashboard error:', err);
  }
}

function renderDeptRiskChart(deptData) {
  const canvas = document.getElementById('dept-risk-chart');
  if (!canvas) return;

  const c = chartColors();
  const entries = Object.entries(deptData);
  const labels = entries.map(([dept]) => dept);
  const readmission = entries.map(([, v]) => v.readmission_avg);
  const complication = entries.map(([, v]) => v.complication_avg);

  if (deptRiskChart) deptRiskChart.destroy();

  deptRiskChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: labels.length ? labels : ['Нет данных'],
      datasets: [
        {
          label: 'Реадмиссия',
          data: readmission.length ? readmission : [0],
          backgroundColor: c.danger,
        },
        {
          label: 'Осложнения',
          data: complication.length ? complication : [0],
          backgroundColor: c.bar,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: c.text } } },
      scales: chartScaleOptions({ yMax: 100 }),
    },
  });
}

function renderTrendsChart(trends) {
  const canvas = document.getElementById('trends-chart');
  if (!canvas) return;

  const c = chartColors();
  const labels = trends.labels || [];
  if (trendsChart) trendsChart.destroy();

  trendsChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: labels.length ? labels : ['—'],
      datasets: [
        {
          label: 'Реадмиссия',
          data: trends.readmission || [],
          borderColor: c.dangerLine,
          tension: 0.3,
        },
        {
          label: 'Осложнения',
          data: trends.complication || [],
          borderColor: c.primaryLine,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: c.text } } },
      scales: chartScaleOptions({ yMax: 100 }),
    },
  });
}

function renderBarChart(canvasId, dataObj, existingChart, setChart) {
  const c = chartColors();
  const entries = Object.entries(dataObj).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const labels = entries.map(e => e[0]);
  const values = entries.map(e => e[1]);

  if (existingChart) existingChart.destroy();

  const ctx = document.getElementById(canvasId).getContext('2d');
  const chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: c.bar,
        borderColor: c.barBorder,
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: chartScaleOptions({ yStep: 1 }),
    },
  });
  setChart(chart);
}

async function loadPatientsForSelect(selectId) {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.innerHTML = '<option value="">— Загрузка… —</option>';
  try {
    const res = await apiFetch('/api/patients?page=1&page_size=100');
    const data = await parseApiResponse(res);
    if (!res.ok) {
      const msg = formatApiError(data.detail) || `Ошибка загрузки пациентов (${res.status})`;
      select.innerHTML = `<option value="">${msg}</option>`;
      return;
    }
    const items = data.items || [];
    if (!items.length) {
      select.innerHTML = '<option value="">— Нет доступных пациентов —</option>';
      return;
    }
    select.innerHTML = '<option value="">— Выберите пациента —</option>';
    items.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = formatFullName(p);
      select.appendChild(opt);
    });
  } catch (err) {
    select.innerHTML = `<option value="">— ${err.message || 'Ошибка загрузки пациентов'} —</option>`;
  }
}

function setupUploadForm(onSuccess) {
  const form = document.getElementById('upload-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('upload-error');
    const progressEl = document.getElementById('upload-progress');
    errEl.classList.add('hidden');

    const fileInput = document.getElementById('upload-file');
    const patientId = document.getElementById('upload-patient').value;
    if (!patientId) {
      errEl.textContent = 'Выберите пациента';
      errEl.classList.remove('hidden');
      return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('patient_id', patientId);
    formData.append('document_type', document.getElementById('upload-type').value);

    progressEl.classList.remove('hidden');
    errEl.classList.add('hidden');

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const res = await apiFetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
        headers: {},
      });
      const data = await res.json();
      if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка загрузки');

      document.getElementById('upload-modal').classList.add('hidden');
      form.reset();
      progressEl.classList.add('hidden');
      if (onSuccess) onSuccess(data);
    } catch (err) {
      progressEl.classList.add('hidden');
      errEl.textContent = err.message || 'Ошибка загрузки';
      errEl.classList.remove('hidden');
      console.error('Upload failed:', err);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
}

async function exportPatientPdf(patientId) {
  const res = await apiFetch(`/api/export/patient/${patientId}`, { method: 'POST' });
  if (!res.ok) {
    const data = await res.json();
    alert(data.detail || 'Ошибка экспорта');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `patient_${patientId}_report.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

const PATIENT_CARD_DOCX_SECTIONS = [
  'patient',
  'anamnesis',
  'diagnoses',
  'lab',
  'medications',
  'predictions',
  'dicom',
  'conclusion',
];

function filenameFromContentDisposition(header, fallback) {
  if (!header) return fallback;
  const match = header.match(/filename\*?=(?:UTF-8''|")?([^";\n]+)"?/i);
  return match ? decodeURIComponent(match[1].trim()) : fallback;
}

async function pollDocxExportDownload(downloadUrl, patientId) {
  const maxAttempts = 30;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const res = await apiFetch(downloadUrl);
    if (res.status === 202) continue;
    if (!res.ok) {
      const data = await parseApiResponse(res);
      throw new Error(formatApiError(data.detail) || 'Ошибка загрузки DOCX');
    }
    const blob = await res.blob();
    const filename = filenameFromContentDisposition(
      res.headers.get('content-disposition'),
      `patient_${patientId}_card.docx`,
    );
    downloadBlob(blob, filename);
    return;
  }
  throw new Error('Генерация DOCX заняла слишком много времени');
}

async function exportPatientDocx(patientId, btn = null) {
  const originalLabel = btn?.textContent;
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Формирование…';
  }

  try {
    const res = await apiFetch('/api/export/patient-card', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id: patientId,
        format: 'docx',
        sections: PATIENT_CARD_DOCX_SECTIONS,
        fill_demo: true,
        force_regenerate: true,
      }),
    });

    const contentType = res.headers.get('content-type') || '';
    if (!res.ok) {
      const data = await parseApiResponse(res);
      throw new Error(formatApiError(data.detail) || 'Ошибка экспорта DOCX');
    }

    if (contentType.includes('application/json')) {
      const data = await res.json();
      if (data.status === 'processing' && data.download_url) {
        await pollDocxExportDownload(data.download_url, patientId);
        return;
      }
      throw new Error(data.message || 'Неожиданный ответ сервера');
    }

    const blob = await res.blob();
    const filename = filenameFromContentDisposition(
      res.headers.get('content-disposition'),
      `patient_${patientId}_card.docx`,
    );
    downloadBlob(blob, filename);
  } catch (err) {
    alert(err.message || 'Ошибка экспорта DOCX');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalLabel || '⬇ Экспорт DOCX';
    }
  }
}

function initDashboard() {
  if (!requireAuth()) return;
  setupLogout();
  setupModals();
  setupPatientForm(() => loadDashboard());
  setupUploadForm(() => loadDashboard({ cacheBust: true }));
  setupWebhookForm();

  document.getElementById('new-patient-btn').addEventListener('click', () => {
    openNewPatientModal();
  });
  document.getElementById('upload-doc-btn').addEventListener('click', async () => {
    await loadPatientsForSelect('upload-patient');
    openModal('upload-modal');
  });

  const deptFilter = document.getElementById('dept-filter');
  if (deptFilter) deptFilter.addEventListener('change', () => loadDashboard());

  fetchCurrentUser()
    .then(async () => {
      showAdminNav();
      applyWriteRestrictions();
      setupDashboardWebSocket();
      await loadDepartments('dept-filter', { includeAll: true });
      return loadDashboard();
    })
    .catch(err => {
      console.error(err);
      showToast(err.message || 'Ошибка загрузки дашборда', 'error');
    });
}

let patientsPage = 1;
let patientsPageSize = 20;
let patientsSearch = '';

async function loadPatientsList(page = 1, { cacheBust = false } = {}) {
  const params = new URLSearchParams({ page, limit: patientsPageSize });
  if (patientsSearch) params.set('search', patientsSearch);
  if (cacheBust) params.set('_', String(Date.now()));
  const res = await apiFetch(`/api/patients?${params.toString()}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки');

  patientsPage = data.page || page;
  const tbody = document.querySelector('#patients-table tbody');
  tbody.innerHTML = '';

  if (!data.items.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#64748b">Ничего не найдено</td></tr>';
  }

  data.items.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${p.id}</td>
      <td>${formatFullName(p)}</td>
      <td>${p.birth_date}</td>
      <td>${GENDER_LABELS[p.gender] || p.gender}</td>
      <td>${p.phone}</td>
      <td>${p.email || '—'}</td>
      <td>
        <a href="/patient/${p.id}" class="btn btn-secondary btn-sm">Карточка</a>
        ${renderPatientActions(p.id, formatFullName(p))}
      </td>
    `;
    tbody.appendChild(tr);
  });

  bindPatientActionButtons(() => loadPatientsList(patientsPage, { cacheBust: true }));

  const totalPages = data.pages || 1;
  document.getElementById('page-info').textContent = `Страница ${patientsPage} из ${totalPages} (всего ${data.total})`;
  document.getElementById('prev-page').disabled = !data.prev_page;
  document.getElementById('next-page').disabled = !data.next_page;
}

// --- Phase 7: search/limit controls + Excel export ---

function debounce(fn, wait = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function setupPatientsControls() {
  const searchEl = document.getElementById('patient-search');
  if (searchEl) {
    searchEl.addEventListener('input', debounce((e) => {
      patientsSearch = e.target.value.trim();
      loadPatientsList(1);
    }, 300));
  }
  const limitEl = document.getElementById('patient-limit');
  if (limitEl) {
    limitEl.addEventListener('change', (e) => {
      patientsPageSize = parseInt(e.target.value, 10) || 20;
      loadPatientsList(1);
    });
  }
  const exportBtn = document.getElementById('export-patients-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      const filters = patientsSearch ? { search: patientsSearch } : {};
      exportToExcel('patients', filters, [], exportBtn);
    });
  }
}

async function exportToExcel(entity, filters = {}, columns = [], btn = null) {
  const originalText = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Экспорт…'; }
  try {
    const res = await apiFetch(`/api/export/${entity}`, {
      method: 'POST',
      body: JSON.stringify({ filters, columns }),
    });
    const contentType = res.headers.get('content-type') || '';

    if (contentType.includes('application/json')) {
      // Large dataset -> async job; poll the download URL until ready.
      const job = await res.json();
      if (!res.ok) throw new Error(job.detail || 'Ошибка экспорта');
      if (btn) btn.textContent = 'Готовим файл…';
      await pollExportDownload(job.download_url, entity);
    } else {
      const blob = await res.blob();
      downloadBlob(blob, `${entity}_export_${new Date().toISOString().slice(0, 10)}.xlsx`);
    }
  } catch (err) {
    alert(err.message || 'Ошибка экспорта');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = originalText; }
  }
}

async function pollExportDownload(downloadUrl, entity) {
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const res = await apiFetch(downloadUrl);
    if (res.ok) {
      const blob = await res.blob();
      downloadBlob(blob, `${entity}_export_${new Date().toISOString().slice(0, 10)}.xlsx`);
      return;
    }
  }
  alert('Экспорт занимает слишком много времени. Попробуйте позже по ссылке скачивания.');
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function pollJobStatus(jobId, onComplete, onError) {
  const maxAttempts = 60;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const res = await apiFetch(`/api/analytics/predict/status/${jobId}`);
    const data = await parseApiResponse(res);
    if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка статуса задачи');

    if (data.status === 'completed') {
      onComplete(data.result);
      return;
    }
    if (data.status === 'failed') {
      onError(data.error || 'Задача завершилась с ошибкой');
      return;
    }
  }
  onError('Превышено время ожидания');
}

async function pollDocumentStatus(docId, onComplete, onError) {
  const maxAttempts = 60;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const res = await apiFetch(`/api/documents/${docId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка статуса документа');

    if (data.status === 'parsed') {
      onComplete(data);
      return;
    }
    if (data.status === 'failed') {
      onError(data.parsed_data?.error || 'Парсинг завершился с ошибкой');
      return;
    }
  }
  onError('Превышено время ожидания парсинга');
}

async function startPrediction(patientId) {
  const loadingEl = document.getElementById('prediction-loading');
  const resultEl = document.getElementById('prediction-result');
  if (loadingEl) loadingEl.classList.remove('hidden');
  if (resultEl) resultEl.innerHTML = '';

  try {
    const res = await apiFetch(`/api/analytics/predict/${patientId}`, { method: 'POST' });
    const data = await parseApiResponse(res);
    if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка запуска прогноза');

    await pollJobStatus(
      data.job_id,
      () => loadPatientPredictions(patientId),
      (err) => { if (resultEl) resultEl.innerHTML = `<div class="error-message">${err}</div>`; }
    );
  } catch (err) {
    if (resultEl) resultEl.innerHTML = `<div class="error-message">${err.message}</div>`;
  } finally {
    if (loadingEl) loadingEl.classList.add('hidden');
  }
}

async function loadPatientInsights(patientId) {
  const el = document.getElementById('insights-result');
  if (el) {
    el.classList.remove('hidden');
    el.innerHTML = '<div class="loading-indicator">Генерация инсайтов...</div>';
  }

  try {
    const res = await apiFetch(`/api/analytics/insights/${patientId}`, { method: 'POST' });
    const data = await parseApiResponse(res);
    if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка генерации инсайтов');

    if (el) {
      el.innerHTML = `
        <div class="recommendations-list">
          <h3>Клиническая заметка</h3>
          <p>${escapeHtml(data.insights)}</p>
          <h3>Рекомендации</h3>
          <ul>${(data.recommendations || []).map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>
        </div>
      `;
    }
  } catch (err) {
    if (el) el.innerHTML = `<div class="error-message">${escapeHtml(err.message)}</div>`;
  }
}

async function loadPatientPredictions(patientId) {
  const resultEl = document.getElementById('prediction-result');
  if (!resultEl) return;

  const res = await apiFetch(`/api/analytics/predictions/${patientId}`);
  const data = await parseApiResponse(res);
  if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка загрузки прогнозов');

  if (!data.predictions.length) {
    resultEl.innerHTML = '<p style="color:#64748b">Прогнозы ещё не сгенерированы. Нажмите «Сгенерировать прогноз».</p>';
    return;
  }

  const latest = data.predictions[0];
  const pred = latest.prediction || {};
  const readmission = Math.round(pred.readmission_risk || 0);
  const complication = Math.round(pred.complication_risk || 0);

  resultEl.innerHTML = `
    <div class="risk-grid">
      <div class="risk-card ${riskClass(readmission)}">
        <div class="risk-label">Риск реадмиссии</div>
        <div class="risk-value">${readmission}%</div>
        ${riskBadge(readmission)}
      </div>
      <div class="risk-card ${riskClass(complication)}">
        <div class="risk-label">Риск осложнений</div>
        <div class="risk-value">${complication}%</div>
        ${riskBadge(complication)}
      </div>
    </div>
    ${pred.factors?.length ? `
      <div class="recommendations-list">
        <h3>Факторы риска</h3>
        <ul>${pred.factors.map(f => `<li>${escapeHtml(f)}</li>`).join('')}</ul>
      </div>
    ` : ''}
    ${pred.recommendations?.length ? `
      <div class="recommendations-list">
        <h3>Рекомендации</h3>
        <ul>${pred.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>
      </div>
    ` : ''}
    <p style="font-size:0.8rem;color:#64748b;margin-top:0.75rem">
      Уверенность: ${Math.round(latest.confidence_score * 100)}% ·
      ${new Date(latest.created_at).toLocaleString('ru-RU')}
      ${latest.validated ? ' · ✓ Подтверждено врачом' : ''}
    </p>
  `;
}

async function loadPatientDetail(patientId) {
  const res = await apiFetch(`/api/patients/${patientId}`);
  const patient = await res.json();
  if (!res.ok) throw new Error(patient.detail || 'Пациент не найден');

  document.getElementById('patient-name').textContent = formatFullName(patient);
  document.getElementById('patient-info').innerHTML = `
    <p><strong>Дата рождения:</strong> ${patient.birth_date}</p>
    <p><strong>Пол:</strong> ${GENDER_LABELS[patient.gender] || patient.gender}</p>
    <p><strong>Телефон:</strong> ${patient.phone}</p>
    <p><strong>Email:</strong> ${patient.email || '—'}</p>
  `;

  const docsRes = await apiFetch(`/api/documents/patient/${patientId}`);
  const docs = await docsRes.json();
  const docsEl = document.getElementById('documents-list');
  if (docsEl) {
    docsEl.dataset.patientId = String(patientId);
    docsEl.innerHTML = docs.length
      ? docs.map(renderDocumentItem).join('')
      : '<li style="color:#64748b">Документы не загружены</li>';
  }

  await loadPatientPredictions(patientId);
  await loadPatientDicomStudies(patientId);
}

function initPatientPage() {
  if (!requireAuth()) return;
  setupLogout();
  setupDocumentActions();

  const match = window.location.pathname.match(/\/patient\/(\d+)/);
  const patientId = match ? parseInt(match[1], 10) : null;
  if (!patientId) {
    window.location.href = '/patients';
    return;
  }

  document.getElementById('generate-prediction-btn')?.addEventListener('click', () => startPrediction(patientId));
  document.getElementById('generate-insights-btn')?.addEventListener('click', () => loadPatientInsights(patientId));
  document.getElementById('export-patient-docx-btn')?.addEventListener('click', (event) => {
    exportPatientDocx(patientId, event.currentTarget);
  });
  setupPatientDicomSection(patientId);

  fetchCurrentUser()
    .then(() => { applyWriteRestrictions(); return loadPatientDetail(patientId); })
    .catch(err => {
      console.error(err);
      showToast(err.message || 'Ошибка загрузки карточки пациента', 'error');
    });
}

function initPatientsPage() {
  if (!requireAuth()) return;
  setupLogout();
  setupModals();
  setupPatientForm(() => loadPatientsList(patientsPage));

  document.getElementById('new-patient-btn').addEventListener('click', () => {
    openNewPatientModal();
  });
  document.getElementById('prev-page').addEventListener('click', () => loadPatientsList(patientsPage - 1));
  document.getElementById('next-page').addEventListener('click', () => loadPatientsList(patientsPage + 1));
  setupPatientsControls();

  fetchCurrentUser()
    .then(() => { showAdminNav(); applyWriteRestrictions(); return loadPatientsList(); })
    .catch(err => {
      console.error(err);
      showToast(err.message || 'Ошибка загрузки пациентов', 'error');
    });
}
