/** OHIF-style DICOM viewer — series/frame navigation, zoom, pan, rotate, window/level. */

const viewerState = {
  study: null,
  seriesIndex: 0,
  frameIndex: 0,
  scale: 1,
  rotation: 0,
  panX: 0,
  panY: 0,
  windowCenter: 128,
  windowWidth: 256,
  preset: 'default',
  dragging: false,
  lastX: 0,
  lastY: 0,
  img: null,
  annotationTool: null,
  annotationEditor: null,
  annotationToolbar: null,
  annotationsEnabled: false,
  annotateMode: false,
};

function getUrlParams() {
  const p = new URLSearchParams(window.location.search);
  return {
    wc: p.get('wc') != null ? parseInt(p.get('wc'), 10) : null,
    ww: p.get('ww') != null ? parseInt(p.get('ww'), 10) : null,
    preset: p.get('preset'),
    frame: parseInt(p.get('frame') || '0', 10),
  };
}

function setUrlParams(frameIndex) {
  const url = new URL(window.location.href);
  url.searchParams.set('frame', String(frameIndex));
  window.history.replaceState({}, '', url);
}

function currentFrames() {
  const series = viewerState.study?.series?.[viewerState.seriesIndex];
  return series?.frames || [];
}

function currentFrame() {
  const frames = currentFrames();
  return frames[viewerState.frameIndex] || null;
}

function imageDimensions(img) {
  if (!img) return { w: 0, h: 0 };
  return {
    w: img.naturalWidth || img.width || 0,
    h: img.naturalHeight || img.height || 0,
  };
}

function releaseViewerImage() {
  const img = viewerState.img;
  if (img && typeof img.close === 'function') {
    img.close();
  }
  viewerState.img = null;
}

function renderMeta() {
  const el = document.getElementById('dicom-meta');
  if (!el || !viewerState.study) return;
  const s = viewerState.study;
  el.innerHTML = `
    <h4>Метаданные</h4>
    <dl class="dicom-meta-list">
      <dt>Пациент</dt><dd>${s.patient_name_dicom || '—'}</dd>
      <dt>Study Date</dt><dd>${s.study_date ? new Date(s.study_date).toLocaleDateString('ru-RU') : '—'}</dd>
      <dt>Modality</dt><dd>${s.modality || '—'}</dd>
      <dt>Body Part</dt><dd>${s.body_part || '—'}</dd>
      <dt>Описание</dt><dd>${s.study_description || '—'}</dd>
    </dl>`;
}

function renderSeriesList() {
  const list = document.getElementById('series-list');
  if (!list || !viewerState.study) return;
  list.innerHTML = (viewerState.study.series || []).map((series, idx) => {
    const active = idx === viewerState.seriesIndex ? 'active' : '';
    return `<li class="${active}" data-idx="${idx}">
      <strong>S${series.series_number ?? idx + 1}</strong>
      <span>${series.modality || ''} · ${series.num_instances} кадр.</span>
      <small>${series.series_description || ''}</small>
    </li>`;
  }).join('');

  list.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => {
      viewerState.seriesIndex = parseInt(li.dataset.idx, 10);
      viewerState.frameIndex = 0;
      viewerState.scale = 1;
      viewerState.rotation = 0;
      viewerState.panX = 0;
      viewerState.panY = 0;
      resetWindowLevel();
      renderSeriesList();
      updateFrameSlider();
      loadCurrentFrameImage();
    });
  });
}

function updateFrameSlider() {
  const frames = currentFrames();
  const slider = document.getElementById('frame-slider');
  const label = document.getElementById('frame-label');
  if (slider) {
    slider.max = Math.max(0, frames.length - 1);
    slider.value = viewerState.frameIndex;
  }
  if (label) {
    label.textContent = `Кадр ${viewerState.frameIndex + 1} / ${Math.max(1, frames.length)}`;
  }
}

function applyWindowLevel(ctx, canvas) {
  const { windowCenter, windowWidth } = viewerState;
  if (window.DicomWlPresets?.isDefault(windowCenter, windowWidth)) return;
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  window.DicomWlPresets.applyToImageData(imageData, windowCenter, windowWidth);
  ctx.putImageData(imageData, 0, 0);
}

function drawImage() {
  const canvas = document.getElementById('dicom-canvas');
  if (!canvas || !viewerState.img) return;
  const ctx = canvas.getContext('2d');
  const wrap = document.getElementById('canvas-wrap');
  const maxW = wrap?.clientWidth || 800;
  const maxH = wrap?.clientHeight || 600;
  const { w: iw, h: ih } = imageDimensions(viewerState.img);
  if (!iw || !ih) return;

  canvas.width = iw;
  canvas.height = ih;

  ctx.save();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.translate(canvas.width / 2 + viewerState.panX, canvas.height / 2 + viewerState.panY);
  ctx.rotate((viewerState.rotation * Math.PI) / 180);
  ctx.scale(viewerState.scale, viewerState.scale);
  ctx.drawImage(viewerState.img, -iw / 2, -ih / 2);
  ctx.restore();

  applyWindowLevel(ctx, canvas);

  canvas.style.maxWidth = `${maxW}px`;
  canvas.style.maxHeight = `${maxH}px`;

  fitCanvasStack();
  syncAnnotationOverlay();
}

function fitCanvasStack() {
  const wrap = document.getElementById('canvas-wrap');
  const canvas = document.getElementById('dicom-canvas');
  const overlay = document.getElementById('annotation-overlay');
  if (!wrap || !canvas || !viewerState.img) return;

  const maxW = wrap.clientWidth || 800;
  const maxH = wrap.clientHeight || 600;
  const { w: iw, h: ih } = imageDimensions(viewerState.img);
  if (!iw || !ih) return;
  const scale = Math.min(maxW / iw, maxH / ih, 1);
  const displayW = Math.max(1, Math.round(iw * scale));
  const displayH = Math.max(1, Math.round(ih * scale));

  for (const el of [canvas, overlay]) {
    if (!el) continue;
    el.style.width = `${displayW}px`;
    el.style.height = `${displayH}px`;
    el.style.maxWidth = `${displayW}px`;
    el.style.maxHeight = `${displayH}px`;
  }
}

function syncAnnotationOverlay() {
  if (!viewerState.annotationTool) return;
  const overlay = document.getElementById('annotation-overlay');
  const canvas = document.getElementById('dicom-canvas');
  if (overlay && canvas) {
    overlay.width = canvas.width;
    overlay.height = canvas.height;
  }
  viewerState.annotationTool.setViewTransform({
    scale: viewerState.scale,
    panX: viewerState.panX,
    panY: viewerState.panY,
    rotation: viewerState.rotation,
  });
  viewerState.annotationTool.redraw();
}

function setAnnotateMode(active) {
  viewerState.annotateMode = active;
  const overlay = document.getElementById('annotation-overlay');
  const viewport = document.querySelector('.dicom-viewport');
  overlay?.classList.toggle('interactive', active);
  viewport?.classList.toggle('annotating', active);
}

async function initViewerAnnotationUi(frame) {
  if (!viewerState.annotationsEnabled || !frame?.id) return;
  const overlay = document.getElementById('annotation-overlay');
  const toolbarEl = document.getElementById('annotation-toolbar');
  if (!overlay || typeof DicomAnnotationTool === 'undefined') return;

  toolbarEl?.classList.remove('hidden');

  if (!viewerState.annotationTool) {
    viewerState.annotationTool = new DicomAnnotationTool({
      imageCanvas: document.getElementById('dicom-canvas'),
      overlayCanvas: overlay,
      frameId: frame.id,
      pixelSpacing: frame.pixel_spacing,
      autoSaveDelay: 500,
      onSaveStatus: status => viewerState.annotationToolbar?.setSaveStatus(status),
    });

    viewerState.annotationEditor = new DicomAnnotationEditor(viewerState.annotationTool, {
      historyLimit: 50,
    });
    viewerState.annotationTool.editor = viewerState.annotationEditor;

    viewerState.annotationToolbar = new DicomAnnotationToolbar(viewerState.annotationTool, {
      container: toolbarEl,
      editor: viewerState.annotationEditor,
      frameId: frame.id,
      onToolChange: () => setAnnotateMode(true),
      onUndo: () => viewerState.annotationEditor?.undo(),
      onRedo: () => viewerState.annotationEditor?.redo(),
      onDelete: () => viewerState.annotationTool.deleteSelected(),
      onSaveAll: () => viewerState.annotationTool.saveAll(),
      onClearAll: () => viewerState.annotationTool.clearAll(),
    });
  } else {
    viewerState.annotationTool.setFrame(frame.id, frame.pixel_spacing);
  }

  setAnnotateMode(false);
  await viewerState.annotationTool.loadAnnotations(frame.id);
  syncAnnotationOverlay();
}

function resetWindowLevel() {
  const def = window.DicomWlPresets?.DEFAULT_WL || { center: 128, width: 256 };
  viewerState.windowCenter = def.center;
  viewerState.windowWidth = def.width;
  viewerState.preset = 'default';
  window.DicomViewerToolbar?.resetUi();
}

function updateView3dLink() {
  const link = document.getElementById('view-3d-link');
  if (!link || !viewerState.study?.study_uid) return;
  const params = new URLSearchParams();
  if (viewerState.preset && viewerState.preset !== 'default') {
    params.set('preset', viewerState.preset);
  }
  if (viewerState.windowCenter != null) params.set('wc', String(viewerState.windowCenter));
  if (viewerState.windowWidth != null) params.set('ww', String(viewerState.windowWidth));
  const qs = params.toString();
  link.href = `/dicom/3d/${encodeURIComponent(viewerState.study.study_uid)}${qs ? `?${qs}` : ''}`;
}

function handleWlToolbarAction(action, value) {
  if (action === 'preset') {
    viewerState.preset = value.id;
    viewerState.windowCenter = value.center;
    viewerState.windowWidth = value.width;
  } else if (action === 'window') {
    viewerState.preset = 'custom';
    viewerState.windowCenter = value.center;
    viewerState.windowWidth = value.width;
  }
  updateView3dLink();
  drawImage();
}

function setupWlToolbar() {
  const host = document.getElementById('dicom-wl-toolbar-host');
  if (host && window.DicomViewerToolbar) {
    DicomViewerToolbar.mount(host, handleWlToolbarAction);
  }
}

function updateAnnotateLink(frame) {
  const link = document.getElementById('annotate-link');
  if (!link || !frame) return;
  const studyUid = viewerState.study?.study_uid;
  const series = viewerState.study?.series?.[viewerState.seriesIndex];
  if (studyUid && series?.series_uid && frame.instance_uid) {
    link.href = `/dicom/annotate/${encodeURIComponent(studyUid)}/${encodeURIComponent(series.series_uid)}/${encodeURIComponent(frame.instance_uid)}`;
    link.classList.remove('hidden');
  } else {
    link.classList.add('hidden');
  }
}

async function loadCurrentFrameImage() {
  const frame = currentFrame();
  if (!frame?.image_url) return;

  const canvas = document.getElementById('dicom-canvas');
  if (!canvas) return;

  const res = await apiFetch(frame.image_url);
  if (!res.ok) {
    console.error('Failed to load frame');
    notifyError('Не удалось загрузить кадр DICOM');
    return;
  }

  let bitmap;
  try {
    bitmap = await createImageBitmap(await res.blob());
  } catch (err) {
    console.error('Failed to decode frame', err);
    notifyError('Не удалось декодировать кадр DICOM');
    return;
  }

  releaseViewerImage();
  viewerState.img = bitmap;
  drawImage();
  setUrlParams(viewerState.frameIndex);
  const current = currentFrame();
  updateAnnotateLink(current);
  try {
    await initViewerAnnotationUi(current);
  } catch (err) {
    console.error('Annotation UI init failed', err);
  }
}

function setupViewerTools() {
  document.getElementById('tool-zoom-in')?.addEventListener('click', () => {
    viewerState.scale = Math.min(viewerState.scale * 1.2, 10);
    drawImage();
  });
  document.getElementById('tool-zoom-out')?.addEventListener('click', () => {
    viewerState.scale = Math.max(viewerState.scale / 1.2, 0.1);
    drawImage();
  });
  document.getElementById('tool-reset')?.addEventListener('click', () => {
    viewerState.scale = 1;
    viewerState.rotation = 0;
    viewerState.panX = 0;
    viewerState.panY = 0;
    resetWindowLevel();
    updateView3dLink();
    drawImage();
  });
  document.getElementById('tool-rotate')?.addEventListener('click', () => {
    viewerState.rotation = (viewerState.rotation + 90) % 360;
    drawImage();
  });

  document.getElementById('frame-slider')?.addEventListener('input', e => {
    viewerState.frameIndex = parseInt(e.target.value, 10);
    updateFrameSlider();
    loadCurrentFrameImage();
  });

  const wrap = document.getElementById('canvas-wrap');
  wrap?.addEventListener('wheel', e => {
    if (viewerState.annotateMode && e.target.closest('#annotation-overlay')) return;
    e.preventDefault();
    viewerState.scale *= e.deltaY < 0 ? 1.1 : 0.9;
    viewerState.scale = Math.max(0.1, Math.min(10, viewerState.scale));
    drawImage();
  });

  wrap?.addEventListener('mousedown', e => {
    if (viewerState.annotateMode) return;
    viewerState.dragging = true;
    viewerState.lastX = e.clientX;
    viewerState.lastY = e.clientY;
  });
  window.addEventListener('mouseup', () => { viewerState.dragging = false; });
  window.addEventListener('mousemove', e => {
    if (!viewerState.dragging || viewerState.annotateMode) return;
    viewerState.panX += e.clientX - viewerState.lastX;
    viewerState.panY += e.clientY - viewerState.lastY;
    viewerState.lastX = e.clientX;
    viewerState.lastY = e.clientY;
    drawImage();
  });
}

async function initDicomViewer(studyUid) {
  if (!requireAuth()) return;
  setupLogout();
  setupWlToolbar();
  setupViewerTools();

  const cfgRes = await apiFetch('/api/dicom/annotations/config');
  if (cfgRes.ok) {
    const cfg = await cfgRes.json();
    viewerState.annotationsEnabled = !!cfg.enabled;
  }

  const urlParams = getUrlParams();
  viewerState.frameIndex = urlParams.frame || 0;
  if (urlParams.preset && window.DicomWlPresets?.PRESET_WL[urlParams.preset]) {
    const wl = window.DicomWlPresets.PRESET_WL[urlParams.preset];
    viewerState.preset = urlParams.preset;
    viewerState.windowCenter = wl.center;
    viewerState.windowWidth = wl.width;
    window.DicomViewerToolbar?.setWindow(wl.center, wl.width, urlParams.preset);
  } else if (urlParams.wc != null && urlParams.ww != null) {
    viewerState.preset = 'custom';
    viewerState.windowCenter = urlParams.wc;
    viewerState.windowWidth = urlParams.ww;
    window.DicomViewerToolbar?.setWindow(urlParams.wc, urlParams.ww, null);
  }

  const res = await apiFetch(`/api/dicom/studies/${encodeURIComponent(studyUid)}`);
  if (!res.ok) {
    notifyError('Исследование не найдено');
    window.location.href = '/dicom';
    return;
  }
  viewerState.study = await res.json();
  document.title = `DICOM — ${viewerState.study.modality || studyUid}`;

  updateView3dLink();

  const deleteBtn = document.getElementById('delete-study-btn');
  if (deleteBtn) {
    if (viewerState.study.can_delete) {
      deleteBtn.classList.remove('hidden');
      deleteBtn.onclick = async () => {
        const label = viewerState.study.study_description || viewerState.study.modality || 'DICOM';
        if (!confirm(`Удалить DICOM-исследование «${label}»? Файлы и кадры будут удалены безвозвратно.`)) {
          return;
        }
        const studyId = viewerState.study.id;
        const del = await apiFetch(`/api/dicom/studies/by-id/${studyId}`, { method: 'DELETE' });
        if (!del.ok) {
          const data = await del.json().catch(() => ({}));
          notifyError(formatApiError(data.detail) || 'Ошибка удаления');
          return;
        }
        window.location.href = '/dicom';
      };
    } else {
      deleteBtn.classList.add('hidden');
    }
  }

  renderMeta();
  renderSeriesList();
  updateFrameSlider();
  await loadCurrentFrameImage();

  window.addEventListener('resize', () => {
    fitCanvasStack();
    syncAnnotationOverlay();
  });
}
