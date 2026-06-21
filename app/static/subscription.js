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
      return loadSubscription();
    })
    .catch(err => console.error(err));
}
