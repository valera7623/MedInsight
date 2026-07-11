/** Session, token refresh, and API client. */
const API = '';

let _refreshPromise = null;

function getToken() {
  return localStorage.getItem('token');
}

function getRefreshToken() {
  return localStorage.getItem('refresh_token');
}

function getTenantId() {
  return localStorage.getItem('tenant_id');
}

function setSession(token, tenantId, role, refreshToken) {
  localStorage.setItem('token', token);
  if (refreshToken) localStorage.setItem('refresh_token', refreshToken);
  if (tenantId != null) localStorage.setItem('tenant_id', String(tenantId));
  if (role) localStorage.setItem('role', role);
}

function clearSession() {
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('tenant_id');
  localStorage.removeItem('role');
}

async function logoutSession(allDevices = false) {
  const refresh = getRefreshToken();
  const token = getToken();
  try {
    await fetch(`${API}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ refresh_token: refresh, all_devices: allDevices }),
    });
  } catch {
    /* best effort */
  }
  clearSession();
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  if (!_refreshPromise) {
    _refreshPromise = fetch(`${API}/api/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) return false;
        setSession(data.access_token, data.tenant_id, data.role, data.refresh_token);
        return true;
      })
      .finally(() => { _refreshPromise = null; });
  }
  return _refreshPromise;
}

async function apiFetch(path, options = {}, retried = false) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const tenantId = getTenantId();
  if (tenantId) headers['X-Tenant-ID'] = tenantId;
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  const res = await fetch(`${API}${path}`, { ...options, headers, credentials: 'include' });

  if (res.status === 401 && !retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return apiFetch(path, options, true);
    clearSession();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}

async function parseApiResponse(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(text.slice(0, 120) || `HTTP ${res.status}`);
  }
}

function formatApiError(detail) {
  if (detail == null || detail === '') return '';
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
  }
  if (typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }
  return String(detail);
}
