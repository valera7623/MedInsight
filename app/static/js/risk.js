/** Risk level helpers for prediction cards and dashboard tables. */
function riskLevel(value) {
  if (value < 40) return 'low';
  if (value < 70) return 'medium';
  return 'high';
}

function riskBadge(value) {
  const level = riskLevel(value);
  const labels = { low: 'Низкий', medium: 'Средний', high: 'Высокий' };
  return `<span class="risk-badge risk-badge-${level}">${labels[level]} (${value}%)</span>`;
}

function riskClass(value) {
  return `risk-${riskLevel(value)}`;
}
