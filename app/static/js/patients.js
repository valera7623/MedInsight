/** Patients list page logic. */
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
