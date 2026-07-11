/**
 * Toolbar for DICOM 3D viewer — presets, W/L, tools (rotate, zoom, pan, reset).
 */

const Dicom3dToolbar = (() => {
  const { PRESETS, PRESET_WL } = window.DicomWlPresets;

  const MODES = [
    { id: 'mip', label: 'MIP' },
    { id: 'minip', label: 'MinIP' },
    { id: 'avg', label: 'Average' },
    { id: 'vr', label: 'VR' },
  ];

  let onAction = null;
  let root = null;

  function buildHtml() {
    const presetBtns = PRESETS.map(
      (p) => `<button type="button" class="btn btn-secondary btn-sm dicom-3d-preset" data-preset="${p.id}">${p.label}</button>`
    ).join('');
    const modeBtns = MODES.map(
      (m) => `<button type="button" class="btn btn-secondary btn-sm dicom-3d-mode" data-mode="${m.id}">${m.label}</button>`
    ).join('');

    return `
      <div class="dicom-3d-toolbar">
        <div class="dicom-3d-toolbar-group">
          <span class="dicom-3d-toolbar-label">Пресеты</span>
          ${presetBtns}
        </div>
        <div class="dicom-3d-toolbar-group">
          <span class="dicom-3d-toolbar-label">Режим</span>
          ${modeBtns}
        </div>
        <div class="dicom-3d-toolbar-group">
          <span class="dicom-3d-toolbar-label">W/L</span>
          <label>Центр <input type="range" id="wl-center" min="0" max="255" value="128"></label>
          <label>Ширина <input type="range" id="wl-width" min="8" max="512" value="256"></label>
        </div>
        <div class="dicom-3d-toolbar-group">
          <span class="dicom-3d-toolbar-label">Инструменты</span>
          <button type="button" class="btn btn-secondary btn-sm" id="tool-rot-left" title="Поворот влево">↺</button>
          <button type="button" class="btn btn-secondary btn-sm" id="tool-rot-right" title="Поворот вправо">↻</button>
          <button type="button" class="btn btn-secondary btn-sm" id="tool-zoom-in" title="Увеличить">🔍+</button>
          <button type="button" class="btn btn-secondary btn-sm" id="tool-zoom-out" title="Уменьшить">🔍−</button>
          <button type="button" class="btn btn-secondary btn-sm" id="tool-reset" title="Сброс">⟲ Сброс</button>
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
        onAction?.('preset', btn.dataset.preset);
      });
    });

    root.querySelectorAll('.dicom-3d-mode').forEach((btn) => {
      btn.addEventListener('click', () => {
        root.querySelectorAll('.dicom-3d-mode').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        onAction?.('mode', btn.dataset.mode);
      });
    });

    const emitWindow = () => {
      onAction?.('window', {
        center: parseInt(wlCenter.value, 10),
        width: parseInt(wlWidth.value, 10),
      });
    };
    wlCenter?.addEventListener('input', emitWindow);
    wlWidth?.addEventListener('input', emitWindow);

    root.querySelector('#tool-rot-left')?.addEventListener('click', () => {
      onAction?.('rotate', { azimuth: -15, elevation: 0 });
    });
    root.querySelector('#tool-rot-right')?.addEventListener('click', () => {
      onAction?.('rotate', { azimuth: 15, elevation: 0 });
    });
    root.querySelector('#tool-zoom-in')?.addEventListener('click', () => onAction?.('zoom', 1));
    root.querySelector('#tool-zoom-out')?.addEventListener('click', () => onAction?.('zoom', -1));
    root.querySelector('#tool-reset')?.addEventListener('click', () => onAction?.('reset'));
  }

  function mount(container, actionCallback) {
    if (!container) return;
    onAction = actionCallback;
    root = container;
    root.innerHTML = buildHtml();
    bindEvents();
    root.querySelector('.dicom-3d-preset[data-preset="default"]')?.classList.add('active');
    root.querySelector('.dicom-3d-mode[data-mode="mip"]')?.classList.add('active');
  }

  function resetUi() {
    if (!root) return;
    root.querySelector('#wl-center').value = 128;
    root.querySelector('#wl-width').value = 256;
    root.querySelectorAll('.dicom-3d-preset').forEach((b) => b.classList.remove('active'));
    root.querySelector('.dicom-3d-preset[data-preset="default"]')?.classList.add('active');
    root.querySelectorAll('.dicom-3d-mode').forEach((b) => b.classList.remove('active'));
    root.querySelector('.dicom-3d-mode[data-mode="mip"]')?.classList.add('active');
  }

  return { mount, resetUi };
})();

window.Dicom3dToolbar = Dicom3dToolbar;
