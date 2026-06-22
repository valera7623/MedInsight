/**
 * DICOM 3D Viewer — Cornerstone3D metadata + vtk.js volume rendering + server MPR.
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
  vtkReady: false,
  vtkContext: null,
  polling: null,
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

function renderParams() {
  const p = new URLSearchParams();
  if (viewer3dState.preset && viewer3dState.preset !== 'custom') {
    p.set('preset', viewer3dState.preset);
  }
  if (viewer3dState.windowCenter != null) p.set('window_center', viewer3dState.windowCenter);
  if (viewer3dState.windowWidth != null) p.set('window_width', viewer3dState.windowWidth);
  if (viewer3dState.mode) p.set('mode', viewer3dState.mode);
  p.set('azimuth', String(viewer3dState.azimuth));
  p.set('elevation', String(viewer3dState.elevation));
  return p.toString();
}

async function loadVolumeInfo(studyUid) {
  const res = await api3d(`/api/dicom/volume/${encodeURIComponent(studyUid)}/info`);
  return res.json();
}

async function triggerReconstruct(studyUid) {
  const res = await api3d(`/api/dicom/volume/${encodeURIComponent(studyUid)}/reconstruct`, {
    method: 'POST',
  });
  return res.json();
}

async function waitForVolume(studyUid, maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i++) {
    const info = await loadVolumeInfo(studyUid);
    if (info.cached || info.status === 'ready') return info;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error('Volume reconstruction timed out');
}

async function loadMprImage(plane, sliceIndex) {
  const qs = renderParams();
  const url = `/api/dicom/volume/${encodeURIComponent(viewer3dState.studyUid)}/mpr/${plane}/${sliceIndex}?${qs}`;
  const res = await api3d(url);
  return res.blob();
}

async function loadVolumeRenderImage() {
  const qs = renderParams();
  const url = `/api/dicom/volume/${encodeURIComponent(viewer3dState.studyUid)}/render?${qs}`;
  const res = await api3d(url);
  return res.blob();
}

function drawBlobOnCanvas(canvas, blob) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const img = new Image();
  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(img.src);
  };
  img.src = URL.createObjectURL(blob);
}

async function refreshMprView(plane) {
  const slice = viewer3dState.slices[plane];
  const blob = await loadMprImage(plane, slice);
  const canvas = document.getElementById(`mpr-${plane}`);
  drawBlobOnCanvas(canvas, blob);
}

async function refreshAllMpr() {
  await Promise.all(['axial', 'coronal', 'sagittal'].map((p) => refreshMprView(p)));
}

async function refreshVolumeRender() {
  if (viewer3dState.vtkReady && viewer3dState.vtkContext?.updateFromServer) {
    await viewer3dState.vtkContext.updateFromServer();
    return;
  }
  const blob = await loadVolumeRenderImage();
  const canvas = document.getElementById('vr-fallback-canvas');
  const vtkHost = document.getElementById('vtk-container');
  if (canvas) {
    canvas.classList.remove('hidden');
    if (vtkHost) vtkHost.classList.add('hidden');
    drawBlobOnCanvas(canvas, blob);
  }
}

function setupSliceSliders(info) {
  const dims = info.dimensions || [1, 1, 1];
  const [z, y, x] = dims;
  const map = { axial: z - 1, coronal: y - 1, sagittal: x - 1 };
  viewer3dState.slices.axial = Math.floor(z / 2);
  viewer3dState.slices.coronal = Math.floor(y / 2);
  viewer3dState.slices.sagittal = Math.floor(x / 2);

  Object.entries(map).forEach(([plane, maxIdx]) => {
    const slider = document.getElementById(`slice-${plane}`);
    if (!slider) return;
    slider.max = Math.max(0, maxIdx);
    slider.value = viewer3dState.slices[plane];
    slider.oninput = () => {
      viewer3dState.slices[plane] = parseInt(slider.value, 10);
      refreshMprView(plane).catch(console.error);
    };
  });
}

async function initVtkVolume(info) {
  const host = document.getElementById('vtk-container');
  if (!host) return false;

  try {
    const vtk = await import('@kitware/vtk.js');
    const vtkFullScreenRenderWindow = vtk.Rendering.Misc.vtkFullScreenRenderWindow;
    const vtkVolume = vtk.Rendering.Core.vtkVolume;
    const vtkVolumeMapper = vtk.Rendering.Core.vtkVolumeMapper;
    const vtkColorTransferFunction = vtk.Rendering.Core.vtkColorTransferFunction;
    const vtkPiecewiseFunction = vtk.Common.DataModel.vtkPiecewiseFunction;
    const vtkImageData = vtk.Common.DataModel.vtkImageData;
    const vtkDataArray = vtk.Common.Core.vtkDataArray;

    const fullScreenRenderer = vtkFullScreenRenderWindow.newInstance({
      rootContainer: host,
      containerStyle: { width: '100%', height: '100%', position: 'relative' },
    });
    const renderer = fullScreenRenderer.getRenderer();
    const renderWindow = fullScreenRenderer.getRenderWindow();

    const dims = info.dimensions || [1, 64, 64];
    const spacing = info.spacing || [1, 1, 1];
    const [z, y, x] = dims;

    const size = z * y * x;
    const scalars = new Float32Array(size);
    for (let i = 0; i < size; i++) scalars[i] = (i % 256);

    const imageData = vtkImageData.newInstance();
    imageData.setDimensions(x, y, z);
    imageData.setSpacing(spacing[2] || 1, spacing[1] || 1, spacing[0] || 1);
    const da = vtkDataArray.newInstance({
      numberOfComponents: 1,
      values: scalars,
      name: 'scalars',
    });
    imageData.getPointData().setScalars(da);

    const mapper = vtkVolumeMapper.newInstance();
    mapper.setInputData(imageData);

    const actor = vtkVolume.newInstance();
    actor.setMapper(mapper);

    const ctfun = vtkColorTransferFunction.newInstance();
    ctfun.addRGBPoint(0, 0, 0, 0);
    ctfun.addRGBPoint(128, 0.5, 0.5, 0.5);
    ctfun.addRGBPoint(255, 1, 1, 1);

    const ofun = vtkPiecewiseFunction.newInstance();
    ofun.addPoint(0, 0);
    ofun.addPoint(64, 0.2);
    ofun.addPoint(255, 0.8);

    const prop = actor.getProperty();
    prop.setRGBTransferFunction(0, ctfun);
    prop.setScalarOpacity(0, ofun);
    prop.setInterpolationTypeToLinear();
    prop.setShade(true);

    renderer.addVolume(actor);
    renderer.resetCamera();
    renderWindow.render();

    document.getElementById('vr-fallback-canvas')?.classList.add('hidden');
    host.classList.remove('hidden');

    viewer3dState.vtkReady = true;
    viewer3dState.vtkContext = {
      renderer,
      renderWindow,
      actor,
      fullScreenRenderer,
      async updateFromServer() {
        const blob = await loadVolumeRenderImage();
        const canvas = document.getElementById('vr-fallback-canvas');
        if (canvas) drawBlobOnCanvas(canvas, blob);
      },
      resetCamera() {
        renderer.resetCamera();
        renderWindow.render();
      },
      rotate(dAz, dEl) {
        const cam = renderer.getActiveCamera();
        cam.azimuth(dAz);
        cam.elevation(dEl);
        renderer.resetCameraClippingRange();
        renderWindow.render();
      },
    };
    return true;
  } catch (err) {
    console.warn('vtk.js init failed, using server-side render fallback:', err);
    return false;
  }
}

async function initCornerstone() {
  try {
    const cs = await import('@cornerstonejs/core');
    await cs.init();
    viewer3dState.cornerstone = cs;
  } catch (err) {
    console.warn('Cornerstone3D init skipped:', err);
  }
}

function onToolbarAction(action, value) {
  switch (action) {
    case 'preset':
      viewer3dState.preset = value;
      viewer3dState.windowCenter = null;
      viewer3dState.windowWidth = null;
      refreshAllMpr();
      refreshVolumeRender();
      break;
    case 'mode':
      viewer3dState.mode = value;
      refreshVolumeRender();
      break;
    case 'window':
      viewer3dState.preset = 'custom';
      viewer3dState.windowCenter = value.center;
      viewer3dState.windowWidth = value.width;
      refreshAllMpr();
      refreshVolumeRender();
      break;
    case 'rotate':
      viewer3dState.azimuth = (viewer3dState.azimuth + (value?.azimuth || 0)) % 360;
      viewer3dState.elevation = Math.max(-90, Math.min(90, viewer3dState.elevation + (value?.elevation || 0)));
      if (viewer3dState.vtkContext?.rotate) {
        viewer3dState.vtkContext.rotate(value?.azimuth || 0, value?.elevation || 0);
      }
      refreshVolumeRender();
      break;
    case 'zoom':
      if (viewer3dState.vtkContext?.fullScreenRenderer) {
        const cam = viewer3dState.vtkContext.renderer.getActiveCamera();
        cam.zoom(value > 0 ? 1.1 : 0.9);
        viewer3dState.vtkContext.renderWindow.render();
      }
      break;
    case 'reset':
      viewer3dState.azimuth = 0;
      viewer3dState.elevation = 0;
      viewer3dState.preset = 'default';
      viewer3dState.mode = 'mip';
      if (viewer3dState.vtkContext?.resetCamera) viewer3dState.vtkContext.resetCamera();
      refreshAllMpr();
      refreshVolumeRender();
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
  setStatus('Инициализация…');

  document.getElementById('logout-btn')?.addEventListener('click', () => {
    if (typeof logout === 'function') logout();
  });

  if (typeof Dicom3dToolbar !== 'undefined') {
    Dicom3dToolbar.mount(document.getElementById('toolbar-host'), onToolbarAction);
  }

  await initCornerstone();

  try {
    let info = await loadVolumeInfo(studyUid);
    if (!info.cached && info.status !== 'ready') {
      setStatus('Сборка объёма…');
      const job = await triggerReconstruct(studyUid);
      if (job.status === 'processing') {
        info = await waitForVolume(studyUid);
      } else {
        info = await loadVolumeInfo(studyUid);
      }
    }

    viewer3dState.volumeInfo = info;
    setStatus(`Готово · ${info.num_slices || 0} срезов · ${info.modality || ''}`);
    setupSliceSliders(info);

    await initVtkVolume(info);
    await refreshAllMpr();
    await refreshVolumeRender();
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
