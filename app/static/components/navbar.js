// Shared navbar helpers: ws-status badge + mobile toggle on pages that include .navbar.
(function () {
  function ensureWsStatus() {
    const actions = document.querySelector('.navbar .nav-actions');
    if (!actions || document.getElementById('ws-status')) return;
    const el = document.createElement('span');
    el.id = 'ws-status';
    el.className = 'text-muted';
    el.style.cssText = 'font-size:0.75rem;margin-right:0.5rem';
    el.title = 'Real-time статус';
    el.textContent = '—';
    actions.insertBefore(el, actions.firstChild);
  }

  function ensureNavToggle() {
    const navbar = document.querySelector('.navbar');
    if (!navbar || document.getElementById('nav-toggle')) return;
    const brand = navbar.querySelector('.nav-brand');
    const toggle = document.createElement('button');
    toggle.className = 'nav-toggle';
    toggle.id = 'nav-toggle';
    toggle.setAttribute('aria-label', 'Меню');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '☰';
    if (brand && brand.nextSibling) {
      navbar.insertBefore(toggle, brand.nextSibling);
    } else {
      navbar.prepend(toggle);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    ensureWsStatus();
    ensureNavToggle();
  });
})();
