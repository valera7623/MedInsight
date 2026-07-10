/** Demo-mode banner for buyer presentation stack. */
(function () {
  function isDemoMode() {
    return (
      localStorage.getItem('demo_mode') === 'true' ||
      window.location.hostname.startsWith('demo.')
    );
  }

  function ensureBanner() {
    if (!isDemoMode() || document.getElementById('demo-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'demo-banner';
    banner.className = 'demo-banner';
    banner.innerHTML = `
      <div class="demo-banner-content">
        <span class="demo-badge">ДЕМО</span>
        <span class="demo-text">
          Вы используете демо-версию для ознакомления.
          Создание и изменение данных недоступны.
        </span>
      </div>`;
    document.body.prepend(banner);
    document.body.classList.add('has-demo-banner');
  }

  function lockWriteActions() {
    if (!isDemoMode()) return;
    const selectors = [
      '#new-patient-btn',
      '#upload-doc-btn',
      '#create-tenant-btn',
      '#patient-upload-dicom-btn',
      '.delete-btn',
      '.doc-delete-btn',
      '.patient-dicom-delete-btn',
      '.tenant-del',
      '.tenant-edit',
      '.dept-del',
      '#dept-form button[type="submit"]',
      '#upload-form button[type="submit"]',
      '#patient-form button[type="submit"]',
      '[data-act="delete"]',
      '[data-act="block"]',
      '[data-act="unblock"]',
    ];
    document.querySelectorAll(selectors.join(',')).forEach((el) => {
      el.disabled = true;
      el.setAttribute('aria-disabled', 'true');
      el.classList.add('demo-disabled');
      el.title = 'В демо-версии недоступно';
      if (el.tagName === 'A' || el.tagName === 'BUTTON') {
        el.addEventListener(
          'click',
          (e) => {
            e.preventDefault();
            e.stopPropagation();
            alert('В демо-версии изменение данных недоступно');
          },
          true
        );
      }
    });
    const tenantsSection = document.getElementById('tenants-section');
    if (tenantsSection) {
      const createBtn = document.getElementById('create-tenant-btn');
      if (createBtn) createBtn.classList.add('hidden');
    }
  }

  window.MedInsightDemo = {
    isDemoMode,
    ensureBanner,
    lockWriteActions,
    apply() {
      if (!isDemoMode()) return;
      ensureBanner();
      lockWriteActions();
    },
    markFromApi(demoMode) {
      if (demoMode) localStorage.setItem('demo_mode', 'true');
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    if (window.location.hostname.startsWith('demo.')) {
      localStorage.setItem('demo_mode', 'true');
    }
    window.MedInsightDemo.apply();
  });
})();
