/**
 * W/L toolbar for 2D DICOM viewer — same presets as 3D (without projection modes).
 */
const DicomViewerToolbar = (() => {
  const { PRESETS, PRESET_WL, DEFAULT_WL } = window.DicomWlPresets;

  let onAction = null;
  let root = null;

  function buildHtml() {
    const presetBtns = PRESETS.map(
      (p) => `<button type="button" class="btn btn-secondary btn-sm dicom-3d-preset" data-preset="${p.id}">${p.label}</button>`
    ).join('');

    return `
      <div class="dicom-3d-toolbar">
        <div class="dicom-3d-toolbar-group">
          <span class="dicom-3d-toolbar-label">Пресеты</span>
          ${presetBtns}
        </div>
        <div class="dicom-3d-toolbar-group">
          <span class="dicom-3d-toolbar-label">W/L</span>
          <label>Центр <input type="range" id="wl-center" min="0" max="255" value="${DEFAULT_WL.center}"></label>
          <label>Ширина <input type="range" id="wl-width" min="8" max="512" value="${DEFAULT_WL.width}"></label>
        </div>
      </div>`;
  }

  function bindEvents() {
    const wlCenter = root.querySelector('#wl-center');
    const wlWidth = root.querySelector('#wl-width');

    root.querySelectorAll('.dicom-3d-preset').forEach((btn) => {
      btn.addEventListener('click', () => {
        root.querySelectorAll('.dicom-3d-preset').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        const wl = PRESET_WL[btn.dataset.preset];
        if (wl && wlCenter && wlWidth) {
          wlCenter.value = wl.center;
          wlWidth.value = wl.width;
        }
        onAction?.('preset', {
          id: btn.dataset.preset,
          center: wl?.center ?? DEFAULT_WL.center,
          width: wl?.width ?? DEFAULT_WL.width,
        });
      });
    });

    const emitWindow = () => {
      onAction?.('window', {
        center: parseInt(wlCenter.value, 10),
        width: parseInt(wlWidth.value, 10),
      });
    };
    wlCenter?.addEventListener('input', () => {
      root.querySelectorAll('.dicom-3d-preset').forEach((b) => b.classList.remove('active'));
      emitWindow();
    });
    wlWidth?.addEventListener('input', () => {
      root.querySelectorAll('.dicom-3d-preset').forEach((b) => b.classList.remove('active'));
      emitWindow();
    });
  }

  function mount(container, actionCallback) {
    if (!container) return;
    onAction = actionCallback;
    root = container;
    root.innerHTML = buildHtml();
    bindEvents();
    root.querySelector('.dicom-3d-preset[data-preset="default"]')?.classList.add('active');
  }

  function resetUi() {
    if (!root) return;
    root.querySelector('#wl-center').value = DEFAULT_WL.center;
    root.querySelector('#wl-width').value = DEFAULT_WL.width;
    root.querySelectorAll('.dicom-3d-preset').forEach((b) => b.classList.remove('active'));
    root.querySelector('.dicom-3d-preset[data-preset="default"]')?.classList.add('active');
  }

  function setWindow(center, width, presetId) {
    if (!root) return;
    const wlCenter = root.querySelector('#wl-center');
    const wlWidth = root.querySelector('#wl-width');
    if (wlCenter) wlCenter.value = center;
    if (wlWidth) wlWidth.value = width;
    root.querySelectorAll('.dicom-3d-preset').forEach((b) => b.classList.remove('active'));
    const pid = presetId || 'default';
    root.querySelector(`.dicom-3d-preset[data-preset="${pid}"]`)?.classList.add('active');
  }

  return { mount, resetUi, setWindow };
})();

window.DicomViewerToolbar = DicomViewerToolbar;
