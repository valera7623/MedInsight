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
    toggle.textContent = '☰';
  };

  toggle.addEventListener('click', () => {
    const open = navbar.classList.toggle('nav-open');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.textContent = open ? '✕' : '☰';
  });

  navbar.querySelectorAll('.nav-links a').forEach((a) => a.addEventListener('click', close));
}

document.addEventListener('DOMContentLoaded', setupNav);

function formatApiError(detail) {
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
  }
  if (typeof detail === 'object' && detail !== null) {
    return detail.message || JSON.stringify(detail);
  }
  return detail || 'Неизвестная ошибка';
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
  return currentUser;
}

function isAdmin() {
  return currentUser?.role === 'admin' || currentUser?.role === 'super_admin';
}

function isViewer() {
  return currentUser?.role === 'viewer' || currentUser?.role === 'researcher';
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
let deptRiskChart = null;
let trendsChart = null;

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
        <a href="/patient/${p.id}" class="btn btn-secondary btn-sm">Карточка</a>
        ${renderPatientActions(p.id, formatFullName(p))}
      </td>
    `;
    tbody.appendChild(tr);
  });

  bindPatientActionButtons(() => loadDashboard());
  loadPredictionsDashboard();
  loadSubscription();
  loadWebhooks();
}

// --- Phase 4: Subscription + Webhooks ---

async function loadSubscription() {
  const planEl = document.getElementById('sub-plan');
  if (!planEl) return;
  try {
    const res = await apiFetch('/api/payments/subscription');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка подписки');
    planEl.textContent = data.plan_type;
    document.getElementById('sub-usage').textContent = `${data.reports_used} / ${data.reports_limit}`;
    document.getElementById('sub-remaining').textContent = data.reports_remaining;
    await renderPlans(data.plan_type);
  } catch (err) {
    console.error('Subscription error:', err);
  }
}

async function renderPlans(currentPlan) {
  const wrap = document.getElementById('plans-list');
  if (!wrap) return;
  const res = await apiFetch('/api/payments/prices');
  const data = await res.json();
  if (!res.ok) return;
  const providers = data.providers || {};
  wrap.innerHTML = '';
  data.plans.forEach((p) => {
    if (p.plan_type === 'freemium' || p.plan_type === currentPlan) return;
    const priceRub = (p.price_rub / 100).toFixed(0);
    const box = document.createElement('div');
    box.className = 'stat-card';
    box.style.cssText = 'text-align:left;min-width:220px';
    let buttons = '';
    if (providers.stripe) buttons += `<button class="btn btn-primary btn-sm" data-plan="${p.plan_type}" data-provider="stripe">Stripe</button> `;
    if (providers.yookassa) buttons += `<button class="btn btn-secondary btn-sm" data-plan="${p.plan_type}" data-provider="yookassa">ЮKassa</button>`;
    if (!buttons) buttons = '<span style="color:#94a3b8;font-size:0.8rem">Платёжный провайдер не настроен</span>';
    box.innerHTML = `<strong>${p.name}</strong><br>${p.analysis_limit} анализов/мес<br>${priceRub} ₽ / $${(p.price_usd / 100).toFixed(2)}<div style="margin-top:0.5rem">${buttons}</div>`;
    wrap.appendChild(box);
  });
  wrap.querySelectorAll('button[data-plan]').forEach((btn) => {
    btn.addEventListener('click', () => upgradePlan(btn.dataset.provider, btn.dataset.plan));
  });
}

async function upgradePlan(provider, planType) {
  const msg = document.getElementById('subscription-msg');
  const path = provider === 'stripe' ? '/api/payments/create-checkout' : '/api/payments/yookassa/create';
  try {
    const res = await apiFetch(path, { method: 'POST', body: JSON.stringify({ plan_type: planType }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка создания платежа');
    const url = data.checkout_url || data.confirmation_url;
    if (url) window.location.href = url;
    else if (msg) msg.textContent = 'Платёж создан, но URL не получен.';
  } catch (err) {
    if (msg) msg.textContent = err.message;
  }
}

async function loadWebhooks() {
  const tbody = document.querySelector('#webhooks-table tbody');
  if (!tbody) return;
  try {
    const res = await apiFetch('/api/webhooks');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка вебхуков');
    tbody.innerHTML = data.length
      ? ''
      : '<tr><td colspan="5" style="text-align:center;color:#64748b">Вебхуки не настроены</td></tr>';
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
    const res = await apiFetch('/api/analytics/dashboard/predictions');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки прогнозов');

    statEl.textContent = data.high_risk_patients.length;

    const tbody = document.querySelector('#high-risk-table tbody');
    if (tbody) {
      tbody.innerHTML = '';
      if (data.high_risk_patients.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b">Нет данных — сгенерируйте прогнозы для пациентов</td></tr>';
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
  } catch (err) {
    console.error('Predictions dashboard error:', err);
  }
}

function renderDeptRiskChart(deptData) {
  const canvas = document.getElementById('dept-risk-chart');
  if (!canvas) return;

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
          backgroundColor: 'rgba(220, 38, 38, 0.7)',
        },
        {
          label: 'Осложнения',
          data: complication.length ? complication : [0],
          backgroundColor: 'rgba(37, 99, 235, 0.7)',
        },
      ],
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true, max: 100 } },
    },
  });
}

function renderTrendsChart(trends) {
  const canvas = document.getElementById('trends-chart');
  if (!canvas) return;

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
          borderColor: 'rgba(220, 38, 38, 1)',
          tension: 0.3,
        },
        {
          label: 'Осложнения',
          data: trends.complication || [],
          borderColor: 'rgba(37, 99, 235, 1)',
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true, max: 100 } },
    },
  });
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

function initDashboard() {
  if (!requireAuth()) return;
  setupLogout();
  setupModals();
  setupPatientForm(() => loadDashboard());
  setupUploadForm(() => loadDashboard());
  setupWebhookForm();

  document.getElementById('new-patient-btn').addEventListener('click', () => openModal('patient-modal'));
  document.getElementById('upload-doc-btn').addEventListener('click', async () => {
    await loadPatientsForSelect('upload-patient');
    openModal('upload-modal');
  });

  fetchCurrentUser()
    .then(() => { showAdminNav(); return loadDashboard(); })
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
        <a href="/patient/${p.id}" class="btn btn-secondary btn-sm">Карточка</a>
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

async function pollJobStatus(jobId, onComplete, onError) {
  const maxAttempts = 60;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const res = await apiFetch(`/api/analytics/predict/status/${jobId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка статуса задачи');

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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка запуска прогноза');

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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка генерации инсайтов');

    if (el) {
      el.innerHTML = `
        <div class="recommendations-list">
          <h3>Клиническая заметка</h3>
          <p>${data.insights}</p>
          <h3>Рекомендации</h3>
          <ul>${data.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>
        </div>
      `;
    }
  } catch (err) {
    if (el) el.innerHTML = `<div class="error-message">${err.message}</div>`;
  }
}

async function loadPatientPredictions(patientId) {
  const resultEl = document.getElementById('prediction-result');
  if (!resultEl) return;

  const res = await apiFetch(`/api/analytics/predictions/${patientId}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки прогнозов');

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
        <ul>${pred.factors.map(f => `<li>${f}</li>`).join('')}</ul>
      </div>
    ` : ''}
    ${pred.recommendations?.length ? `
      <div class="recommendations-list">
        <h3>Рекомендации</h3>
        <ul>${pred.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>
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
    docsEl.innerHTML = docs.length
      ? docs.map(d => `<li>${d.filename} — <em>${d.status}</em> (${new Date(d.created_at).toLocaleDateString('ru-RU')})</li>`).join('')
      : '<li style="color:#64748b">Документы не загружены</li>';
  }

  await loadPatientPredictions(patientId);
}

function initPatientPage() {
  if (!requireAuth()) return;
  setupLogout();

  const match = window.location.pathname.match(/\/patient\/(\d+)/);
  const patientId = match ? parseInt(match[1], 10) : null;
  if (!patientId) {
    window.location.href = '/patients';
    return;
  }

  document.getElementById('generate-prediction-btn')?.addEventListener('click', () => startPrediction(patientId));
  document.getElementById('generate-insights-btn')?.addEventListener('click', () => loadPatientInsights(patientId));

  fetchCurrentUser()
    .then(() => loadPatientDetail(patientId))
    .catch(err => console.error(err));
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
    .then(() => { showAdminNav(); return loadPatientsList(); })
    .catch(err => console.error(err));
}
