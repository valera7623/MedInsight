/**
 * DICOM annotation editor — select, move, resize, edit popup, keyboard shortcuts.
 * Works on top of DicomAnnotationTool.
 */

const HANDLE_SIZE = 7;

class DicomAnnotationEditor {
  constructor(tool, options = {}) {
    this.tool = tool;
    this.overlay = tool.overlayCanvas;
    this.interactionMode = 'select'; // select | move | resize | draw
    this.dragState = null;
    this.activeHandle = null;
    this.history = [];
    this.redoStack = [];
    this.historyLimit = options.historyLimit || 50;
    this.onEdit = options.onEdit || (() => {});
    this._bindEvents();
  }

  setInteractionMode(mode) {
    this.interactionMode = mode;
    if (mode === 'draw') {
      this.tool.setTool(this.tool.tool || 'rectangle');
    }
    this.tool.redraw();
  }

  _bindEvents() {
    if (!this.overlay) return;
    this.overlay.addEventListener('dblclick', e => this._onDblClick(e));
    this.overlay.addEventListener('mousedown', e => this._onEditMouseDown(e), true);
    this.overlay.addEventListener('mousemove', e => this._onEditMouseMove(e), true);
    this.overlay.addEventListener('mouseup', e => this._onEditMouseUp(e), true);
    window.addEventListener('keydown', e => this._onKeyDown(e));
  }

  _canvasPoint(evt) {
    return this.tool._canvasPoint(evt);
  }

  _findAnnotationAt(pt) {
    for (let i = this.tool.annotations.length - 1; i >= 0; i--) {
      const ann = this.tool.annotations[i];
      if (this._hitTest(ann, pt)) return ann;
    }
    return null;
  }

  _hitTest(ann, pt) {
    const c = ann.coordinates || {};
    const tol = 8;
    if (ann.type === 'rectangle') {
      const x1 = Math.min(c.x1, c.x2), x2 = Math.max(c.x1, c.x2);
      const y1 = Math.min(c.y1, c.y2), y2 = Math.max(c.y1, c.y2);
      return pt.x >= x1 - tol && pt.x <= x2 + tol && pt.y >= y1 - tol && pt.y <= y2 + tol;
    }
    if (ann.type === 'circle') {
      const d = Math.hypot(pt.x - c.cx, pt.y - c.cy);
      return Math.abs(d - (c.radius || 0)) < tol || d < (c.radius || 0);
    }
    if (ann.type === 'text') {
      return Math.hypot(pt.x - (c.x || 0), pt.y - (c.y || 0)) < tol;
    }
    if (c.x1 != null && c.x2 != null) {
      const d = this._pointToSegment(pt, { x: c.x1, y: c.y1 }, { x: c.x2, y: c.y2 });
      return d < tol;
    }
    return false;
  }

  _pointToSegment(p, a, b) {
    const dx = b.x - a.x, dy = b.y - a.y;
    if (!dx && !dy) return Math.hypot(p.x - a.x, p.y - a.y);
    const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)));
    return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
  }

  getHandles(ann) {
    const c = ann.coordinates || {};
    const h = [];
    if (ann.type === 'rectangle') {
      const x1 = Math.min(c.x1, c.x2), x2 = Math.max(c.x1, c.x2);
      const y1 = Math.min(c.y1, c.y2), y2 = Math.max(c.y1, c.y2);
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      [
        [x1, y1, 'nw'], [mx, y1, 'n'], [x2, y1, 'ne'],
        [x1, my, 'w'], [x2, my, 'e'],
        [x1, y2, 'sw'], [mx, y2, 's'], [x2, y2, 'se'],
      ].forEach(([x, y, id]) => h.push({ x, y, id }));
    } else if (ann.type === 'circle') {
      h.push({ x: c.cx, y: c.cy, id: 'center' });
      h.push({ x: c.cx + (c.radius || 0), y: c.cy, id: 'radius' });
    } else if (c.x1 != null) {
      h.push({ x: c.x1, y: c.y1, id: 'start' });
      h.push({ x: c.x2, y: c.y2, id: 'end' });
    } else if (ann.type === 'text') {
      h.push({ x: c.x, y: c.y, id: 'text' });
    }
    return h;
  }

  _findHandle(pt, ann) {
    if (!ann) return null;
    for (const handle of this.getHandles(ann)) {
      if (Math.hypot(pt.x - handle.x, pt.y - handle.y) <= HANDLE_SIZE + 2) return handle;
    }
    return null;
  }

  drawHandles(ctx, ann) {
    if (!ann || ann.id !== this.tool.selectedId) return;
    ctx.save();
    for (const handle of this.getHandles(ann)) {
      ctx.fillStyle = '#FFFFFF';
      ctx.strokeStyle = '#0066FF';
      ctx.lineWidth = 2;
      ctx.fillRect(handle.x - HANDLE_SIZE / 2, handle.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
      ctx.strokeRect(handle.x - HANDLE_SIZE / 2, handle.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
    }
    ctx.restore();
  }

  pushHistory(action, annotationId, before, after) {
    this.history.push({ action, annotation_id: annotationId, before, after });
    if (this.history.length > this.historyLimit) this.history.shift();
    this.redoStack = [];
  }

  undo() {
    if (!this.history.length) {
      this.tool.undo();
      return;
    }
    const entry = this.history.pop();
    this.redoStack.push(entry);
    this._applyState(entry.annotation_id, entry.before);
  }

  redo() {
    if (!this.redoStack.length) {
      this.tool.redo();
      return;
    }
    const entry = this.redoStack.pop();
    this.history.push(entry);
    this._applyState(entry.annotation_id, entry.after);
  }

  _applyState(annotationId, state) {
    const idx = this.tool.annotations.findIndex(a => String(a.id) === String(annotationId));
    if (idx < 0 || !state) return;
    Object.assign(this.tool.annotations[idx], state);
    this.tool.redraw();
    this._persistEdit(annotationId, state);
    this.onEdit();
  }

  async _persistEdit(annotationId, state) {
    if (String(annotationId).startsWith('local-')) return;
    const body = {};
    if (state.coordinates) body.coordinates = state.coordinates;
    if (state.color) body.color = state.color;
    if ('label' in state) body.label = state.label;
    if (state.type) body.type = state.type;
    const endpoint = state.coordinates
      ? `/api/dicom/annotations/${annotationId}/resize`
      : `/api/dicom/annotations/${annotationId}`;
    await apiFetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body.coordinates ? { coordinates: body.coordinates } : body),
    });
  }

  _onEditMouseDown(evt) {
    if (this.interactionMode === 'draw' || evt.button !== 0) return;
    const pt = this._canvasPoint(evt);
    const ann = this._findAnnotationAt(pt);
    if (ann) {
      evt.stopPropagation();
      this.tool.selectAnnotation(ann.id);
      const handle = this._findHandle(pt, ann);
      if (this.interactionMode === 'resize' && handle) {
        this.dragState = { ann, handle, start: pt, orig: JSON.parse(JSON.stringify(ann.coordinates)) };
        this.activeHandle = handle.id;
      } else if (this.interactionMode === 'move' || this.interactionMode === 'select') {
        this.dragState = { ann, handle: null, start: pt, orig: JSON.parse(JSON.stringify(ann.coordinates)) };
      }
      return;
    }
    if (this.interactionMode === 'select') {
      this.tool.selectAnnotation(null);
    }
  }

  _onEditMouseMove(evt) {
    if (!this.dragState) return;
    evt.stopPropagation();
    const pt = this._canvasPoint(evt);
    const dx = pt.x - this.dragState.start.x;
    const dy = pt.y - this.dragState.start.y;
    const ann = this.dragState.ann;
    const orig = this.dragState.orig;

    if (this.dragState.handle) {
      ann.coordinates = this._resizeCoords(ann, orig, this.dragState.handle.id, dx, dy);
    } else {
      ann.coordinates = this._translateCoords(orig, dx, dy);
    }
    this.tool.redraw();
  }

  _onEditMouseUp(evt) {
    if (!this.dragState) return;
    evt.stopPropagation();
    const ann = this.dragState.ann;
    const before = { ...ann, coordinates: this.dragState.orig };
    const after = { ...ann, coordinates: { ...ann.coordinates } };
    this.pushHistory('move', ann.id, before, after);
    this._persistEdit(ann.id, { coordinates: ann.coordinates });
    this.dragState = null;
    this.activeHandle = null;
    this.onEdit();
  }

  _translateCoords(coords, dx, dy) {
    const c = { ...coords };
    for (const key of Object.keys(c)) {
      if (key === 'x' || key.endsWith('x') || key === 'cx') c[key] = (c[key] || 0) + dx;
      if (key === 'y' || key.endsWith('y') || key === 'cy') c[key] = (c[key] || 0) + dy;
    }
    return c;
  }

  _resizeCoords(ann, orig, handleId, dx, dy) {
    const c = { ...orig };
    if (ann.type === 'rectangle') {
      if (handleId.includes('w')) { c.x1 = (orig.x1 < orig.x2 ? orig.x1 : orig.x2) + dx; if (orig.x1 > orig.x2) c.x2 = orig.x1 + dx; else c.x1 = orig.x1 + dx; }
      if (handleId.includes('e')) { c.x2 = orig.x2 + dx; }
      if (handleId === 'n' || handleId === 'nw' || handleId === 'ne') c.y1 = orig.y1 + dy;
      if (handleId === 's' || handleId === 'sw' || handleId === 'se') c.y2 = orig.y2 + dy;
      if (handleId === 'nw') c.x1 = orig.x1 + dx;
      if (handleId === 'ne') c.x2 = orig.x2 + dx;
      if (handleId === 'sw') c.x1 = orig.x1 + dx;
      if (handleId === 'se') c.x2 = orig.x2 + dx;
      return c;
    }
    if (ann.type === 'circle') {
      if (handleId === 'center') return this._translateCoords(orig, dx, dy);
      if (handleId === 'radius') {
        c.radius = Math.max(3, (orig.radius || 0) + dx);
        return c;
      }
    }
    if (handleId === 'start') { c.x1 = orig.x1 + dx; c.y1 = orig.y1 + dy; }
    if (handleId === 'end') { c.x2 = orig.x2 + dx; c.y2 = orig.y2 + dy; }
    if (handleId === 'text') return this._translateCoords(orig, dx, dy);
    return c;
  }

  _onDblClick(evt) {
    if (this.interactionMode === 'draw') return;
    const pt = this._canvasPoint(evt);
    const ann = this._findAnnotationAt(pt);
    if (!ann) return;
    evt.stopPropagation();
    this._showEditPopup(ann);
  }

  _showEditPopup(ann) {
    let popup = document.getElementById('ann-edit-popup');
    if (!popup) {
      popup = document.createElement('div');
      popup.id = 'ann-edit-popup';
      popup.className = 'ann-edit-popup';
      document.body.appendChild(popup);
    }
    const types = ['rectangle', 'circle', 'arrow', 'text', 'line', 'measurement'];
    popup.innerHTML = `
      <div class="ann-edit-popup-inner">
        <h4>Редактировать аннотацию</h4>
        <label>Label <input type="text" id="popup-label" value="${ann.label || ''}"></label>
        <label>Color <input type="color" id="popup-color" value="${ann.color || '#FF0000'}"></label>
        <label>Type
          <select id="popup-type">${types.map(t => `<option value="${t}" ${t === ann.type ? 'selected' : ''}>${t}</option>`).join('')}</select>
        </label>
        <div class="ann-edit-popup-actions">
          <button type="button" class="btn btn-primary btn-sm" id="popup-save">✅ Save</button>
          <button type="button" class="btn btn-secondary btn-sm" id="popup-cancel">❌ Cancel</button>
        </div>
      </div>`;
    popup.classList.remove('hidden');
    popup.querySelector('#popup-cancel').onclick = () => popup.classList.add('hidden');
    popup.querySelector('#popup-save').onclick = async () => {
      const before = { ...ann, coordinates: { ...ann.coordinates } };
      ann.label = popup.querySelector('#popup-label').value || null;
      ann.color = popup.querySelector('#popup-color').value;
      ann.type = popup.querySelector('#popup-type').value;
      const after = { ...ann, coordinates: { ...ann.coordinates } };
      this.pushHistory('edit', ann.id, before, after);
      if (!String(ann.id).startsWith('local-')) {
        await apiFetch(`/api/dicom/annotations/${ann.id}/label`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: ann.label }),
        });
        await apiFetch(`/api/dicom/annotations/${ann.id}/color`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ color: ann.color }),
        });
        await apiFetch(`/api/dicom/annotations/${ann.id}/type`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: ann.type }),
        });
      }
      this.tool.redraw();
      this.onEdit();
      popup.classList.add('hidden');
    };
  }

  _onKeyDown(evt) {
    if (evt.target.tagName === 'INPUT' || evt.target.tagName === 'TEXTAREA') return;
    if ((evt.ctrlKey || evt.metaKey) && evt.key === 'z') {
      evt.preventDefault();
      this.undo();
    }
    if ((evt.ctrlKey || evt.metaKey) && (evt.key === 'y' || (evt.shiftKey && evt.key === 'z'))) {
      evt.preventDefault();
      this.redo();
    }
    if (evt.key === 'Delete' || evt.key === 'Backspace') {
      if (this.tool.selectedId) {
        evt.preventDefault();
        this.tool.deleteSelected();
        this.onEdit();
      }
    }
  }
}

window.DicomAnnotationEditor = DicomAnnotationEditor;
