/**
 * MedInsight Appointments — FullCalendar integration
 */
(function () {
  if (!requireAuth()) return;

  setupLogout();
  setupNav();

  let calendar = null;
  let types = [];
  let patients = [];
  let doctors = [];
  let editingId = null;

  const STATUS_LABELS = {
    scheduled: 'Запланирован',
    confirmed: 'Подтверждён',
    in_progress: 'В процессе',
    completed: 'Завершён',
    cancelled: 'Отменён',
    no_show: 'Не явился',
  };

  function isScheduleView() {
    return window.location.pathname.includes('/schedule');
  }

  function toLocalInputValue(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function buildQuery(params) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== '') q.set(k, v);
    });
    const s = q.toString();
    return s ? `?${s}` : '';
  }

  async function loadTypes() {
    const res = await apiFetch('/api/appointments/types');
    if (!res.ok) throw new Error('Failed to load types');
    types = await res.json();
    const sel = document.getElementById('appt-type');
    sel.innerHTML = types.map((t) => `<option value="${t.id}" data-duration="${t.duration_minutes}">${t.name} (${t.duration_minutes} мин)</option>`).join('');
  }

  async function loadPatients() {
    const res = await apiFetch('/api/patients?limit=100');
    if (!res.ok) return;
    const data = await res.json();
    patients = data.items || [];
    const sel = document.getElementById('appt-patient');
    sel.innerHTML = '<option value="">— выберите —</option>' + patients.map((p) =>
      `<option value="${p.id}">${p.last_name} ${p.first_name}</option>`
    ).join('');
  }

  async function loadDoctors() {
    const today = new Date().toISOString().slice(0, 10);
    const res = await apiFetch(`/api/appointments/schedule/overview${buildQuery({ start_date: today, end_date: today })}`);
    if (!res.ok) {
      doctors = [];
      return;
    }
    const data = await res.json();
    doctors = (data.doctors || []).map((d) => ({ id: d.doctor_id, full_name: d.doctor_name }));
    const options = doctors.map((d) => `<option value="${d.id}">${d.full_name || d.id}</option>`).join('');
    document.getElementById('appt-doctor').innerHTML = '<option value="">— выберите —</option>' + options;
    document.getElementById('filter-doctor').innerHTML = '<option value="">Все врачи</option>' + options;
    document.getElementById('schedule-doctor').innerHTML = options;
  }

  async function fetchAppointments(rangeStart, rangeEnd) {
    const doctorId = document.getElementById('filter-doctor').value;
    const status = document.getElementById('filter-status').value;
    const q = buildQuery({
      limit: 200,
      date_from: rangeStart.toISOString().slice(0, 10),
      date_to: rangeEnd.toISOString().slice(0, 10),
      doctor_id: doctorId || undefined,
      status: status || undefined,
    });
    const res = await apiFetch(`/api/appointments${q}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.items || [];
  }

  function apptToEvent(appt) {
    return {
      id: String(appt.id),
      title: appt.title,
      start: appt.start_time,
      end: appt.end_time,
      backgroundColor: appt.type_color || '#3B82F6',
      borderColor: appt.type_color || '#3B82F6',
      extendedProps: appt,
    };
  }

  function initCalendar() {
    const el = document.getElementById('calendar');
    calendar = new FullCalendar.Calendar(el, {
      initialView: 'dayGridMonth',
      locale: 'ru',
      headerToolbar: {
        left: 'prev,next today',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek,timeGridDay',
      },
      slotMinTime: '08:00:00',
      slotMaxTime: '20:00:00',
      nowIndicator: true,
      selectable: true,
      editable: false,
      events: async (info, success, failure) => {
        try {
          const items = await fetchAppointments(info.start, info.end);
          success(items.map(apptToEvent));
        } catch (e) {
          failure(e);
        }
      },
      dateClick(info) {
        openModal(null, info.date);
      },
      eventClick(info) {
        openModal(info.event.extendedProps);
      },
    });
    calendar.render();
  }

  function openModal(appt, dateHint) {
    editingId = appt ? appt.id : null;
    document.getElementById('modal-title').textContent = appt ? 'Редактирование приёма' : 'Новый приём';
    document.getElementById('appt-id').value = appt ? appt.id : '';
    document.getElementById('appt-patient').value = appt ? appt.patient_id : '';
    document.getElementById('appt-doctor').value = appt ? appt.doctor_id : '';
    document.getElementById('appt-type').value = appt ? appt.appointment_type_id : (types[0]?.id || '');
    document.getElementById('appt-start').value = appt
      ? toLocalInputValue(appt.start_time)
      : (dateHint ? toLocalInputValue(dateHint) : '');
    document.getElementById('appt-description').value = appt?.description || '';
    document.getElementById('appt-remind').value = appt?.remind_before_minutes || 30;
    document.getElementById('appt-actions').classList.toggle('hidden', !appt);
    document.getElementById('appointment-modal').classList.remove('hidden');
  }

  function closeModal() {
    document.getElementById('appointment-modal').classList.add('hidden');
    editingId = null;
  }

  async function saveAppointment(e) {
    e.preventDefault();
    const startLocal = document.getElementById('appt-start').value;
    const typeId = parseInt(document.getElementById('appt-type').value, 10);
    const type = types.find((t) => t.id === typeId);
    const payload = {
      patient_id: parseInt(document.getElementById('appt-patient').value, 10),
      doctor_id: parseInt(document.getElementById('appt-doctor').value, 10),
      appointment_type_id: typeId,
      start_time: new Date(startLocal).toISOString(),
      duration_minutes: type?.duration_minutes || 30,
      description: document.getElementById('appt-description').value || null,
      remind_before_minutes: parseInt(document.getElementById('appt-remind').value, 10),
    };
    const id = document.getElementById('appt-id').value;
    const res = await apiFetch(id ? `/api/appointments/${id}` : '/api/appointments', {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || 'Ошибка сохранения');
      return;
    }
    closeModal();
    calendar?.refetchEvents();
    if (isScheduleView()) loadSchedule();
  }

  async function appointmentAction(action) {
    if (!editingId) return;
    let body = undefined;
    if (action === 'cancel') {
      const reason = prompt('Причина отмены:');
      if (!reason) return;
      body = JSON.stringify({ reason });
    } else if (action === 'complete') {
      body = JSON.stringify({ notes: '' });
    }
    const path = action === 'cancel'
      ? `/api/appointments/${editingId}/cancel`
      : `/api/appointments/${editingId}/${action}`;
    const res = await apiFetch(path, { method: 'POST', body });
    if (!res.ok) {
      alert('Ошибка операции');
      return;
    }
    closeModal();
    calendar?.refetchEvents();
    loadSchedule();
  }

  async function loadSchedule() {
    const doctorId = document.getElementById('schedule-doctor').value;
    const day = document.getElementById('schedule-date').value;
    if (!doctorId || !day) return;
    const res = await apiFetch(`/api/appointments/schedule/doctor/${doctorId}${buildQuery({ start_date: day, end_date: day })}`);
    if (!res.ok) return;
    const data = await res.json();
    const list = document.getElementById('schedule-list');
    if (!data.appointments?.length) {
      list.innerHTML = '<p>Нет приёмов на выбранную дату.</p>';
      return;
    }
    list.innerHTML = `<table class="data-table"><thead><tr><th>Время</th><th>Пациент</th><th>Тип</th><th>Статус</th></tr></thead><tbody>${
      data.appointments.map((a) => `<tr>
        <td>${new Date(a.start_time).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</td>
        <td>${a.patient_name || '—'}</td>
        <td>${a.type_name || '—'}</td>
        <td><span class="status-badge status-${a.status}">${STATUS_LABELS[a.status] || a.status}</span></td>
      </tr>`).join('')
    }</tbody></table>`;
  }

  async function loadSlots() {
    const doctorId = document.getElementById('schedule-doctor').value;
    const day = document.getElementById('schedule-date').value;
    if (!doctorId || !day) return;
    const res = await apiFetch(`/api/appointments/schedule/available-slots${buildQuery({ doctor_id: doctorId, date: day })}`);
    if (!res.ok) return;
    const data = await res.json();
    const grid = document.getElementById('slots-grid');
    if (!data.slots?.length) {
      grid.innerHTML = '<p>Нет свободных слотов.</p>';
      return;
    }
    grid.innerHTML = data.slots.map((s) => {
      const t = new Date(s.start_time).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
      return `<button type="button" class="slot-btn" data-start="${s.start_time}">${t}</button>`;
    }).join('');
    grid.querySelectorAll('.slot-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        openModal(null, new Date(btn.dataset.start));
      });
    });
  }

  function switchView(mode) {
    const cal = mode === 'calendar';
    document.getElementById('tab-calendar').classList.toggle('active', cal);
    document.getElementById('tab-schedule').classList.toggle('active', !cal);
    document.getElementById('calendar-panel').classList.toggle('hidden', !cal);
    document.getElementById('calendar-toolbar').classList.toggle('hidden', !cal);
    document.getElementById('schedule-panel').classList.toggle('active', !cal);
    if (!cal) loadSchedule();
  }

  function setupTabs() {
    document.getElementById('tab-calendar').addEventListener('click', () => {
      history.replaceState(null, '', '/appointments');
      switchView('calendar');
    });
    document.getElementById('tab-schedule').addEventListener('click', () => {
      history.replaceState(null, '', '/appointments/schedule');
      switchView('schedule');
    });
    if (isScheduleView()) switchView('schedule');
  }

  function setupWs() {
    if (typeof connectWebSocket !== 'function') return;
    connectWebSocket((msg) => {
      if (msg.event === 'appointment.reminder' || msg.event === 'appointment.created' || msg.event === 'appointment.updated') {
        calendar?.refetchEvents();
      }
    });
  }

  async function init() {
    const today = new Date().toISOString().slice(0, 10);
    document.getElementById('schedule-date').value = today;
    await Promise.all([loadTypes(), loadPatients(), loadDoctors()]);
    initCalendar();
    setupTabs();
    setupWs();

    document.getElementById('filter-doctor').addEventListener('change', () => calendar.refetchEvents());
    document.getElementById('filter-status').addEventListener('change', () => calendar.refetchEvents());
    document.getElementById('new-appointment-btn').addEventListener('click', () => openModal());
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.querySelector('#appointment-modal .modal-backdrop').addEventListener('click', closeModal);
    document.getElementById('appointment-form').addEventListener('submit', saveAppointment);
    document.getElementById('appt-confirm').addEventListener('click', () => appointmentAction('confirm'));
    document.getElementById('appt-complete').addEventListener('click', () => appointmentAction('complete'));
    document.getElementById('appt-cancel-appt').addEventListener('click', () => appointmentAction('cancel'));
    document.getElementById('load-slots-btn').addEventListener('click', loadSlots);
    document.getElementById('schedule-doctor').addEventListener('change', loadSchedule);
    document.getElementById('schedule-date').addEventListener('change', loadSchedule);
    document.getElementById('export-ics-btn').addEventListener('click', async () => {
      const res = await apiFetch('/api/appointments/export/ics');
      if (!res.ok) { alert('Ошибка экспорта'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'appointments.ics';
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  init().catch((err) => console.error(err));
})();
