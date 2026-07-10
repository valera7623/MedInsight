/** Toast notifications (replaces alert for non-blocking feedback). */
function showToast(message, type = 'info') {
  let host = document.getElementById('app-toasts');
  if (!host) {
    host = document.createElement('div');
    host.id = 'app-toasts';
    host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:360px';
    document.body.appendChild(host);
  }
  const colors = { info: '#1565c0', error: '#b91c1c', success: '#15803d', warning: '#b45309' };
  const toast = document.createElement('div');
  toast.setAttribute('role', 'status');
  toast.style.cssText = `background:${colors[type] || colors.info};color:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:14px`;
  toast.textContent = message;
  host.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function notifyError(message) {
  if (typeof showToast === 'function') showToast(message, 'error');
  else alert(message);
}

function notifySuccess(message) {
  if (typeof showToast === 'function') showToast(message, 'success');
}
