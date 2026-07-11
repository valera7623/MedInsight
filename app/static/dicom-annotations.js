/** DICOM annotation drawing tools — canvas overlay with auto-save. */

class DicomAnnotationTool {
  constructor(options = {}) {
    this.imageCanvas = options.imageCanvas;
    this.overlayCanvas = options.overlayCanvas || document.getElementById('annotation-canvas');
    this.frameId = options.frameId || null;
    this.pixelSpacing = options.pixelSpacing || null;
    this.autoSaveDelay = options.autoSaveDelay ?? 500;
    this.onSaveStatus = options.onSaveStatus || (() => {});
    this.onAnnotationsChange = options.onAnnotationsChange || (() => {});

    this.annotations = [];
    this.remoteMap = new Map();
    this.tool = 'rectangle';
    this.color = '#FF0000';
    this.label = '';
    this.drawing = false;
    this.startPoint = null;
    this.tempCoords = null;
    this.selectedId = null;
    this.anglePoints = [];
    this.undoStack = [];
    this.redoStack = [];
    this.saveTimer = null;
    this.pendingCreates = [];
    this.viewTransform = { scale: 1, panX: 0, panY: 0, rotation: 0 };
    this.editor = null;

    this._bindOverlayEvents();
  }

  setViewTransform({ scale, panX, panY, rotation }) {
    this.viewTransform = { scale, panX, panY, rotation };
    this.redraw();
  }

  setFrame(frameId, pixelSpacing) {
    this.frameId = frameId;
    this.pixelSpacing = pixelSpacing;
  }

  setTool(tool) {
    this.tool = tool;
    this.anglePoints = [];
    this.tempCoords = null;
  }

  setColor(color) {
    this.color = color;
  }

  setLabel(label) {
    this.label = label;
  }

  async loadAnnotations(frameId) {
    if (!frameId) return;
    this.frameId = frameId;
    const res = await apiFetch(`/api/dicom/annotations/frame/${frameId}`);
    if (!res.ok) return;
    const data = await res.json();
    this.annotations = data.map(a => ({ ...a, local: false }));
    this.remoteMap = new Map(this.annotations.map(a => [a.id, a]));
    this.undoStack = [];
    this.redoStack = [];
    this.redraw();
    this.onAnnotationsChange(this.annotations);
  }

  async loadByInstanceUid(instanceUid) {
    const res = await apiFetch(`/api/dicom/annotations/frame-instance/${encodeURIComponent(instanceUid)}`);
    if (!res.ok) return;
    const data = await res.json();
    this.annotations = data.map(a => ({ ...a, local: false }));
    if (data.length && data[0].frame_id) {
      this.frameId = data[0].frame_id;
    }
    this.remoteMap = new Map(this.annotations.map(a => [a.id, a]));
    this.redraw();
    this.onAnnotationsChange(this.annotations);
  }

  _canvasPoint(evt) {
    const canvas = this.overlayCanvas;
    const rect = canvas.getBoundingClientRect();
    let x = (evt.clientX - rect.left) * (canvas.width / rect.width);
    let y = (evt.clientY - rect.top) * (canvas.height / rect.height);
    const { scale, panX, panY, rotation } = this.viewTransform;
    const w = canvas.width;
    const h = canvas.height;
    x -= w / 2 + panX;
    y -= h / 2 + panY;
    const rad = (-rotation * Math.PI) / 180;
    const cos = Math.cos(rad);
    const sin = Math.sin(rad);
    let rx = x * cos - y * sin;
    let ry = x * sin + y * cos;
    const safeScale = scale || 1;
    rx /= safeScale;
    ry /= safeScale;
    return { x: rx + w / 2, y: ry + h / 2 };
  }

  _bindOverlayEvents() {
    if (!this.overlayCanvas) return;
    this.overlayCanvas.addEventListener('mousedown', e => this._onMouseDown(e));
    this.overlayCanvas.addEventListener('mousemove', e => this._onMouseMove(e));
    this.overlayCanvas.addEventListener('mouseup', e => this._onMouseUp(e));
    this.overlayCanvas.addEventListener('mouseleave', () => {
      if (this.drawing && this.tool !== 'angle') {
        this.drawing = false;
        this.tempCoords = null;
        this.redraw();
      }
    });
  }

  _onMouseDown(evt) {
    if (!this.frameId || evt.button !== 0) return;
    const pt = this._canvasPoint(evt);

    if (this.tool === 'text') {
      const text = prompt('Текст аннотации:', this.label || '');
      if (text === null) return;
      this._pushUndo();
      const ann = this._makeLocal({
        type: 'text',
        coordinates: { x: pt.x, y: pt.y, text },
        color: this.color,
        label: this.label || text,
      });
      this.annotations.push(ann);
      this._scheduleSave(ann);
      this.redraw();
      return;
    }

    if (this.tool === 'angle') {
      this.anglePoints.push(pt);
      if (this.anglePoints.length === 3) {
        const [p1, p2, p3] = this.anglePoints;
        const angle = this._computeAngle(p1, p2, p3);
        this._pushUndo();
        const ann = this._makeLocal({
          type: 'angle',
          coordinates: {
            x1: p1.x, y1: p1.y,
            x2: p2.x, y2: p2.y,
            x3: p3.x, y3: p3.y,
          },
          color: this.color,
          label: this.label || `${angle.toFixed(1)}°`,
          measurement_value: angle,
          measurement_unit: 'deg',
        });
        this.annotations.push(ann);
        this.anglePoints = [];
        this._scheduleSave(ann);
        this.redraw();
      } else {
        this.redraw();
      }
      return;
    }

    if (this.tool === 'measurement') {
      if (!this.drawing) {
        this.drawing = true;
        this.startPoint = pt;
        this.tempCoords = { x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y };
      } else {
        this.tempCoords.x2 = pt.x;
        this.tempCoords.y2 = pt.y;
        const dist = this._pixelDistance(this.tempCoords);
        const mm = this._pixelsToMm(dist, this.tempCoords);
        this._pushUndo();
        const ann = this._makeLocal({
          type: 'measurement',
          coordinates: { ...this.tempCoords },
          color: this.color,
          label: this.label || `${mm.toFixed(2)} mm`,
          measurement_value: mm,
          measurement_unit: 'mm',
        });
        this.annotations.push(ann);
        this.drawing = false;
        this.startPoint = null;
        this.tempCoords = null;
        this._scheduleSave(ann);
        this.redraw();
      }
      return;
    }

    this.drawing = true;
    this.startPoint = pt;
    this.tempCoords = this._initialCoords(pt);
  }

  _onMouseMove(evt) {
    if (!this.drawing || !this.startPoint) {
      if (this.tool === 'angle' && this.anglePoints.length) {
        this.redraw(this._canvasPoint(evt));
      }
      return;
    }
    const pt = this._canvasPoint(evt);
    this.tempCoords = this._updateCoords(this.startPoint, pt);
    this.redraw();
  }

  _onMouseUp(evt) {
    if (!this.drawing || !this.startPoint || this.tool === 'measurement' || this.tool === 'angle') return;
    const pt = this._canvasPoint(evt);
    const coords = this._updateCoords(this.startPoint, pt);
    if (Math.hypot(coords.x2 - coords.x1, coords.y2 - coords.y1) < 3) {
      this.drawing = false;
      this.tempCoords = null;
      this.redraw();
      return;
    }
    this._pushUndo();
    const ann = this._makeLocal({
      type: this.tool,
      coordinates: coords,
      color: this.color,
      label: this.label || null,
    });
    this.annotations.push(ann);
    this.drawing = false;
    this.startPoint = null;
    this.tempCoords = null;
    this._scheduleSave(ann);
    this.redraw();
  }

  _initialCoords(pt) {
    return { x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y };
  }

  _updateCoords(start, end) {
    if (this.tool === 'circle') {
      const r = Math.hypot(end.x - start.x, end.y - start.y);
      return { cx: start.x, cy: start.y, radius: r };
    }
    return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
  }

  _makeLocal(partial) {
    return {
      ...partial,
      id: `local-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      frame_id: this.frameId,
      local: true,
      coordinates: partial.coordinates,
    };
  }

  _pushUndo() {
    this.undoStack.push(JSON.stringify(this.annotations));
    this.redoStack = [];
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.annotations));
    this.annotations = JSON.parse(this.undoStack.pop());
    this.redraw();
    this._scheduleSaveAll();
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.annotations));
    this.annotations = JSON.parse(this.redoStack.pop());
    this.redraw();
    this._scheduleSaveAll();
  }

  selectAnnotation(id) {
    this.selectedId = id;
    this.redraw();
  }

  deleteSelected() {
    if (!this.selectedId) return;
    this._pushUndo();
    const ann = this.annotations.find(a => a.id === this.selectedId);
    this.annotations = this.annotations.filter(a => a.id !== this.selectedId);
    this.selectedId = null;
    this.redraw();
    if (ann && !ann.local) {
      this._deleteRemote(ann.id);
    }
    this.onAnnotationsChange(this.annotations);
  }

  async clearAll() {
    if (!this.frameId || !confirm('Удалить все аннотации на кадре?')) return;
    this._pushUndo();
    await apiFetch(`/api/dicom/annotations/frame/${this.frameId}`, { method: 'DELETE' });
    this.annotations = [];
    this.remoteMap.clear();
    this.redraw();
    this.onAnnotationsChange(this.annotations);
  }

  async saveAll() {
    await this._flushPending();
    this.onSaveStatus('saved');
  }

  _scheduleSave(ann) {
    this.onAnnotationsChange(this.annotations);
    this.pendingCreates.push(ann);
    this.onSaveStatus('saving');
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this._flushPending(), this.autoSaveDelay);
  }

  _scheduleSaveAll() {
    this.onSaveStatus('saving');
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this._syncAll(), this.autoSaveDelay);
  }

  async _flushPending() {
    const queue = [...this.pendingCreates];
    this.pendingCreates = [];
    for (const ann of queue) {
      if (!ann.local) continue;
      const body = {
        frame_id: this.frameId,
        type: ann.type,
        coordinates: ann.coordinates,
        color: ann.color,
        label: ann.label,
        measurement_value: ann.measurement_value,
        measurement_unit: ann.measurement_unit,
      };
      const res = await apiFetch('/api/dicom/annotations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const saved = await res.json();
        const idx = this.annotations.findIndex(a => a.id === ann.id);
        if (idx >= 0) {
          this.annotations[idx] = { ...saved, local: false };
          this.remoteMap.set(saved.id, saved);
        }
      }
    }
    this.onSaveStatus('saved');
    this.onAnnotationsChange(this.annotations);
  }

  async _syncAll() {
    this.onSaveStatus('saved');
    this.onAnnotationsChange(this.annotations);
  }

  async _deleteRemote(id) {
    await apiFetch(`/api/dicom/annotations/${id}`, { method: 'DELETE' });
  }

  async updateAnnotationRemote(id, patch) {
    const res = await apiFetch(`/api/dicom/annotations/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (res.ok) {
      const updated = await res.json();
      const idx = this.annotations.findIndex(a => a.id === id);
      if (idx >= 0) this.annotations[idx] = { ...updated, local: false };
      this.redraw();
      this.onAnnotationsChange(this.annotations);
    }
  }

  _pixelDistance(coords) {
    return Math.hypot(coords.x2 - coords.x1, coords.y2 - coords.y1);
  }

  _pixelsToMm(px, coords) {
    const spacing = this.pixelSpacing;
    if (spacing) {
      const sx = parseFloat(spacing.col ?? spacing[0] ?? 1) || 1;
      const sy = parseFloat(spacing.row ?? spacing[1] ?? 1) || 1;
      if (coords) {
        const dx = (coords.x2 - coords.x1) * sx;
        const dy = (coords.y2 - coords.y1) * sy;
        return Math.hypot(dx, dy);
      }
      return px * ((sx + sy) / 2);
    }
    return px;
  }

  _computeAngle(p1, p2, p3) {
    const v1 = { x: p1.x - p2.x, y: p1.y - p2.y };
    const v2 = { x: p3.x - p2.x, y: p3.y - p2.y };
    const dot = v1.x * v2.x + v1.y * v2.y;
    const mag = Math.hypot(v1.x, v1.y) * Math.hypot(v2.x, v2.y);
    if (!mag) return 0;
    return (Math.acos(Math.max(-1, Math.min(1, dot / mag))) * 180) / Math.PI;
  }

  redraw(previewPoint) {
    const canvas = this.overlayCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const imgCanvas = this.imageCanvas;
    if (imgCanvas) {
      canvas.width = imgCanvas.width;
      canvas.height = imgCanvas.height;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.save();
    this._applyViewTransform(ctx, canvas);

    for (const ann of this.annotations) {
      this._drawAnnotation(ctx, ann, ann.id === this.selectedId);
    }

    if (this.tempCoords) {
      this._drawAnnotation(ctx, { type: this.tool, coordinates: this.tempCoords, color: this.color }, false, true);
    }

    if (this.tool === 'angle' && this.anglePoints.length) {
      ctx.strokeStyle = this.color;
      ctx.lineWidth = 2;
      this.anglePoints.forEach((p, i) => {
        if (i > 0) {
          const prev = this.anglePoints[i - 1];
          ctx.beginPath();
          ctx.moveTo(prev.x, prev.y);
          ctx.lineTo(p.x, p.y);
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
      });
      if (previewPoint && this.anglePoints.length < 3) {
        const last = this.anglePoints[this.anglePoints.length - 1];
        ctx.beginPath();
        ctx.moveTo(last.x, last.y);
        ctx.lineTo(previewPoint.x, previewPoint.y);
        ctx.stroke();
      }
    }

    if (this.editor && this.selectedId) {
      const sel = this.annotations.find(a => String(a.id) === String(this.selectedId));
      if (sel) this.editor.drawHandles(ctx, sel);
    }

    ctx.restore();
  }

  _applyViewTransform(ctx, canvas) {
    const w = canvas.width;
    const h = canvas.height;
    const { scale, panX, panY, rotation } = this.viewTransform;
    ctx.translate(w / 2 + panX, h / 2 + panY);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.scale(scale, scale);
    ctx.translate(-w / 2, -h / 2);
  }

  _drawAnnotation(ctx, ann, selected, dashed) {
    const c = ann.coordinates || {};
    ctx.strokeStyle = ann.color || '#FF0000';
    ctx.fillStyle = ann.color || '#FF0000';
    ctx.lineWidth = selected ? 3 : 2;
    if (dashed) ctx.setLineDash([6, 4]);
    else ctx.setLineDash([]);

    switch (ann.type) {
      case 'rectangle':
        ctx.strokeRect(
          Math.min(c.x1, c.x2),
          Math.min(c.y1, c.y2),
          Math.abs(c.x2 - c.x1),
          Math.abs(c.y2 - c.y1)
        );
        break;
      case 'circle':
        ctx.beginPath();
        ctx.arc(c.cx, c.cy, c.radius || 0, 0, Math.PI * 2);
        ctx.stroke();
        break;
      case 'line':
      case 'measurement':
        ctx.beginPath();
        ctx.moveTo(c.x1, c.y1);
        ctx.lineTo(c.x2, c.y2);
        ctx.stroke();
        if (ann.type === 'measurement') {
          this._drawMeasureTicks(ctx, c);
        }
        break;
      case 'arrow':
        this._drawArrow(ctx, c.x1, c.y1, c.x2, c.y2);
        break;
      case 'text':
        ctx.font = '16px sans-serif';
        ctx.fillText(c.text || ann.label || '', c.x, c.y);
        break;
      case 'angle':
        ctx.beginPath();
        ctx.moveTo(c.x1, c.y1);
        ctx.lineTo(c.x2, c.y2);
        ctx.lineTo(c.x3, c.y3);
        ctx.stroke();
        break;
      default:
        break;
    }

    if (ann.label && ann.type !== 'text') {
      ctx.font = '12px sans-serif';
      ctx.fillText(ann.label, c.x1 ?? c.cx ?? c.x ?? 0, (c.y1 ?? c.cy ?? c.y ?? 0) - 6);
    } else if (ann.type === 'measurement' && ann.measurement_value != null) {
      ctx.font = '12px sans-serif';
      const unit = ann.measurement_unit || 'mm';
      const text = `${Number(ann.measurement_value).toFixed(1)} ${unit}`;
      const lx = c.x1 ?? 0;
      const ly = (c.y1 ?? 0) - 6;
      ctx.fillText(text, lx, ly);
    } else if (ann.type === 'angle' && ann.measurement_value != null) {
      ctx.font = '12px sans-serif';
      const text = ann.label || `${Number(ann.measurement_value).toFixed(1)}°`;
      ctx.fillText(text, c.x2 ?? 0, (c.y2 ?? 0) - 8);
    }
    ctx.setLineDash([]);
  }

  _drawArrow(ctx, x1, y1, x2, y2) {
    const head = 12;
    const angle = Math.atan2(y2 - y1, x2 - x1);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - head * Math.cos(angle - Math.PI / 6), y2 - head * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(x2 - head * Math.cos(angle + Math.PI / 6), y2 - head * Math.sin(angle + Math.PI / 6));
    ctx.closePath();
    ctx.fill();
  }

  _drawMeasureTicks(ctx, c) {
    const mx = (c.x1 + c.x2) / 2;
    const my = (c.y1 + c.y2) / 2;
    const angle = Math.atan2(c.y2 - c.y1, c.x2 - c.x1) + Math.PI / 2;
    const len = 6;
    ctx.beginPath();
    ctx.moveTo(mx - len * Math.cos(angle), my - len * Math.sin(angle));
    ctx.lineTo(mx + len * Math.cos(angle), my + len * Math.sin(angle));
    ctx.stroke();
  }
}

window.DicomAnnotationTool = DicomAnnotationTool;
