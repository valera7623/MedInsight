/**
 * DICOM 3D Viewer — server-side VR/MPR with incremental image loading.
 */

const PREVIEW_MAX_EDGE = 512;

const MODE_LABELS = {
  mip: 'MIP — проекция объёма',
  minip: 'MinIP — проекция объёма',
  avg: 'Average — усреднение',
  vr: 'VR — объём с освещением',
};

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
  mprRefreshTimer: null,
  pendingMpr: { axial: false, coronal: false, sagittal: false },
  lastPreview: null,
  zoom: 1,
  objectUrls: [],
  imageUrls: { vr: null, axial: null, coronal: null, sagittal: null },
};

function authHeaders() {
  const token = typeof getToken === 'function' ? getToken() : null;
  const tenantId = typeof getTenantId === 'function' ? getTenantId() : null;
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
  };
}

function setImageUrl(key, url) {
  const prev = viewer3dState.imageUrls[key];
  if (prev) URL.revokeObjectURL(prev);
  viewer3dState.imageUrls[key] = url;
}

function revokeObjectUrls() {
  Object.values(viewer3dState.imageUrls).forEach((url) => {
    if (url) URL.revokeObjectURL(url);
  });
  viewer3dState.imageUrls = { vr: null, axial: null, coronal: null, sagittal: null };
  viewer3dState.objectUrls.forEach((url) => URL.revokeObjectURL(url));
  viewer3dState.objectUrls = [];
}

async function api3d(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (res.status === 401) {
    if (typeof clearSession === 'function') clearSession();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res;
}

async function api3dImage(path, cacheKey) {
  const res = await api3d(path);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  if (cacheKey) setImageUrl(cacheKey, url);
  else viewer3dState.objectUrls.push(url);
  return url;
}

function updateVrPanelTitle() {
  const el = document.getElementById('vr-panel-title');
  if (el) el.textContent = MODE_LABELS[viewer3dState.mode] || MODE_LABELS.mip;
}

function setupVrDrag() {
  const canvas = document.getElementById('vr-fallback-canvas');
  if (!canvas) return;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  canvas.style.cursor = 'grab';
  canvas.title = 'Перетащите для поворота проекции';

  canvas.addEventListener('mousedown', (e) => {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.style.cursor = 'grabbing';
  });
  window.addEventListener('mouseup', () => {
    dragging = false;
    canvas.style.cursor = 'grab';
  });
  canvas.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    viewer3dState.azimuth = (viewer3dState.azimuth + dx * 0.4) % 360;
    viewer3dState.elevation = Math.max(-90, Math.min(90, viewer3dState.elevation - dy * 0.25));
    scheduleVrRefresh();
  });
}

function setStatus(text, isError = false) {
  const el = document.getElementById('volume-status');
  if (el) {
    el.textContent = text;
    el.classList.toggle('error', isError);
    el.title = isError || text.length > 40 ? text : '';
  }
}

function showVolumeWarning(info) {
  const warn = info?.warning;
  if (!warn) return;
  let banner = document.getElementById('dicom-3d-warning');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'dicom-3d-warning';
    banner.className = 'dicom-3d-warning';
    document.querySelector('.dicom-3d-layout')?.prepend(banner);
  }
  banner.textContent = warn;
  banner.classList.remove('hidden');
}

function renderQueryParams({ includeSlices = false } = {}) {
  const p = new URLSearchParams();
  if (viewer3dState.preset && viewer3dState.preset !== 'custom') {
    p.set('preset', viewer3dState.preset);
  }
  if (viewer3dState.windowCenter != null) p.set('window_center', viewer3dState.windowCenter);
  if (viewer3dState.windowWidth != null) p.set('window_width', viewer3dState.windowWidth);
  if (viewer3dState.mode) p.set('mode', viewer3dState.mode);
  p.set('azimuth', String(viewer3dState.azimuth));
  p.set('elevation', String(viewer3dState.elevation));
  p.set('preview_max_edge', String(PREVIEW_MAX_EDGE));
  if (includeSlices) {
    p.set('axial_slice', String(viewer3dState.slices.axial));
    p.set('coronal_slice', String(viewer3dState.slices.coronal));
    p.set('sagittal_slice', String(viewer3dState.slices.sagittal));
  }
  return p.toString();
}

function mprQueryParams() {
  const p = new URLSearchParams();
  if (viewer3dState.preset && viewer3dState.preset !== 'custom') {
    p.set('preset', viewer3dState.preset);
  }
  if (viewer3dState.windowCenter != null) p.set('window_center', viewer3dState.windowCenter);
  if (viewer3dState.windowWidth != null) p.set('window_width', viewer3dState.windowWidth);
  p.set('preview_max_edge', String(PREVIEW_MAX_EDGE));
  return p.toString();
}

function vrQueryParams() {
  return renderQueryParams({ includeSlices: false });
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

function fitImageToCanvas(canvas, img) {
  const container = canvas.closest('.dicom-3d-viewport, .dicom-3d-mpr-viewport');
  if (!container) return;
  const maxW = Math.max(container.clientWidth, 1);
  const maxH = Math.max(container.clientHeight, 1);
  let scale = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight);
  const isVr = canvas.id === 'vr-fallback-canvas';
  if (isVr) {
    scale *= viewer3dState.zoom;
  }
  const w = Math.max(1, Math.round(img.naturalWidth * scale));
  const h = Math.max(1, Math.round(img.naturalHeight * scale));
  canvas.width = maxW;
  canvas.height = maxH;
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.clearRect(0, 0, maxW, maxH);
  const x = Math.round((maxW - w) / 2);
  const y = Math.round((maxH - h) / 2);
  ctx.drawImage(img, x, y, w, h);
}

function drawUrlOnCanvas(canvas, url) {
  if (!canvas || !url) return;
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      fitImageToCanvas(canvas, img);
      resolve();
    };
    img.onerror = () => reject(new Error('Failed to decode image'));
    img.src = url;
  });
}

async function loadVrRender() {
  const qs = vrQueryParams();
  const url = await api3dImage(
    `/api/dicom/volume/${encodeURIComponent(viewer3dState.studyUid)}/render?${qs}`,
    'vr'
  );
  await drawUrlOnCanvas(document.getElementById('vr-fallback-canvas'), url);
}

async function loadMprSlice(plane) {
  const idx = viewer3dState.slices[plane];
  const qs = mprQueryParams();
  const url = await api3dImage(
    `/api/dicom/volume/${encodeURIComponent(viewer3dState.studyUid)}/mpr/${plane}/${idx}?${qs}`,
    plane
  );
  await drawUrlOnCanvas(document.getElementById(`mpr-${plane}`), url);
}

async function loadAllMpr() {
  await Promise.all(['axial', 'coronal', 'sagittal'].map((plane) => loadMprSlice(plane)));
}

async function loadFullPreview() {
  revokeObjectUrls();
  await Promise.all([loadVrRender(), loadAllMpr()]);
}

function redrawPreview() {
  if (viewer3dState.lastPreview) {
    applyPreview(viewer3dState.lastPreview);
  } else {
    loadVrRender().catch((err) => console.error('VR redraw failed:', err));
  }
}

function applyPreview(preview) {
  viewer3dState.lastPreview = preview;
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
    showVolumeWarning(preview.info);
  }
}

function drawBase64OnCanvas(canvas, b64) {
  if (!canvas || !b64) return;
  const img = new Image();
  img.onload = () => fitImageToCanvas(canvas, img);
  img.src = `data:image/png;base64,${b64}`;
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
      scheduleMprRefresh(plane);
    };
  });
}

function scheduleMprRefresh(plane) {
  viewer3dState.pendingMpr[plane] = true;
  clearTimeout(viewer3dState.mprRefreshTimer);
  viewer3dState.mprRefreshTimer = setTimeout(async () => {
    const planes = Object.entries(viewer3dState.pendingMpr)
      .filter(([, pending]) => pending)
      .map(([p]) => p);
    Object.keys(viewer3dState.pendingMpr).forEach((p) => {
      viewer3dState.pendingMpr[p] = false;
    });
    try {
      await Promise.all(planes.map((p) => loadMprSlice(p)));
    } catch (err) {
      console.error('MPR refresh failed:', err);
    }
  }, 80);
}

function scheduleVrRefresh() {
  clearTimeout(viewer3dState.refreshTimer);
  viewer3dState.refreshTimer = setTimeout(() => {
    loadVrRender().catch((err) => console.error('VR refresh failed:', err));
  }, 120);
}

function scheduleDisplayRefresh({ vr = true, mpr = true } = {}) {
  clearTimeout(viewer3dState.refreshTimer);
  viewer3dState.refreshTimer = setTimeout(async () => {
    try {
      revokeObjectUrls();
      const tasks = [];
      if (vr) tasks.push(loadVrRender());
      if (mpr) tasks.push(loadAllMpr());
      await Promise.all(tasks);
    } catch (err) {
      console.error('Display refresh failed:', err);
    }
  }, 120);
}

function onToolbarAction(action, value) {
  switch (action) {
    case 'preset':
      viewer3dState.preset = value;
      viewer3dState.windowCenter = null;
      viewer3dState.windowWidth = null;
      scheduleDisplayRefresh();
      break;
    case 'mode':
      viewer3dState.mode = value;
      updateVrPanelTitle();
      scheduleVrRefresh();
      break;
    case 'window':
      viewer3dState.preset = 'custom';
      viewer3dState.windowCenter = value.center;
      viewer3dState.windowWidth = value.width;
      scheduleDisplayRefresh();
      break;
    case 'rotate':
      viewer3dState.azimuth = (viewer3dState.azimuth + (value?.azimuth || 0)) % 360;
      viewer3dState.elevation = Math.max(-90, Math.min(90, viewer3dState.elevation + (value?.elevation || 0)));
      scheduleVrRefresh();
      break;
    case 'zoom':
      viewer3dState.zoom = Math.max(0.5, Math.min(3, viewer3dState.zoom * (value > 0 ? 1.15 : 0.87)));
      redrawPreview();
      break;
    case 'reset':
      viewer3dState.azimuth = 0;
      viewer3dState.elevation = 0;
      viewer3dState.preset = 'default';
      viewer3dState.mode = 'mip';
      viewer3dState.zoom = 1;
      updateVrPanelTitle();
      scheduleDisplayRefresh();
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
  setupVrDrag();
  updateVrPanelTitle();

  try {
    const info = await ensureVolumeReady(studyUid);
    viewer3dState.volumeInfo = info;
    setupSliceSliders(info);
    showVolumeWarning(info);

    setStatus('Рендер…');
    await loadFullPreview();

    const mod = info.modality || '';
    setStatus(`Готово · ${info.num_slices || 0} срезов · ${mod}`);
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

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(redrawPreview, 150);
});
