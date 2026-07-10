// MedInsight real-time WebSocket client (Phase 9).
// Usage:
//   const ws = new MedInsightSocket({ onEvent: (e) => {...} });
//   ws.connect();
//
// Handles: JWT auth (query param), auto-reconnect with backoff, app-level
// heartbeat (ping/pong), subscription management, and a connection-status badge.

(function () {
  const KNOWN_EVENTS = [
    'prediction.ready', 'analysis.completed', 'limit.exceeded',
    'document.parsed', 'patient.updated', 'dicom.ready',
  ];

  class MedInsightSocket {
    constructor(opts = {}) {
      this.onEvent = opts.onEvent || (() => {});
      this.events = opts.events || KNOWN_EVENTS;
      this.clientId = opts.clientId || `web-${Math.random().toString(36).slice(2, 10)}`;
      this.ws = null;
      this.reconnectAttempts = 0;
      this.maxReconnectDelay = 30000;
      this.shouldReconnect = true;
      this.heartbeatTimer = null;
    }

    _token() {
      return localStorage.getItem('token');
    }

    _url() {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const token = encodeURIComponent(this._token() || '');
      return `${proto}://${window.location.host}/ws/${this.clientId}?token=${token}`;
    }

    connect() {
      if (!this._token()) {
        console.warn('[ws] no token — skipping WebSocket');
        return;
      }
      this.shouldReconnect = true;
      try {
        this.ws = new WebSocket(this._url());
      } catch (e) {
        console.error('[ws] connect error', e);
        this._scheduleReconnect();
        return;
      }

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this._setStatus(true);
        this.subscribe(this.events);
        this._startHeartbeat();
      };

      this.ws.onmessage = (msg) => {
        let payload;
        try { payload = JSON.parse(msg.data); } catch { return; }
        if (payload.event === 'ping') { this._send({ action: 'pong' }); return; }
        if (payload.event === 'pong' || payload.event === 'connected' || payload.event === 'subscribed') return;
        if (KNOWN_EVENTS.includes(payload.event)) {
          this.onEvent(payload);
          this._toast(payload);
        }
      };

      this.ws.onclose = () => {
        this._setStatus(false);
        this._stopHeartbeat();
        this._scheduleReconnect();
      };

      this.ws.onerror = () => { try { this.ws.close(); } catch {} };
    }

    disconnect() {
      this.shouldReconnect = false;
      this._stopHeartbeat();
      if (this.ws) this.ws.close();
    }

    _send(obj) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(obj));
      }
    }

    subscribe(events) { this._send({ action: 'subscribe', events }); }
    unsubscribe(events) { this._send({ action: 'unsubscribe', events }); }

    _startHeartbeat() {
      this._stopHeartbeat();
      this.heartbeatTimer = setInterval(() => this._send({ action: 'ping' }), 30000);
    }
    _stopHeartbeat() {
      if (this.heartbeatTimer) { clearInterval(this.heartbeatTimer); this.heartbeatTimer = null; }
    }

    _scheduleReconnect() {
      if (!this.shouldReconnect) return;
      this.reconnectAttempts += 1;
      const delay = Math.min(this.maxReconnectDelay, 1000 * 2 ** Math.min(this.reconnectAttempts, 5));
      const attempt = this.reconnectAttempts;
      setTimeout(async () => {
        if (attempt === 1 && typeof refreshAccessToken === 'function') {
          await refreshAccessToken();
        }
        this.connect();
      }, delay);
    }

    _setStatus(connected) {
      const el = document.getElementById('ws-status');
      if (!el) return;
      el.textContent = connected ? '🟢 Online' : '🔴 Offline';
      el.title = connected ? 'Real-time подключено' : 'Real-time отключено';
    }

    _toast(payload) {
      const labels = {
        'prediction.ready': 'Прогноз готов',
        'analysis.completed': 'Анализ завершён',
        'limit.exceeded': 'Лимит анализов исчерпан',
        'document.parsed': 'Документ обработан',
        'patient.updated': 'Пациент обновлён',
      };
      const text = labels[payload.event] || payload.event;
      let host = document.getElementById('ws-toasts');
      if (!host) {
        host = document.createElement('div');
        host.id = 'ws-toasts';
        host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;flex-direction:column;gap:8px';
        document.body.appendChild(host);
      }
      const toast = document.createElement('div');
      toast.style.cssText = 'background:#1565c0;color:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:14px;max-width:320px';
      const d = payload.data || {};
      const extra = d.patient_id ? ` (пациент #${d.patient_id})` : '';
      toast.textContent = `${text}${extra}`;
      host.appendChild(toast);
      setTimeout(() => toast.remove(), 6000);
    }
  }

  window.MedInsightSocket = MedInsightSocket;
})();
