/** Dashboard Chart.js helpers (requires Chart.js + dashboard.js shared utils). */
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

