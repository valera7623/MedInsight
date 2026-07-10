/** Subscription & billing page (Phase 4). */

async function loadSubscription() {
  const planEl = document.getElementById('sub-plan');
  if (!planEl) return;
  try {
    const res = await apiFetch('/api/payments/subscription');
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка подписки');
    planEl.textContent = data.plan_type;
    document.getElementById('sub-usage').textContent = `${data.reports_used} / ${data.reports_limit}`;
    document.getElementById('sub-remaining').textContent = data.reports_remaining;
    await renderPlans(data.plan_type);
  } catch (err) {
    console.error('Subscription error:', err);
    const msg = document.getElementById('subscription-msg');
    if (msg) msg.textContent = err.message || 'Не удалось загрузить данные подписки';
  }
}

async function renderPlans(currentPlan) {
  const wrap = document.getElementById('plans-list');
  if (!wrap) return;
  const res = await apiFetch('/api/payments/prices');
  const data = await res.json();
  if (!res.ok) return;
  const providers = data.providers || {};
  wrap.innerHTML = '';
  data.plans.forEach(p => {
    if (p.plan_type === 'freemium' || p.plan_type === currentPlan) return;
    const priceRub = (p.price_rub / 100).toFixed(0);
    const box = document.createElement('div');
    box.className = 'stat-card plan-card';
    let buttons = '';
    if (providers.stripe) {
      buttons += `<button class="btn btn-primary btn-sm" data-plan="${p.plan_type}" data-provider="stripe">Stripe</button> `;
    }
    if (providers.yookassa) {
      buttons += `<button class="btn btn-secondary btn-sm" data-plan="${p.plan_type}" data-provider="yookassa">ЮKassa</button>`;
    }
    if (!buttons) buttons = '<span class="text-muted-inline">Платёжный провайдер не настроен</span>';
    box.innerHTML = `
      <strong>${p.name}</strong>
      <p class="text-muted">${p.analysis_limit} анализов/мес</p>
      <p>${priceRub} ₽ / $${(p.price_usd / 100).toFixed(2)}</p>
      <div class="plan-card-actions">${buttons}</div>`;
    wrap.appendChild(box);
  });
  wrap.querySelectorAll('button[data-plan]').forEach(btn => {
    btn.addEventListener('click', () => upgradePlan(btn.dataset.provider, btn.dataset.plan));
  });
}

async function upgradePlan(provider, planType) {
  const msg = document.getElementById('subscription-msg');
  const path = provider === 'stripe' ? '/api/payments/create-checkout' : '/api/payments/yookassa/create';
  try {
    const res = await apiFetch(path, { method: 'POST', body: JSON.stringify({ plan_type: planType }) });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || 'Ошибка создания платежа');
    const url = data.checkout_url || data.confirmation_url;
    if (url) window.location.href = url;
    else if (msg) msg.textContent = 'Платёж создан, но URL не получен.';
  } catch (err) {
    if (msg) msg.textContent = err.message;
  }
}

function initSubscriptionPage() {
  if (!requireAuth()) return;
  setupLogout();

  fetchCurrentUser()
    .then(() => {
      showAdminNav();
      return Promise.all([loadSubscription(), loadIntegrations()]);
    })
    .catch(err => console.error(err));
}

async function loadIntegrations() {
  const capRes = await apiFetch('/api/auth/capabilities');
  const cap = await capRes.json().catch(() => ({}));
  if (!cap.telegram_bot_enabled) {
    document.getElementById('telegram-section')?.classList.add('hidden');
  } else {
    await loadTelegramStatus(cap);
    document.getElementById('telegram-link-btn')?.addEventListener('click', linkTelegram);
    document.getElementById('telegram-unlink-btn')?.addEventListener('click', unlinkTelegram);
  }
  await loadTotpStatus();
  document.getElementById('totp-setup-btn')?.addEventListener('click', setupTotp);
  document.getElementById('totp-enable-btn')?.addEventListener('click', enableTotp);
  document.getElementById('totp-disable-btn')?.addEventListener('click', disableTotp);
}

async function loadTelegramStatus(cap = {}) {
  const el = document.getElementById('telegram-status');
  const linkEl = document.getElementById('telegram-bot-link');
  const res = await apiFetch('/api/telegram/status');
  const data = await res.json();
  if (!res.ok) { if (el) el.textContent = 'Ошибка загрузки'; return; }
  const botUser = cap.telegram_bot_username;
  if (linkEl && botUser) {
    linkEl.href = `https://t.me/${botUser}`;
    linkEl.textContent = `@${botUser}`;
    linkEl.classList.remove('hidden');
  }
  if (data.linked) {
    el.textContent = `Привязан: @${data.telegram_username || data.telegram_user_id}`;
    document.getElementById('telegram-unlink-btn')?.classList.remove('hidden');
  } else {
    el.textContent = botUser
      ? `Telegram не привязан. Откройте бота @${botUser} и отправьте /start для кода.`
      : 'Telegram не привязан';
    document.getElementById('telegram-unlink-btn')?.classList.add('hidden');
  }
}

async function linkTelegram() {
  const code = document.getElementById('telegram-link-code')?.value?.trim();
  if (!code) return notifyError('Введите код');
  const res = await apiFetch('/api/telegram/link', { method: 'POST', body: JSON.stringify({ code }) });
  const data = await res.json();
  if (!res.ok) return notifyError(formatApiError(data.detail) || 'Ошибка');
  notifySuccess('Telegram привязан');
  loadTelegramStatus();
}

async function unlinkTelegram() {
  const res = await apiFetch('/api/telegram/link', { method: 'DELETE' });
  if (!res.ok) return notifyError('Не удалось отвязать');
  notifySuccess('Telegram отвязан');
  loadTelegramStatus();
}

async function loadTotpStatus() {
  const el = document.getElementById('totp-status-text');
  const res = await apiFetch('/api/auth/totp/status');
  const data = await res.json();
  if (!res.ok) { if (el) el.textContent = '—'; return; }
  el.textContent = data.enabled ? '2FA включена' : '2FA не настроена';
  document.getElementById('totp-disable-btn')?.classList.toggle('hidden', !data.enabled);
  document.getElementById('totp-setup-btn')?.classList.toggle('hidden', data.enabled);
}

async function setupTotp() {
  const res = await apiFetch('/api/auth/totp/setup');
  const data = await res.json();
  if (!res.ok) return notifyError(formatApiError(data.detail) || 'Ошибка');
  document.getElementById('totp-setup-panel')?.classList.remove('hidden');
  document.getElementById('totp-uri').textContent = data.provisioning_uri;
  document.getElementById('totp-backup-codes').textContent = 'Backup codes: ' + data.backup_codes.join(', ');
}

async function enableTotp() {
  const code = document.getElementById('totp-enable-code')?.value?.trim();
  const res = await apiFetch('/api/auth/totp/enable', { method: 'POST', body: JSON.stringify({ code }) });
  const data = await res.json();
  if (!res.ok) return notifyError(formatApiError(data.detail) || 'Неверный код');
  notifySuccess('2FA включена');
  document.getElementById('totp-setup-panel')?.classList.add('hidden');
  loadTotpStatus();
}

async function disableTotp() {
  const password = prompt('Введите пароль для отключения 2FA:');
  if (!password) return;
  const code = prompt('Введите код 2FA или backup code:');
  if (!code) return;
  const res = await apiFetch('/api/auth/totp/disable', {
    method: 'POST',
    body: JSON.stringify({ password, code }),
  });
  const data = await res.json();
  if (!res.ok) return notifyError(formatApiError(data.detail) || 'Ошибка');
  notifySuccess('2FA отключена');
  loadTotpStatus();
}
