/**
 * MedInsight theme toggle — localStorage + API sync + Chart.js refresh.
 * Load in <head> (without defer) to avoid flash of wrong theme.
 */
(function () {
  const STORAGE_KEY = 'theme';
  const VALID = new Set(['light', 'dark', 'system']);

  function systemPrefersDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function resolveTheme(stored) {
    if (stored === 'dark' || stored === 'light') return stored;
    if (stored === 'system' || !stored) return systemPrefersDark() ? 'dark' : 'light';
    return 'light';
  }

  function applyDomTheme(stored) {
    const root = document.documentElement;
    if (stored === 'light' || stored === 'dark') {
      root.setAttribute('data-theme', stored);
    } else {
      root.removeAttribute('data-theme');
    }
    root.dataset.themePreference = stored || 'system';
  }

  function getStoredTheme() {
    const v = localStorage.getItem(STORAGE_KEY);
    return VALID.has(v) ? v : null;
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // --- Early apply (before paint) ---
  const initialStored = getStoredTheme();
  applyDomTheme(initialStored || 'system');

  window.ThemeManager = {
    STORAGE_KEY,

    getStoredTheme() {
      return getStoredTheme() || 'system';
    },

    getEffectiveTheme() {
      return resolveTheme(this.getStoredTheme());
    },

    applyTheme(stored) {
      const normalized = VALID.has(stored) ? stored : 'system';
      localStorage.setItem(STORAGE_KEY, normalized);
      applyDomTheme(normalized);
      window.dispatchEvent(new CustomEvent('themechange', {
        detail: { theme: normalized, effective: resolveTheme(normalized) },
      }));
    },

    toggleTheme() {
      const effective = this.getEffectiveTheme();
      this.applyTheme(effective === 'dark' ? 'light' : 'dark');
      this.syncToServer(this.getStoredTheme());
    },

    chartColors() {
      return {
        text: cssVar('--chart-text') || cssVar('--text-secondary'),
        grid: cssVar('--chart-grid') || cssVar('--border-primary'),
        bar: cssVar('--chart-bar'),
        barBorder: cssVar('--chart-bar-border'),
        danger: cssVar('--chart-danger'),
        dangerLine: cssVar('--chart-danger-line'),
        primaryLine: cssVar('--chart-primary-line'),
      };
    },

    chartScaleOptions() {
      const c = this.chartColors();
      return {
        x: {
          ticks: { color: c.text },
          grid: { color: c.grid },
        },
        y: {
          beginAtZero: true,
          ticks: { color: c.text },
          grid: { color: c.grid },
        },
      };
    },

    async syncToServer(theme) {
      const token = localStorage.getItem('token');
      if (!token) return;
      try {
        await fetch('/api/preferences/theme', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            ...(localStorage.getItem('tenant_id')
              ? { 'X-Tenant-ID': localStorage.getItem('tenant_id') }
              : {}),
          },
          body: JSON.stringify({ theme: theme || this.getStoredTheme() }),
        });
      } catch (_) {
        /* offline / guest — localStorage is enough */
      }
    },

    async loadFromServer() {
      const token = localStorage.getItem('token');
      if (!token) return;
      try {
        const res = await fetch('/api/preferences', {
          headers: {
            Authorization: `Bearer ${token}`,
            ...(localStorage.getItem('tenant_id')
              ? { 'X-Tenant-ID': localStorage.getItem('tenant_id') }
              : {}),
          },
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.theme && VALID.has(data.theme)) {
          localStorage.setItem(STORAGE_KEY, data.theme);
          applyDomTheme(data.theme);
          window.dispatchEvent(new CustomEvent('themechange', {
            detail: { theme: data.theme, effective: resolveTheme(data.theme) },
          }));
        }
      } catch (_) {
        /* ignore */
      }
    },

    mountToggle(container) {
      if (!container || container.dataset.themeMounted) return;
      container.dataset.themeMounted = '1';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'theme-toggle-btn';
      btn.setAttribute('aria-label', 'Переключить тему');
      btn.title = 'Светлая / тёмная тема';
      btn.innerHTML = '<span class="icon-sun" aria-hidden="true">☀️</span><span class="icon-moon" aria-hidden="true">🌙</span>';
      btn.addEventListener('click', () => this.toggleTheme());
      container.appendChild(btn);
    },

    init() {
      document.querySelectorAll('[data-theme-toggle]').forEach((el) => this.mountToggle(el));
      if (localStorage.getItem('token')) {
        this.loadFromServer();
      }
      if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
          const stored = this.getStoredTheme();
          if (stored === 'system' || !stored) {
            applyDomTheme('system');
            window.dispatchEvent(new CustomEvent('themechange', {
              detail: { theme: 'system', effective: resolveTheme('system') },
            }));
          }
        });
      }
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.ThemeManager.init());
  } else {
    window.ThemeManager.init();
  }
})();
