/** OHIF-style DICOM viewer — series/frame navigation, zoom, pan, rotate, window/level. */

const viewerState = {
  study: null,
  seriesIndex: 0,
  frameIndex: 0,
  scale: 1,
  rotation: 0,
  panX: 0,
  panY: 0,
  wl: 100,
  dragging: false,
  lastX: 0,
  lastY: 0,
  img: null,
  annotationTool: null,
  annotationsEnabled: false,
};

function getUrlParams() {
  const p = new URLSearchParams(window.location.search);
  return {
    wc: p.get('wc'),
    ww: p.get('ww'),
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

function applyWindowLevel(ctx, canvas, wlPercent) {
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;
  const factor = wlPercent / 100;
  const brightness = (factor - 0.5) * 80;
  const contrast = 0.5 + factor * 0.5;
  for (let i = 0; i < data.length; i += 4) {
    for (let c = 0; c < 3; c++) {
      let v = data[i + c];
      v = (v - 128) * contrast + 128 + brightness;
      data[i + c] = Math.max(0, Math.min(255, v));
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

function drawImage() {
  const canvas = document.getElementById('dicom-canvas');
  if (!canvas || !viewerState.img) return;
  const ctx = canvas.getContext('2d');
  const wrap = document.getElementById('canvas-wrap');
  const maxW = wrap?.clientWidth || 800;
  const maxH = wrap?.clientHeight || 600;

  canvas.width = viewerState.img.naturalWidth;
  canvas.height = viewerState.img.naturalHeight;

  ctx.save();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.translate(canvas.width / 2 + viewerState.panX, canvas.height / 2 + viewerState.panY);
  ctx.rotate((viewerState.rotation * Math.PI) / 180);
  ctx.scale(viewerState.scale, viewerState.scale);
  ctx.drawImage(viewerState.img, -viewerState.img.naturalWidth / 2, -viewerState.img.naturalHeight / 2);
  ctx.restore();

  if (viewerState.wl !== 100) {
    applyWindowLevel(ctx, canvas, viewerState.wl);
  }

  canvas.style.maxWidth = `${maxW}px`;
  canvas.style.maxHeight = `${maxH}px`;

  syncAnnotationOverlay();
}

function syncAnnotationOverlay() {
  if (!viewerState.annotationTool) return;
  const overlay = document.getElementById('annotation-overlay');
  const canvas = document.getElementById('dicom-canvas');
  if (overlay && canvas) {
    overlay.width = canvas.width;
    overlay.height = canvas.height;
    overlay.style.maxWidth = canvas.style.maxWidth;
    overlay.style.maxHeight = canvas.style.maxHeight;
  }
  viewerState.annotationTool.redraw();
}

async function initViewerAnnotations(frame) {
  if (!viewerState.annotationsEnabled || !frame?.id) return;
  const overlay = document.getElementById('annotation-overlay');
  if (!overlay || typeof DicomAnnotationTool === 'undefined') return;

  if (!viewerState.annotationTool) {
    viewerState.annotationTool = new DicomAnnotationTool({
      imageCanvas: document.getElementById('dicom-canvas'),
      overlayCanvas: overlay,
      frameId: frame.id,
      pixelSpacing: frame.pixel_spacing,
      autoSaveDelay: 500,
    });
  } else {
    viewerState.annotationTool.setFrame(frame.id, frame.pixel_spacing);
  }
  await viewerState.annotationTool.loadAnnotations(frame.id);
  syncAnnotationOverlay();
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

  const img = new Image();
  img.crossOrigin = 'anonymous';
  const token = getToken();
  const tenantId = getTenantId();

  const res = await fetch(frame.image_url, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
    },
  });
  if (!res.ok) {
    console.error('Failed to load frame');
    return;
  }
  const blob = await res.blob();
  img.onload = () => {
    viewerState.img = img;
    drawImage();
    setUrlParams(viewerState.frameIndex);
    const frame = currentFrame();
    updateAnnotateLink(frame);
    initViewerAnnotations(frame);
  };
  img.src = URL.createObjectURL(blob);
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
    viewerState.wl = 100;
    const wl = document.getElementById('wl-slider');
    if (wl) wl.value = '100';
    drawImage();
  });
  document.getElementById('tool-rotate')?.addEventListener('click', () => {
    viewerState.rotation = (viewerState.rotation + 90) % 360;
    drawImage();
  });

  document.getElementById('wl-slider')?.addEventListener('input', e => {
    viewerState.wl = parseInt(e.target.value, 10);
    loadCurrentFrameImage();
  });

  document.getElementById('frame-slider')?.addEventListener('input', e => {
    viewerState.frameIndex = parseInt(e.target.value, 10);
    updateFrameSlider();
    loadCurrentFrameImage();
  });

  const wrap = document.getElementById('canvas-wrap');
  wrap?.addEventListener('wheel', e => {
    e.preventDefault();
    viewerState.scale *= e.deltaY < 0 ? 1.1 : 0.9;
    viewerState.scale = Math.max(0.1, Math.min(10, viewerState.scale));
    drawImage();
  });

  wrap?.addEventListener('mousedown', e => {
    viewerState.dragging = true;
    viewerState.lastX = e.clientX;
    viewerState.lastY = e.clientY;
  });
  window.addEventListener('mouseup', () => { viewerState.dragging = false; });
  window.addEventListener('mousemove', e => {
    if (!viewerState.dragging) return;
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
  setupViewerTools();

  const cfgRes = await apiFetch('/api/dicom/annotations/config');
  if (cfgRes.ok) {
    const cfg = await cfgRes.json();
    viewerState.annotationsEnabled = !!cfg.enabled;
  }

  const urlParams = getUrlParams();
  viewerState.frameIndex = urlParams.frame || 0;

  const res = await apiFetch(`/api/dicom/studies/${encodeURIComponent(studyUid)}`);
  if (!res.ok) {
    notifyError('Исследование не найдено');
    window.location.href = '/dicom';
    return;
  }
  viewerState.study = await res.json();
  document.title = `DICOM — ${viewerState.study.modality || studyUid}`;

  const view3d = document.getElementById('view-3d-link');
  if (view3d) {
    view3d.href = `/dicom/3d/${encodeURIComponent(studyUid)}`;
  }

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
}
