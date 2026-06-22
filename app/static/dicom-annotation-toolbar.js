/** Toolbar for DICOM annotation tools. */

const ANNOTATION_COLORS = ['#FF0000', '#00AA00', '#0066FF', '#FFAA00', '#AA00FF', '#00CCCC'];

class DicomAnnotationToolbar {
  constructor(tool, options = {}) {
    this.tool = tool;
    this.container = options.container || document.getElementById('annotation-toolbar');
    this.onToolChange = options.onToolChange || (() => {});
    this.onColorChange = options.onColorChange || (() => {});
    this.onLabelChange = options.onLabelChange || (() => {});
    this.onUndo = options.onUndo || (() => {});
    this.onRedo = options.onRedo || (() => {});
    this.onDelete = options.onDelete || (() => {});
    this.onSaveAll = options.onSaveAll || (() => {});
    this.onClearAll = options.onClearAll || (() => {});
    this.render();
  }

  render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="ann-toolbar-row">
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="rectangle" title="Прямоугольник">📐 Rectangle</button>
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="circle" title="Круг">⭕ Circle</button>
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="arrow" title="Стрелка">➡️ Arrow</button>
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="text" title="Текст">🔤 Text</button>
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="line" title="Линия">📏 Line</button>
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="measurement" title="Расстояние">📐 Measurement</button>
        <button type="button" class="btn btn-secondary btn-sm ann-tool" data-tool="angle" title="Угол">📐 Angle</button>
      </div>
      <div class="ann-toolbar-row">
        <span class="ann-colors">${ANNOTATION_COLORS.map(c =>
          `<button type="button" class="ann-color-swatch" data-color="${c}" style="background:${c}" title="${c}"></button>`
        ).join('')}</span>
        <label class="ann-label-field">Label <input type="text" id="ann-label-input" placeholder="Описание"></label>
        <span id="ann-save-status" class="ann-save-status">🟢 saved</span>
      </div>
      <div class="ann-toolbar-row">
        <button type="button" class="btn btn-secondary btn-sm" id="ann-undo">↩️ Undo</button>
        <button type="button" class="btn btn-secondary btn-sm" id="ann-redo">↪️ Redo</button>
        <button type="button" class="btn btn-secondary btn-sm" id="ann-delete">🗑️ Delete selected</button>
        <button type="button" class="btn btn-primary btn-sm" id="ann-save">💾 Save all</button>
        <button type="button" class="btn btn-danger btn-sm" id="ann-clear">Очистить все</button>
      </div>`;

    this.container.querySelectorAll('.ann-tool').forEach(btn => {
      btn.addEventListener('click', () => {
        this._setActiveTool(btn.dataset.tool);
        this.tool.setTool(btn.dataset.tool);
        this.onToolChange(btn.dataset.tool);
      });
    });

    this.container.querySelectorAll('.ann-color-swatch').forEach(btn => {
      btn.addEventListener('click', () => {
        this.tool.setColor(btn.dataset.color);
        this.onColorChange(btn.dataset.color);
        this.container.querySelectorAll('.ann-color-swatch').forEach(s => s.classList.remove('active'));
        btn.classList.add('active');
      });
    });

    const firstColor = this.container.querySelector('.ann-color-swatch');
    firstColor?.classList.add('active');

    this.container.querySelector('#ann-label-input')?.addEventListener('input', e => {
      this.tool.setLabel(e.target.value);
      this.onLabelChange(e.target.value);
    });

    this.container.querySelector('#ann-undo')?.addEventListener('click', () => this.onUndo());
    this.container.querySelector('#ann-redo')?.addEventListener('click', () => this.onRedo());
    this.container.querySelector('#ann-delete')?.addEventListener('click', () => this.onDelete());
    this.container.querySelector('#ann-save')?.addEventListener('click', () => this.onSaveAll());
    this.container.querySelector('#ann-clear')?.addEventListener('click', () => this.onClearAll());

    this._setActiveTool('rectangle');
  }

  _setActiveTool(tool) {
    this.container?.querySelectorAll('.ann-tool').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tool === tool);
    });
  }

  setSaveStatus(status) {
    const el = this.container?.querySelector('#ann-save-status');
    if (!el) return;
    el.textContent = status === 'saving' ? '🔴 saving' : '🟢 saved';
  }
}

window.DicomAnnotationToolbar = DicomAnnotationToolbar;
