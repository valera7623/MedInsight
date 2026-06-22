/**
 * DICOM 3D Viewer — fast server-side VR/MPR (single preview API), lazy vtk.js optional.
 */

const viewer3dState = {
  studyUid: null,
  volumeInfo: null,
  slices: { axial: 0, coronal: 0, sagittal: 0 },
  preset: 'default',
  mode: 'mip',
  azimuth: 0,
  elevation: 0,
  windowCenter: null,
  windowWidth: null,
  refreshTimer: null,
};

function authHeaders() {
  const token = typeof getToken === 'function' ? getToken() : null;
  const tenantId = typeof getTenantId === 'function' ? getTenantId() : null;
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
  };
}

async function api3d(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res;
}

function setStatus(text, isError = false) {
  const el = document.getElementById('volume-status');
  if (el) {
    el.textContent = text;
    el.classList.toggle('error', isError);
  }
}

function renderQueryParams() {
  const p = new URLSearchParams();
  if (viewer3dState.preset && viewer3dState.preset !== 'custom') {
    p.set('preset', viewer3dState.preset);
  }
  if (viewer3dState.windowCenter != null) p.set('window_center', viewer3dState.windowCenter);
  if (viewer3dState.windowWidth != null) p.set('window_width', viewer3dState.windowWidth);
  if (viewer3dState.mode) p.set('mode', viewer3dState.mode);
  p.set('azimuth', String(viewer3dState.azimuth));
  p.set('elevation', String(viewer3dState.elevation));
  p.set('axial_slice', String(viewer3dState.slices.axial));
  p.set('coronal_slice', String(viewer3dState.slices.coronal));
  p.set('sagittal_slice', String(viewer3dState.slices.sagittal));
  return p.toString();
}

async function loadVolumeInfo(studyUid) {
  const res = await api3d(`/api/dicom/volume/${encodeURIComponent(studyUid)}/info`);
  return res.json();
}

async function ensureVolumeReady(studyUid) {
  const info = await loadVolumeInfo(studyUid);
  if (info.cached || info.status === 'ready') return info;

  setStatus('Сборка объёма…');
  const res = await api3d(`/api/dicom/volume/${encodeURIComponent(studyUid)}/reconstruct`, {
    method: 'POST',
  });
  const job = await res.json();

  if (job.status === 'ready') {
    return loadVolumeInfo(studyUid);
  }

  let delay = 250;
  for (let i = 0; i < 80; i++) {
    await new Promise((r) => setTimeout(r, delay));
    const next = await loadVolumeInfo(studyUid);
    if (next.cached || next.status === 'ready') return next;
    delay = Math.min(delay * 1.2, 1500);
  }
  throw new Error('Volume reconstruction timed out');
}

async function loadPreview() {
  const qs = renderQueryParams();
  const res = await api3d(
    `/api/dicom/volume/${encodeURIComponent(viewer3dState.studyUid)}/preview?${qs}`
  );
  return res.json();
}

function drawBase64OnCanvas(canvas, b64) {
  if (!canvas || !b64) return;
  const img = new Image();
  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
  };
  img.src = `data:image/png;base64,${b64}`;
}

function applyPreview(preview) {
  drawBase64OnCanvas(document.getElementById('vr-fallback-canvas'), preview.render);

  for (const plane of ['axial', 'coronal', 'sagittal']) {
    drawBase64OnCanvas(document.getElementById(`mpr-${plane}`), preview.mpr?.[plane]);
    if (preview.slices?.[plane] != null) {
      viewer3dState.slices[plane] = preview.slices[plane];
      const slider = document.getElementById(`slice-${plane}`);
      if (slider) slider.value = preview.slices[plane];
    }
  }

  if (preview.info) {
    viewer3dState.volumeInfo = preview.info;
  }
}

function setupSliceSliders(info) {
  const dims = info.dimensions || [1, 1, 1];
  const [z, y, x] = dims;
  const map = { axial: z - 1, coronal: y - 1, sagittal: x - 1 };

  Object.entries(map).forEach(([plane, maxIdx]) => {
    const slider = document.getElementById(`slice-${plane}`);
    if (!slider) return;
    slider.max = Math.max(0, maxIdx);
    if (viewer3dState.slices[plane] == null) {
      viewer3dState.slices[plane] = Math.floor((maxIdx + 1) / 2);
    }
    slider.value = viewer3dState.slices[plane];
    slider.oninput = () => {
      viewer3dState.slices[plane] = parseInt(slider.value, 10);
      schedulePreviewRefresh();
    };
  });
}

function schedulePreviewRefresh() {
  clearTimeout(viewer3dState.refreshTimer);
  viewer3dState.refreshTimer = setTimeout(() => {
    loadPreview()
      .then(applyPreview)
      .catch((err) => console.error('Preview refresh failed:', err));
  }, 120);
}

function scheduleFullRefresh() {
  clearTimeout(viewer3dState.refreshTimer);
  viewer3dState.refreshTimer = setTimeout(() => {
    loadPreview()
      .then(applyPreview)
      .catch((err) => console.error('Preview refresh failed:', err));
  }, 0);
}

function onToolbarAction(action, value) {
  switch (action) {
    case 'preset':
      viewer3dState.preset = value;
      viewer3dState.windowCenter = null;
      viewer3dState.windowWidth = null;
      scheduleFullRefresh();
      break;
    case 'mode':
      viewer3dState.mode = value;
      scheduleFullRefresh();
      break;
    case 'window':
      viewer3dState.preset = 'custom';
      viewer3dState.windowCenter = value.center;
      viewer3dState.windowWidth = value.width;
      schedulePreviewRefresh();
      break;
    case 'rotate':
      viewer3dState.azimuth = (viewer3dState.azimuth + (value?.azimuth || 0)) % 360;
      viewer3dState.elevation = Math.max(-90, Math.min(90, viewer3dState.elevation + (value?.elevation || 0)));
      scheduleFullRefresh();
      break;
    case 'zoom':
      break;
    case 'reset':
      viewer3dState.azimuth = 0;
      viewer3dState.elevation = 0;
      viewer3dState.preset = 'default';
      viewer3dState.mode = 'mip';
      scheduleFullRefresh();
      if (typeof Dicom3dToolbar !== 'undefined') Dicom3dToolbar.resetUi();
      break;
    default:
      break;
  }
}

async function initDicom3dViewer(studyUid) {
  if (typeof requireAuth === 'function') {
    const ok = await requireAuth();
    if (!ok) return;
  }

  viewer3dState.studyUid = studyUid;
  setStatus('Загрузка…');

  document.getElementById('vr-fallback-canvas')?.classList.remove('hidden');

  document.getElementById('logout-btn')?.addEventListener('click', () => {
    if (typeof logout === 'function') logout();
  });

  if (typeof Dicom3dToolbar !== 'undefined') {
    Dicom3dToolbar.mount(document.getElementById('toolbar-host'), onToolbarAction);
  }

  try {
    const info = await ensureVolumeReady(studyUid);
    viewer3dState.volumeInfo = info;
    setupSliceSliders(info);

    const preview = await loadPreview();
    applyPreview(preview);
    setStatus(`Готово · ${info.num_slices || 0} срезов · ${info.modality || ''}`);
  } catch (err) {
    console.error(err);
    setStatus(err.message || 'Ошибка загрузки', true);
  }
}

window.initDicom3dViewer = initDicom3dViewer;

document.addEventListener('DOMContentLoaded', () => {
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts[0] === 'dicom' && parts[1] === '3d' && parts[2]) {
    const studyUid = decodeURIComponent(parts[2]);
    const back = document.getElementById('back-to-2d');
    if (back) back.href = `/dicom/viewer/${encodeURIComponent(studyUid)}`;
    initDicom3dViewer(studyUid);
  }
});
