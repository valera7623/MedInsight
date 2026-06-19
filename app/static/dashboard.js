const API = '';

let currentUser = null;

function getToken() {
  return localStorage.getItem('token');
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
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}

function setupLogout() {
  const btn = document.getElementById('logout-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      localStorage.removeItem('token');
      currentUser = null;
      window.location.href = '/login';
    });
  }
}

async function fetchCurrentUser() {
  const res = await apiFetch('/api/auth/me');
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки профиля');
  currentUser = data;
  return currentUser;
}

function isAdmin() {
  return currentUser?.role === 'admin';
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
      const data = await res.json().catch(() => ({}));
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg || d).join(', ')
        : data.detail;
      alert(detail || 'Ошибка удаления');
      return;
    }
    if (onSuccess) onSuccess();
  } catch (err) {
    alert(err.message || 'Ошибка удаления');
  }
}

function setupModals() {
  document.querySelectorAll('.modal-close, .modal-backdrop').forEach(el => {
    el.addEventListener('click', () => {
      el.closest('.modal').classList.add('hidden');
    });
  });
}

function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
}

function setupPatientForm(onSuccess) {
  const form = document.getElementById('patient-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('patient-error');
    errEl.classList.add('hidden');

    const payload = {
      first_name: document.getElementById('p-first-name').value,
      last_name: document.getElementById('p-last-name').value,
      birth_date: document.getElementById('p-birth-date').value,
      gender: document.getElementById('p-gender').value,
      phone: document.getElementById('p-phone').value,
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
      form.reset();
      if (onSuccess) onSuccess(data);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    }
  });
}

const GENDER_LABELS = { M: 'М', F: 'Ж', O: '—' };

function formatFullName(p) {
  const parts = [p.last_name, p.first_name];
  if (p.middle_name) parts.push(p.middle_name);
  return parts.join(' ');
}

let diagnosesChart = null;
let medicationsChart = null;

async function loadDashboard() {
  const res = await apiFetch('/api/analytics/dashboard');
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки дашборда');

  document.getElementById('stat-patients').textContent = data.total_patients;
  document.getElementById('stat-documents').textContent = data.total_documents;
  document.getElementById('stat-diagnoses').textContent = Object.keys(data.diagnoses).length;

  renderBarChart('diagnoses-chart', data.diagnoses, diagnosesChart, (c) => { diagnosesChart = c; });
  renderBarChart('medications-chart', data.medications, medicationsChart, (c) => { medicationsChart = c; });

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
        ${renderPatientActions(p.id, formatFullName(p))}
      </td>
    `;
    tbody.appendChild(tr);
  });

  bindPatientActionButtons(() => loadDashboard());
}

function renderBarChart(canvasId, dataObj, existingChart, setChart) {
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
        backgroundColor: 'rgba(37, 99, 235, 0.7)',
        borderColor: 'rgba(37, 99, 235, 1)',
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 1 } },
        x: { ticks: { maxRotation: 45 } },
      },
    },
  });
  setChart(chart);
}

async function loadPatientsForSelect(selectId) {
  const res = await apiFetch('/api/patients?page=1&page_size=100');
  const data = await res.json();
  const select = document.getElementById(selectId);
  select.innerHTML = '<option value="">— Выберите пациента —</option>';
  data.items.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = formatFullName(p);
    select.appendChild(opt);
  });
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

    try {
      const res = await apiFetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
        headers: {},
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки');

      document.getElementById('upload-modal').classList.add('hidden');
      form.reset();
      progressEl.classList.add('hidden');
      if (onSuccess) onSuccess(data);
    } catch (err) {
      progressEl.classList.add('hidden');
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
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

function initDashboard() {
  if (!requireAuth()) return;
  setupLogout();
  setupModals();
  setupPatientForm(() => loadDashboard());
  setupUploadForm(() => loadDashboard());

  document.getElementById('new-patient-btn').addEventListener('click', () => openModal('patient-modal'));
  document.getElementById('upload-doc-btn').addEventListener('click', async () => {
    await loadPatientsForSelect('upload-patient');
    openModal('upload-modal');
  });

  fetchCurrentUser()
    .then(() => loadDashboard())
    .catch(err => console.error(err));
}

let patientsPage = 1;
const patientsPageSize = 20;

async function loadPatientsList(page = 1) {
  const res = await apiFetch(`/api/patients?page=${page}&page_size=${patientsPageSize}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки');

  patientsPage = page;
  const tbody = document.querySelector('#patients-table tbody');
  tbody.innerHTML = '';

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
        ${renderPatientActions(p.id, formatFullName(p))}
      </td>
    `;
    tbody.appendChild(tr);
  });

  bindPatientActionButtons(() => loadPatientsList(patientsPage));

  const totalPages = Math.ceil(data.total / patientsPageSize) || 1;
  document.getElementById('page-info').textContent = `Страница ${page} из ${totalPages}`;
  document.getElementById('prev-page').disabled = page <= 1;
  document.getElementById('next-page').disabled = page >= totalPages;
}

function initPatientsPage() {
  if (!requireAuth()) return;
  setupLogout();
  setupModals();
  setupPatientForm(() => loadPatientsList(patientsPage));

  document.getElementById('new-patient-btn').addEventListener('click', () => openModal('patient-modal'));
  document.getElementById('prev-page').addEventListener('click', () => loadPatientsList(patientsPage - 1));
  document.getElementById('next-page').addEventListener('click', () => loadPatientsList(patientsPage + 1));

  fetchCurrentUser()
    .then(() => loadPatientsList())
    .catch(err => console.error(err));
}
