const API_ROOT = "/api/v1";

const ADMIN_SECTIONS = [
  { slug: "dashboard", label: "Dashboard", icon: "▦", description: "Platform overview and key operational signals." },
  { slug: "realtime", label: "Realtime", icon: "◉", description: "Live try-on volume, generation time, and AI cost." },
  { slug: "organizations", label: "Businesses", icon: "◇", description: "Manage business profiles, usage, tokens, and operational access." },
  { slug: "enquiries", label: "Enquiries", icon: "✦", description: "Review business enquiries submitted through the public contact page." },
  { slug: "customers-subscriptions", label: "Subscriptions", icon: "◎", description: "Manage plans, trials, billing status, cancellations, and renewals." },
  { slug: "billing-pricing", label: "Billing & Pricing", icon: "₹", description: "Review platform billing and pricing configuration." },
  { slug: "platform-operations", label: "Platform Operations", icon: "⚙", description: "Monitor the services that operate Wearo." },
  { slug: "audit-history", label: "Audit History", icon: "≡", description: "Review administrator and platform audit events." },
  { slug: "ai-models-cost", label: "AI Models & Cost", icon: "$", description: "Manage providers, models, funding, and model-level generation cost." },
];

function loginView() {
  return `<main id="main" class="admin-auth">
    <section class="admin-login-card" aria-labelledby="admin-login-title">
      <img class="admin-brand" src="/wearo-brand.png" alt="Wearo.ai" />
      <p class="eyebrow">Platform administration</p>
      <h1 id="admin-login-title">Super Admin sign in</h1>
      <p>Use your authorised Wearo administrator account.</p>
      <form id="admin-login-form">
        <label>Email<input name="email" type="email" autocomplete="username" required /></label>
        <label>Password<input name="password" type="password" autocomplete="current-password" required /></label>
        <button class="button button--primary" type="submit">Sign in</button>
        <p id="admin-login-error" class="form-status form-status--error" role="alert" aria-live="polite"></p>
      </form>
    </section>
  </main>`;
}

function adminSection(pathname) {
  const slug = pathname.replace(/^\/admin\/?/, "").split("/")[0] || "dashboard";
  return ADMIN_SECTIONS.find((section) => section.slug === slug) || ADMIN_SECTIONS[0];
}

function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

function displayEnum(value) {
  return String(value || "Unknown").toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function organizationsView(pathname) {
  const detailId = pathname.split("/")[3];
  if (detailId) {
    return `<div id="admin-organization-detail" class="admin-data-panel" data-tenant-id="${escapeHtml(detailId)}" aria-live="polite">Loading business…</div>`;
  }
  return `<div class="admin-stat-grid" aria-label="Business summary">
      <article><span>Total businesses</span><strong id="organization-total">—</strong></article>
      <article><span>Active businesses</span><strong id="organization-active">—</strong></article>
      <article><span>Paused businesses</span><strong id="organization-paused">—</strong></article>
    </div>
    <form id="organization-filters" class="admin-filters" role="search">
      <label>Search businesses<input name="search" type="search" placeholder="Business name" /></label>
      <label>Business type<select name="businessType"><option value="">All business types</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label>
      <label>Status<select name="status"><option value="">All statuses</option><option value="ACTIVE">Active</option><option value="PAUSED">Paused</option><option value="CANCELLED">Cancelled</option><option value="SUSPENDED">Suspended</option><option value="CLOSED">Closed</option></select></label>
      <button class="button button--primary" type="submit">Apply filters</button>
    </form>
    <div id="organization-list" class="admin-data-panel" aria-live="polite">Loading businesses…</div>`;
}

function platformDashboardView() {
  const metricLabels = ["Total businesses", "Active businesses", "Registered consumers", "Total try-ons", "Successful try-ons", "Failed try-ons", "Tokens consumed", "Average per business"];
  return `<form id="admin-dashboard-filters" class="admin-dashboard-filters">
      <fieldset><legend>Date range</legend><div class="admin-period-options"><label><input type="radio" name="period" value="today" checked /> Today</label><label><input type="radio" name="period" value="week" /> Last 7 Days</label><label><input type="radio" name="period" value="month" /> This Month</label><label><input type="radio" name="period" value="custom" /> Custom</label></div></fieldset>
      <div id="admin-custom-dates" class="admin-custom-dates" hidden><label>From<input name="dateFrom" type="date" /></label><label>To<input name="dateTo" type="date" /></label></div>
      <label>Business<select name="tenantId"><option value="">All businesses</option></select></label>
      <label>Business type<select name="businessType"><option value="">All business types</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label>
      <button class="button button--primary" type="submit">Apply filters</button>
    </form>
    <section class="dashboard-metric-group"><div class="dashboard-metric-group__heading"><div><p class="eyebrow">Platform</p><h2>Platform performance</h2></div><small>Selected reporting period</small></div><div id="admin-platform-metrics" class="metric-grid overview-metrics admin-platform-metrics" aria-live="polite">${metricLabels.map((label) => `<article class="admin-metric-card is-loading"><div><p>${label}</p><span class="metric-icon">•</span></div><strong>—</strong><small>Loading current data</small></article>`).join("")}</div></section>
    <section class="admin-usage-analytics"><div class="admin-section-heading"><div><p class="eyebrow">Usage</p><h2>Business activity</h2></div><span>Attempts are deduplicated by request</span></div><div id="admin-usage-list" class="admin-data-panel" aria-live="polite"><div class="admin-loading-state"><span></span><strong>Loading business analytics</strong></div></div><div id="admin-consumption-history" class="admin-data-panel" hidden></div></section>`;
}

function customerDashboardView() {
  return `<div class="admin-customer-stats" aria-label="Subscription summary">
    ${["Total subscriptions", "Active subscriptions", "Trials", "Payment due", "Try-ons paused", "Cancelled subscriptions", "Expired subscriptions"].map((label, index) => `<article><span>${label}</span><strong data-customer-count="${["total", "active", "trial", "pending_payment", "paused", "cancelled", "expired"][index]}">—</strong></article>`).join("")}
    </div>
    <form id="customer-status-filter" class="admin-customer-filter"><label>Subscription status<select name="status"><option value="">All subscriptions</option><option value="ACTIVE">Active</option><option value="TRIAL">Trial</option><option value="PENDING_PAYMENT">Payment due</option><option value="PAUSED">Paused try-ons</option><option value="CANCELLED">Cancelled</option><option value="EXPIRED">Expired</option></select></label><button class="button button--primary">Apply filter</button></form>
    <div id="admin-customer-list" class="admin-data-panel" aria-live="polite">Loading subscriptions…</div>`;
}

function pricingSettingsView() {
  const businessTypes = '<option value="">All business types</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option>';
  return `<section class="admin-revenue-dashboard"><h2>Platform revenue</h2><form id="admin-revenue-filter" class="admin-filters"><label>From<input name="dateFrom" type="date" required /></label><label>To<input name="dateTo" type="date" required /></label><label>Organization<select name="tenantId"><option value="">All organizations</option></select></label><button class="button button--primary">Apply filters</button></form><div id="admin-revenue-metrics" class="admin-platform-metrics" aria-live="polite">Loading revenue…</div><p class="field-help">Received revenue includes completed payments only. Pending collections are shown separately. Estimated AI cost and margin use the configured cost per generation attempt; actual recorded provider costs are shown independently.</p></section>
  <section class="admin-payment-management"><h2>Billing and payments</h2><div id="admin-payment-summary" class="admin-stat-grid" aria-live="polite"></div><form id="admin-payment-filter" class="admin-filters"><label>Payment status<select name="status"><option value="">All payments</option><option>PAID</option><option>PENDING</option><option>FAILED</option><option>OVERDUE</option></select></label><button class="button button--primary">Apply filter</button></form><div id="admin-payment-list" class="admin-data-panel" aria-live="polite">Loading payments…</div></section>
  <div class="admin-pricing-grid"><form id="pricing-settings-form" class="admin-data-panel"><h2>Platform subscription pricing</h2><label>Plan code<input name="planCode" required maxlength="40" /></label><label>Business type<select name="businessType">${businessTypes}</select></label><label>Monthly fee (INR)<input name="monthlyFee" type="number" min="0" step="0.01" required /></label><label>Tokens per try-on<input name="tryOnCost" type="number" min="1" required /></label><label>Free trial tokens<input name="trialTokens" type="number" min="0" required /></label><label>Trial duration (days)<input name="trialDays" type="number" min="1" max="365" required /></label><label>Payment grace period (days)<input name="graceDays" type="number" min="0" max="90" required /></label><label>GST / tax rate (%)<input name="gst" type="number" min="0" max="100" step="0.01" required /></label><label>Reason for pricing change<input name="reason" required maxlength="500" /></label><button class="button button--primary">Publish pricing</button><p class="form-status" role="status"></p></form>
  <form id="token-package-form" class="admin-data-panel"><h2>Create or replace token package</h2><label>Package code<input name="code" required maxlength="40" /></label><label>Business type<select name="businessType">${businessTypes}</select></label><label>Purchased tokens<input name="purchased" type="number" min="1" required /></label><label>Bonus tokens<input name="promo" type="number" min="0" required /></label><label>Package price (INR)<input name="amount" type="number" min="0.01" step="0.01" required /></label><label>Bulk discount (%)<input name="discount" type="number" min="0" max="100" step="0.01" required /></label><label>GST / tax rate (%)<input name="gst" type="number" min="0" max="100" step="0.01" required /></label><label>Reason for package change<input name="reason" required maxlength="500" /></label><button class="button button--primary">Publish package</button><p class="form-status" role="status"></p></form></div><section class="admin-pricing-current"><h2>Current pricing</h2><div id="admin-pricing-current" class="admin-data-panel">Loading pricing…</div></section>`;
}

function tryOnOperationsView() {
  return `<section><h2>Try-on controls</h2><div id="platform-control-status" class="admin-data-panel" aria-live="polite">Loading platform status…</div><form id="platform-control-form" class="admin-filters"><label>Scope<select name="scope"><option value="PLATFORM">Entire platform</option><option value="BUSINESS_TYPE">Business type</option><option value="ORGANIZATION">One organization</option></select></label><label>Target<select name="scopeKey"><option value="">All</option></select></label><label>Reason<input name="reason" required maxlength="500" /></label><label class="admin-confirm"><input name="confirmed" type="checkbox" required /> I confirm this control change</label><div><button name="action" value="PAUSE" class="button button--danger">Pause try-ons</button><button name="action" value="RESUME" class="button button--quiet">Resume try-ons</button></div><p class="form-status" role="status"></p></form><p class="field-help">Controls affect new try-ons only. Login, payments, history, and existing try-on results remain available.</p></section><form id="tryon-operations-filter" class="admin-dashboard-filters"><label>From<input name="dateFrom" type="date" required /></label><label>To<input name="dateTo" type="date" required /></label><label>Organization<select name="tenantId"><option value="">All organizations</option></select></label><label>Business type<select name="businessType"><option value="">All business types</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label><button class="button button--primary">Apply filters</button></form><div id="tryon-operations-metrics" class="admin-platform-metrics" aria-live="polite">Loading try-on operations…</div><section><h2>Failure reasons</h2><div id="tryon-failure-reasons" class="admin-data-panel"></div></section><section><h2>Request status</h2><p class="field-help">Operational metadata only. Customer images are not loaded or displayed.</p><div id="tryon-operation-list" class="admin-data-panel"></div><div id="tryon-operation-detail" class="admin-data-panel" hidden></div></section>`;
}

function auditHistoryView() {
  return `<form id="admin-audit-filter" class="admin-filters"><label>Search audit history<input name="search" type="search" placeholder="Action, organization, target, or reason" /></label><label>From<input name="dateFrom" type="date" /></label><label>To<input name="dateTo" type="date" /></label><button class="button button--primary">Apply filters</button></form><p class="field-help">Audit records are immutable and cannot be edited or deleted.</p><div id="admin-audit-list" class="admin-data-panel" aria-live="polite">Loading audit history…</div>`;
}

function enquiriesView() {
  return `<div class="admin-stat-grid" aria-label="Enquiry summary">
      <article><span>Total enquiries</span><strong data-enquiry-count="total">—</strong></article>
      <article><span>New enquiries</span><strong data-enquiry-count="submitted">—</strong></article>
      <article><span>In review</span><strong data-enquiry-count="in_review">—</strong></article>
      <article><span>Closed</span><strong data-enquiry-count="closed">—</strong></article>
    </div>
    <form id="admin-enquiry-filter" class="admin-filters" role="search">
      <label>Search enquiries<input name="search" type="search" placeholder="Name, email, mobile, or website" /></label>
      <label>Purpose<select name="purpose"><option value="">All purposes</option><option value="BRAND_TRY_ON">Virtual try-on for a brand</option><option value="RETAIL_PARTNERSHIP">Retail partnership</option><option value="ENTERPRISE_DEMO">Enterprise demo</option><option value="TECHNOLOGY_PARTNERSHIP">Technology partnership</option><option value="PRESS">Press or media</option><option value="OTHER">Something else</option></select></label>
      <label>Status<select name="status"><option value="">All statuses</option><option value="SUBMITTED">New</option><option value="IN_REVIEW">In review</option><option value="CLOSED">Closed</option></select></label>
      <button class="button button--primary" type="submit">Apply filters</button>
    </form>
    <p class="field-help">Contact details contain personal information. Use them only to respond to the submitted business enquiry.</p>
    <div id="admin-enquiry-list" class="admin-data-panel" aria-live="polite">Loading enquiries…</div>`;
}

function sectionContent(active, pathname) {
  if (active.slug === "dashboard") return platformDashboardView();
  if (active.slug === "realtime") return realtimeDashboardView();
  if (active.slug === "ai-models-cost") return aiCostDashboardView();
  if (active.slug === "organizations") return organizationsView(pathname);
  if (active.slug === "enquiries") return enquiriesView();
  if (active.slug === "customers-subscriptions") return customerDashboardView();
  if (active.slug === "billing-pricing") return pricingSettingsView();
  if (active.slug === "platform-operations") return tryOnOperationsView();
  if (active.slug === "audit-history") return auditHistoryView();
  return `<article class="admin-welcome-panel"><h2>${active.slug === "dashboard" ? "Wearo Admin home" : `${active.label} overview`}</h2><p>${active.slug === "dashboard" ? "Choose a section from the navigation to manage the Wearo platform." : "This section is ready for its dedicated administration capabilities."}</p></article>`;
}

function aiCostDashboardView() {
  return `<div class="admin-ai-costs">
    <div id="admin-ai-cost-summary" class="admin-platform-metrics admin-ai-summary">Loading AI cost data…</div>
    <section class="admin-ai-section"><div class="admin-section-heading"><div><h2>Providers</h2><p>Provider accounts and environment-based credentials.</p></div><button class="button button--quiet" type="button" data-open-ai-panel="provider">+ Add provider</button></div><div id="admin-ai-providers" class="admin-data-panel"></div></section>
    <section class="admin-ai-section"><div class="admin-section-heading"><div><h2>Models</h2><p>Compare usage, speed, and cost across configured models.</p></div><button class="button button--primary" type="button" data-open-ai-panel="model">+ Add model</button></div><div id="admin-ai-models" class="admin-data-panel"></div></section>
    <section class="admin-ai-section"><div class="admin-section-heading"><div><h2>Provider purchases</h2><p>Track prepaid balance, credits, tokens, or image packs.</p></div><button class="button button--quiet" type="button" data-open-ai-panel="purchase">+ Record purchase</button></div><div id="admin-ai-purchases" class="admin-data-panel"></div></section>
    <div class="admin-ai-panels">
      <details id="ai-provider-panel" class="admin-ai-panel" hidden><summary><span><strong>Add provider</strong><small>Connect a provider account without storing its secret.</small></span><span aria-hidden="true">＋</span></summary><form id="ai-provider-form" class="admin-ai-form"><label>Provider code<input name="code" required placeholder="OPENAI" /></label><label>Display name<input name="displayName" required placeholder="OpenAI" /></label><label>Adapter type<input name="adapterType" required placeholder="OPENAI" /></label><label>Credential environment variable<input name="credentialEnvName" required placeholder="WEARO_OPENAI_API_KEY" /></label><div class="admin-ai-form__actions"><button class="button button--primary">Save provider</button><p class="form-status"></p></div></form></details>
      <details id="ai-model-panel" class="admin-ai-panel" hidden><summary><span><strong>Configure model</strong><small>Configure routing identity and cost calculation.</small></span><span aria-hidden="true">＋</span></summary><form id="ai-model-form" class="admin-ai-form admin-ai-form--model"><label>Provider<select name="providerId" required></select></label><label>API model ID<input name="apiModelId" required placeholder="gpt-image-2" /></label><label>Display name<input name="displayName" required placeholder="GPT Image 2" /></label><label>Region<input name="region" value="global" required /></label><label>Billing method<select name="billingMethod"><option>TOKEN</option><option>REQUEST</option><option>IMAGE</option><option>CREDIT</option></select></label><label>Input price <small>USD per 1M units</small><input name="inputPrice" type="number" min="0" step="0.000001" value="0" /></label><label>Output price <small>USD per 1M units</small><input name="outputPrice" type="number" min="0" step="0.000001" value="0" /></label><label>Request / image price <small>USD</small><input name="requestPrice" type="number" min="0" step="0.000001" value="0" /></label><label>Fallback cost <small>USD per try-on</small><input name="fallbackCost" type="number" min="0" step="0.000001" value="0" /></label><div class="admin-ai-form__actions"><button class="button button--primary">Save model</button><p class="form-status"></p></div></form></details>
      <details id="ai-purchase-panel" class="admin-ai-panel" hidden><summary><span><strong>Purchase details</strong><small>Add funding at provider level for cost reconciliation.</small></span><span aria-hidden="true">＋</span></summary><form id="ai-purchase-form" class="admin-ai-form"><label>Provider<select name="providerId" required></select></label><label>Amount paid<input name="amount" type="number" min="0.01" step="0.01" required /></label><label>Currency<input name="currency" value="USD" maxlength="3" required /></label><label>Purchased unit<select name="unitType"><option>USD</option><option>TOKEN</option><option>IMAGE</option><option>CREDIT</option></select></label><label>Units purchased<input name="units" type="number" min="0" step="0.000001" placeholder="Optional" /></label><label>Invoice / reference<input name="reference" maxlength="160" placeholder="Optional" /></label><div class="admin-ai-form__actions"><button class="button button--primary">Save purchase</button><p class="form-status"></p></div></form></details>
    </div>
  </div>`;
}

const usdMicros = (value) => `$${(Number(value || 0) / 1000000).toFixed(4)}`;

function modelPricing(model) {
  if (model.billing_method === "TOKEN") return `<span class="admin-model-price"><small>Input</small><strong>$${Number(model.input_unit_price_usd_micros || 0).toFixed(2)} / 1M</strong><small>Output</small><strong>$${Number(model.output_unit_price_usd_micros || 0).toFixed(2)} / 1M</strong>${Number(model.fallback_cost_usd_micros) ? `<small>Fallback</small><strong>${usdMicros(model.fallback_cost_usd_micros)} / try-on</strong>` : ""}</span>`;
  const unit = model.billing_method === "IMAGE" ? "image" : model.billing_method === "CREDIT" ? "credit" : "request";
  return `<span class="admin-model-price"><strong>${usdMicros(model.request_price_usd_micros)} / ${unit}</strong>${Number(model.fallback_cost_usd_micros) ? `<small>Fallback ${usdMicros(model.fallback_cost_usd_micros)} / try-on</small>` : ""}</span>`;
}

async function loadAiCosts(root) {
  const response = await fetch(`${API_ROOT}/admin/ai-costs`, { credentials: "same-origin" });
  if (!response.ok) return;
  const data = await response.json();
  root._aiCostData = data;
  root.querySelectorAll('[data-open-ai-panel="model"], [data-open-ai-panel="purchase"]').forEach((button) => { button.disabled = !data.providers.length; });
  root.querySelectorAll("#ai-model-form select[name=providerId], #ai-purchase-form select[name=providerId]").forEach((select) => { select.innerHTML = data.providers.map((p) => `<option value="${escapeHtml(p.provider_id)}">${escapeHtml(p.display_name)}</option>`).join(""); });
  root.querySelector("#admin-ai-cost-summary").innerHTML = `<article class="admin-metric-card"><span>Providers</span><strong>${data.providers.length}</strong><small>Configured accounts</small></article><article class="admin-metric-card"><span>Models</span><strong>${data.models.length}</strong><small>${data.models.filter((m) => m.status === "ACTIVE").length} active</small></article><article class="admin-metric-card"><span>Total model cost</span><strong>${usdMicros(data.models.reduce((sum, m) => sum + Number(m.total_cost_usd_micros), 0))}</strong><small>Recorded usage</small></article>`;
  root.querySelector("#admin-ai-providers").innerHTML = data.providers.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Provider</th><th>Credential reference</th><th>Purchased</th><th>Used</th><th>Status</th><th>Actions</th></tr></thead><tbody>${data.providers.map((p) => `<tr><td><strong>${escapeHtml(p.display_name)}</strong><br><small>${escapeHtml(p.code)}</small></td><td>${escapeHtml(p.credential_env_name)} <span class="admin-status admin-status--${p.credential_configured ? "active" : "failed"}">${p.credential_configured ? "Configured" : "Missing"}</span></td><td>$${(Number(p.purchased_minor) / 100).toFixed(2)}</td><td>${usdMicros(p.used_usd_micros)}</td><td>${escapeHtml(p.status)}</td><td><div class="admin-ai-row-actions"><button class="admin-history-button" data-ai-edit-provider="${escapeHtml(p.provider_id)}">Edit</button>${aiStatusButtons("providers", p.provider_id, p.status)}<button class="admin-history-button admin-ai-delete" data-ai-delete-provider="${escapeHtml(p.provider_id)}">Delete</button></div></td></tr>`).join("")}</tbody></table></div>` : '<div class="admin-ai-empty"><span>◇</span><div><strong>No providers configured</strong><p>Use “Add provider” above to connect credentials and register models.</p></div></div>';
  root.querySelector("#admin-ai-models").innerHTML = data.models.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Billing</th><th>Pricing</th><th>Try-ons</th><th>Avg time</th><th>Avg cost</th><th>Total cost</th><th>Status</th><th>Actions</th></tr></thead><tbody>${data.models.map((m) => `<tr><td><strong>${escapeHtml(m.display_name)}</strong><br><small>${escapeHtml(m.provider_code)} · ${escapeHtml(m.api_model_id)}</small></td><td>${escapeHtml(m.billing_method)}</td><td>${modelPricing(m)}</td><td>${escapeHtml(m.try_ons)}</td><td>${formatDuration(m.average_generation_time_ms)}</td><td>${usdMicros(m.average_cost_usd_micros)}</td><td>${usdMicros(m.total_cost_usd_micros)}</td><td>${escapeHtml(m.status)}</td><td><div class="admin-ai-row-actions"><button class="admin-history-button" data-ai-edit-model="${escapeHtml(m.model_id)}">Edit</button>${aiStatusButtons("models", m.model_id, m.status)}${Number(m.try_ons) === 0 ? `<button data-ai-delete="${escapeHtml(m.model_id)}" class="admin-history-button admin-ai-delete">Delete</button>` : ""}</div></td></tr>`).join("")}</tbody></table></div>` : '<div class="admin-ai-empty"><span>◎</span><div><strong>No models configured</strong><p>Add a provider first, then use “Add model” above.</p></div></div>';
  root.querySelector("#admin-ai-purchases").innerHTML = data.purchases.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Date</th><th>Provider</th><th>Amount</th><th>Units</th><th>Reference</th></tr></thead><tbody>${data.purchases.map((p) => `<tr><td>${new Date(p.purchased_at).toLocaleDateString()}</td><td>${escapeHtml(p.provider_name)}</td><td>${escapeHtml(p.currency)} ${(Number(p.amount_minor) / 100).toFixed(2)}</td><td>${escapeHtml(p.units_purchased || "—")} ${escapeHtml(p.unit_type)}</td><td>${escapeHtml(p.reference || "—")}</td></tr>`).join("")}</tbody></table></div>` : '<div class="admin-ai-empty"><span>$</span><div><strong>No purchases recorded</strong><p>Use “Record purchase” above when provider funding is added.</p></div></div>';
  attachAiLifecycle(root);
  attachAiPanelButtons(root);
}

function attachAiPanelButtons(root) { root.querySelectorAll("[data-open-ai-panel]").forEach((button) => { if (button.dataset.panelBound) return; button.dataset.panelBound = "true"; button.addEventListener("click", () => { const kind = button.dataset.openAiPanel; const panel = root.querySelector(`#ai-${kind}-panel`); if (!panel) return; const form = panel.querySelector("form"); delete form.dataset.editId; if (form.elements.code) form.elements.code.readOnly = false; form.querySelector("button[type=submit], button:not([type])").textContent = `Save ${kind}`; root.querySelectorAll(".admin-ai-panel").forEach((item) => { item.hidden = item !== panel; item.open = item === panel; }); panel.hidden = false; panel.scrollIntoView({ behavior: "smooth", block: "center" }); panel.querySelector("input, select")?.focus(); }); }); }

function aiStatusButtons(entity, id, status) { return status === "ACTIVE" ? `<button class="admin-history-button" data-ai-status="DISABLED" data-ai-entity="${entity}" data-ai-id="${id}">Disable</button>` : `<button class="admin-history-button" data-ai-status="ACTIVE" data-ai-entity="${entity}" data-ai-id="${id}">Enable</button> <button class="admin-history-button" data-ai-status="ARCHIVED" data-ai-entity="${entity}" data-ai-id="${id}">Archive</button>`; }

function attachAiLifecycle(root) {
  root.querySelectorAll("[data-ai-status]").forEach((button) => button.addEventListener("click", async () => { await fetch(`${API_ROOT}/admin/ai-costs/${button.dataset.aiEntity}/${button.dataset.aiId}/status`, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: button.dataset.aiStatus }) }); loadAiCosts(root); }));
  root.querySelectorAll("[data-ai-delete]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Delete this unused model?")) return; await fetch(`${API_ROOT}/admin/ai-costs/models/${button.dataset.aiDelete}`, { method: "DELETE", credentials: "same-origin" }); loadAiCosts(root); }));
  root.querySelectorAll("[data-ai-delete-provider]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Delete this unused provider?")) return; const response = await fetch(`${API_ROOT}/admin/ai-costs/providers/${button.dataset.aiDeleteProvider}`, { method: "DELETE", credentials: "same-origin" }); if (!response.ok) window.alert("This provider has models or purchases. Archive it instead."); loadAiCosts(root); }));
  root.querySelectorAll("[data-ai-edit-provider]").forEach((button) => button.addEventListener("click", () => editAiProvider(root, button.dataset.aiEditProvider)));
  root.querySelectorAll("[data-ai-edit-model]").forEach((button) => button.addEventListener("click", () => editAiModel(root, button.dataset.aiEditModel)));
}

function editAiProvider(root, id) { const item = root._aiCostData?.providers.find((value) => value.provider_id === id); if (!item) return; root.querySelector('[data-open-ai-panel="provider"]').click(); const form = root.querySelector("#ai-provider-form"); form.dataset.editId = id; form.elements.code.value = item.code; form.elements.code.readOnly = true; form.elements.displayName.value = item.display_name; form.elements.adapterType.value = item.adapter_type; form.elements.credentialEnvName.value = item.credential_env_name; form.querySelector("button").textContent = "Update provider"; }

function editAiModel(root, id) { const item = root._aiCostData?.models.find((value) => value.model_id === id); if (!item) return; root.querySelector('[data-open-ai-panel="model"]').click(); const form = root.querySelector("#ai-model-form"); form.dataset.editId = id; form.elements.providerId.value = item.provider_id; form.elements.apiModelId.value = item.api_model_id; form.elements.displayName.value = item.display_name; form.elements.region.value = item.region; form.elements.billingMethod.value = item.billing_method; form.elements.inputPrice.value = Number(item.input_unit_price_usd_micros); form.elements.outputPrice.value = Number(item.output_unit_price_usd_micros); form.elements.requestPrice.value = Number(item.request_price_usd_micros) / 1000000; form.elements.fallbackCost.value = Number(item.fallback_cost_usd_micros) / 1000000; form.querySelector("button").textContent = "Update model"; }

function attachAiCostDashboard(root) {
  const postForm = (selector, path, payload) => root.querySelector(selector).addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const editId = form.dataset.editId; const target = editId ? `${path}/${editId}` : path; const response = await fetch(`${API_ROOT}${target}`, { method: editId ? "PUT" : "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload(new FormData(form))) }); form.querySelector(".form-status").textContent = response.ok ? "Saved." : "Could not save."; if (response.ok) { delete form.dataset.editId; form.reset(); form.closest("details").hidden = true; loadAiCosts(root); } });
  postForm("#ai-provider-form", "/admin/ai-costs/providers", (d) => ({ code: d.get("code"), display_name: d.get("displayName"), adapter_type: d.get("adapterType"), credential_env_name: d.get("credentialEnvName") }));
  postForm("#ai-model-form", "/admin/ai-costs/models", (d) => ({ provider_id: d.get("providerId"), api_model_id: d.get("apiModelId"), display_name: d.get("displayName"), region: d.get("region"), billing_method: d.get("billingMethod"), input_unit_price_usd_micros: Math.round(Number(d.get("inputPrice")) * 1000000 / 1000000), output_unit_price_usd_micros: Math.round(Number(d.get("outputPrice")) * 1000000 / 1000000), request_price_usd_micros: Math.round(Number(d.get("requestPrice")) * 1000000), fallback_cost_usd_micros: Math.round(Number(d.get("fallbackCost")) * 1000000) }));
  postForm("#ai-purchase-form", "/admin/ai-costs/purchases", (d) => ({ provider_id: d.get("providerId"), amount_minor: Math.round(Number(d.get("amount")) * 100), currency: d.get("currency"), unit_type: d.get("unitType"), units_purchased: d.get("units") ? Number(d.get("units")) : null, reference: d.get("reference") || null }));
  loadAiCosts(root);
}

function realtimeDashboardView() {
  return `<section class="admin-realtime" aria-live="polite">
    <div class="admin-realtime-toolbar"><div><span class="admin-live-badge"><i></i> Live</span><small id="admin-realtime-updated">Connecting…</small></div><label>Window<select id="admin-realtime-window"><option value="15">Last 15 minutes</option><option value="60" selected>Last hour</option><option value="360">Last 6 hours</option><option value="1440">Last 24 hours</option><option value="10080">Last 7 days</option></select></label></div>
    <div id="admin-realtime-metrics" class="admin-platform-metrics"><div class="admin-loading-state"><span></span><strong>Loading live telemetry</strong></div></div>
    <div class="admin-section-heading"><div><p class="eyebrow">Latest activity</p><h2>Try-on generations</h2></div><span>Refreshes every 5 seconds</span></div>
    <div id="admin-realtime-table" class="admin-data-panel"><div class="admin-loading-state"><span></span><strong>Loading generation table</strong></div></div>
  </section>`;
}

function formatDuration(milliseconds) {
  const value = Number(milliseconds || 0);
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
}

async function loadRealtimeDashboard(root) {
  const metrics = root.querySelector("#admin-realtime-metrics");
  const table = root.querySelector("#admin-realtime-table");
  const windowSelect = root.querySelector("#admin-realtime-window");
  if (!metrics || !table || !windowSelect) return;
  const response = await fetch(`${API_ROOT}/admin/realtime?window_minutes=${encodeURIComponent(windowSelect.value)}`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  if (!response.ok) {
    metrics.innerHTML = '<div class="admin-error-state"><strong>Realtime telemetry is unavailable</strong><p>The dashboard will retry automatically.</p></div>';
    return;
  }
  const data = await response.json();
  const summary = data.summary;
  const costNote = data.cost_basis === "ACTUAL" ? "Recorded provider cost" : "Configured estimate; actual cost used when available";
  const cards = [
    ["Try-ons", summary.total_try_ons, `Last ${data.window_minutes} minutes`],
    ["Generating now", Number(summary.queued_try_ons) + Number(summary.processing_try_ons), `${summary.queued_try_ons} queued · ${summary.processing_try_ons} processing`],
    ["Average generation time", formatDuration(summary.average_generation_time_ms), "Completed generations"],
    ["Average cost", usdMicros(summary.average_cost_usd_micros), costNote],
    ["Successful", summary.successful_try_ons, "Delivered generations"],
    ["Failed", summary.failed_try_ons, "Terminal failures"],
    ["Total generation cost", usdMicros(summary.total_cost_usd_micros), costNote],
  ];
  metrics.innerHTML = cards.map(([label, value, note]) => `<article class="admin-metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  root.querySelector("#admin-realtime-updated").textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()} · ${data.cache.toLowerCase()} cache`;
  table.innerHTML = data.try_ons.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Started</th><th>Try-on</th><th>Status</th><th>Generation time</th><th>Cost</th><th>Provider / model</th><th>Failure</th></tr></thead><tbody>${data.try_ons.map((item) => `<tr><td>${escapeHtml(new Date(item.created_at).toLocaleTimeString())}</td><td><small>${escapeHtml(item.job_id)}</small></td><td><span class="admin-status admin-status--${escapeHtml(String(item.status).toLowerCase())}">${escapeHtml(displayEnum(item.status))}</span></td><td>${["PENDING", "PROCESSING"].includes(item.status) ? "In progress" : escapeHtml(formatDuration(item.generation_time_ms))}</td><td>${usdMicros(item.cost_usd_micros)} <small>${escapeHtml(String(item.cost_basis).toLowerCase())}</small></td><td>${escapeHtml(item.provider)}<br><small>${escapeHtml(item.model_version)}</small></td><td>${escapeHtml(item.error_code ? displayEnum(item.error_code) : "—")}</td></tr>`).join("")}</tbody></table></div>` : '<p class="admin-empty">No try-ons in this window.</p>';
}

function attachRealtimeDashboard(root) {
  let timer;
  const refresh = () => loadRealtimeDashboard(root);
  root.querySelector("#admin-realtime-window").addEventListener("change", refresh);
  refresh();
  timer = window.setInterval(() => {
    if (document.body.contains(root.querySelector("#admin-realtime-metrics"))) refresh();
    else window.clearInterval(timer);
  }, 5000);
}

async function loadPricing(root) {
  const panel = root.querySelector("#admin-pricing-current");
  const response = await fetch(`${API_ROOT}/admin/pricing`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  if (!response.ok) return void (panel.textContent = "Pricing could not be loaded.");
  const data = await response.json();
  panel.innerHTML = `<h3>Plans</h3>${data.settings.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Plan</th><th>Business type</th><th>Monthly fee</th><th>Try-on cost</th><th>Trial</th><th>Grace</th><th>GST</th></tr></thead><tbody>${data.settings.map((item) => `<tr><td>${escapeHtml(item.plan_code)}</td><td>${escapeHtml(displayEnum(item.business_type || "All"))}</td><td>₹${(Number(item.monthly_fee_minor) / 100).toFixed(2)}</td><td>${escapeHtml(item.try_on_token_cost)} tokens</td><td>${escapeHtml(item.free_trial_tokens)} tokens / ${escapeHtml(item.trial_duration_days)} days</td><td>${escapeHtml(item.payment_grace_days)} days</td><td>${(Number(item.gst_basis_points) / 100).toFixed(2)}%</td></tr>`).join("")}</tbody></table></div>` : "<p>No platform pricing configured.</p>"}<h3>Token packages</h3>${data.token_packages.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Package</th><th>Business type</th><th>Tokens</th><th>Price</th><th>Discount</th><th>GST</th></tr></thead><tbody>${data.token_packages.map((item) => `<tr><td>${escapeHtml(item.code)}</td><td>${escapeHtml(displayEnum(item.business_type || "All"))}</td><td>${escapeHtml(Number(item.purchased_tokens) + Number(item.promo_tokens))}</td><td>₹${(Number(item.amount_minor) / 100).toFixed(2)}</td><td>${(Number(item.discount_basis_points) / 100).toFixed(2)}%</td><td>${(Number(item.tax_rate_basis_points) / 100).toFixed(2)}%</td></tr>`).join("")}</tbody></table></div>` : "<p>No token packages configured.</p>"}`;
}

function attachPricingControls(root) {
  const revenueForm = root.querySelector("#admin-revenue-filter");
  const revenueFrom = new Date(); revenueFrom.setDate(1);
  revenueForm.elements.dateFrom.value = isoDate(revenueFrom);
  revenueForm.elements.dateTo.value = isoDate(new Date());
  const loadRevenue = async () => {
    const metrics = root.querySelector("#admin-revenue-metrics");
    const parameters = new URLSearchParams({ date_from: revenueForm.elements.dateFrom.value, date_to: revenueForm.elements.dateTo.value });
    if (revenueForm.elements.tenantId.value) parameters.set("tenant_id", revenueForm.elements.tenantId.value);
    const response = await fetch(`${API_ROOT}/admin/revenue?${parameters}`, { credentials: "same-origin" });
    if (response.status === 401) return redirect("/admin");
    if (!response.ok) return void (metrics.textContent = "Revenue metrics could not be loaded.");
    const value = await response.json();
    const money = (minor) => `₹${(Number(minor) / 100).toFixed(2)}`;
    const cards = [["Total received revenue", money(value.total_revenue_minor)], ["Monthly subscription revenue", money(value.monthly_subscription_revenue_minor)], ["Token purchase revenue", money(value.token_purchase_revenue_minor)], ["Pending collections (not received)", money(value.pending_collections_minor)], ["Estimated AI generation cost", money(value.estimated_ai_generation_cost_minor)], ["Actual recorded AI cost", money(value.actual_recorded_ai_cost_minor)], ["Estimated gross margin", `${money(value.estimated_gross_margin_minor)} (${value.estimated_gross_margin_percent}%)`]];
    metrics.innerHTML = cards.map(([label, amount]) => `<article><span>${label}</span><strong>${escapeHtml(amount)}</strong></article>`).join("");
  };
  fetch(`${API_ROOT}/admin/organizations`, { credentials: "same-origin" }).then((response) => response.ok ? response.json() : null).then((data) => { if (data) revenueForm.elements.tenantId.insertAdjacentHTML("beforeend", data.organizations.map((organization) => `<option value="${escapeHtml(organization.tenant_id)}">${escapeHtml(organization.organization_name)}</option>`).join("")); });
  revenueForm.addEventListener("submit", (event) => { event.preventDefault(); loadRevenue(); });
  const loadPayments = async (status = "") => {
    const list = root.querySelector("#admin-payment-list");
    const response = await fetch(`${API_ROOT}/admin/billing${status ? `?status=${encodeURIComponent(status)}` : ""}`, { credentials: "same-origin" });
    if (response.status === 401) return redirect("/admin");
    if (!response.ok) return void (list.textContent = "Payments could not be loaded.");
    const data = await response.json();
    root.querySelector("#admin-payment-summary").innerHTML = `<article><span>Transactions</span><strong>${data.summary.transactions}</strong></article><article><span>Outstanding payments</span><strong>${data.summary.outstanding}</strong></article><article><span>Overdue payments</span><strong>${data.summary.overdue}</strong></article><article><span>Outstanding value</span><strong>₹${(Number(data.summary.outstanding_minor) / 100).toFixed(2)}</strong></article>`;
    list.innerHTML = data.items.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Organization</th><th>Status</th><th>Invoice / payment</th><th>Subtotal</th><th>Tax</th><th>Total payable</th><th>Payment date</th><th>Billing details</th></tr></thead><tbody>${data.items.map((item) => `<tr><td>${escapeHtml(item.organization_name)}</td><td><span class="admin-status">${escapeHtml(displayEnum(item.payment_status))}</span></td><td>${item.invoice_id ? `<a href="${API_ROOT}/admin/billing/invoices/${encodeURIComponent(item.invoice_id)}.txt">${escapeHtml(item.invoice_number)}</a>` : escapeHtml(item.provider_payment_id || "Awaiting payment")}</td><td>₹${(Number(item.subtotal_minor ?? item.amount_minor) / 100).toFixed(2)}</td><td>₹${(Number(item.tax_minor || 0) / 100).toFixed(2)}</td><td>₹${(Number(item.total_payable_minor) / 100).toFixed(2)}</td><td>${item.payment_date ? escapeHtml(new Date(item.payment_date).toLocaleDateString()) : "—"}</td><td>${escapeHtml(item.legal_name)}<br>${escapeHtml(item.billing_email)}<br>GSTIN: ${escapeHtml(item.gstin || "Not provided")}</td></tr>`).join("")}</tbody></table></div>` : '<p class="admin-empty">No payments match this status.</p>';
  };
  const paymentFilter = root.querySelector("#admin-payment-filter");
  paymentFilter?.addEventListener("submit", (event) => { event.preventDefault(); loadPayments(new FormData(paymentFilter).get("status")); });
  const postPricing = async (form, path, body) => {
    const status = form.querySelector(".form-status");
    const response = await fetch(`${API_ROOT}/admin/pricing/${path}`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const result = await response.json();
    status.textContent = response.ok ? "Pricing published. Existing transactions were not changed." : result.message || "Pricing update failed.";
    if (response.ok) { form.reset(); loadPricing(root); }
  };
  const settings = root.querySelector("#pricing-settings-form");
  settings?.addEventListener("submit", (event) => { event.preventDefault(); const data = new FormData(settings); postPricing(settings, "settings", { plan_code: data.get("planCode"), business_type: data.get("businessType") || null, monthly_fee_minor: Math.round(Number(data.get("monthlyFee")) * 100), try_on_token_cost: Number(data.get("tryOnCost")), free_trial_tokens: Number(data.get("trialTokens")), trial_duration_days: Number(data.get("trialDays")), payment_grace_days: Number(data.get("graceDays")), gst_basis_points: Math.round(Number(data.get("gst")) * 100), reason: data.get("reason") }); });
  const packages = root.querySelector("#token-package-form");
  packages?.addEventListener("submit", (event) => { event.preventDefault(); const data = new FormData(packages); postPricing(packages, "token-packages", { code: data.get("code"), business_type: data.get("businessType") || null, purchased_tokens: Number(data.get("purchased")), promo_tokens: Number(data.get("promo")), amount_minor: Math.round(Number(data.get("amount")) * 100), discount_basis_points: Math.round(Number(data.get("discount")) * 100), gst_basis_points: Math.round(Number(data.get("gst")) * 100), reason: data.get("reason") }); });
  loadPricing(root);
  loadPayments();
  loadRevenue();
}

async function attachTryOnOperations(root) {
  const form = root.querySelector("#tryon-operations-filter");
  const from = new Date(); from.setDate(from.getDate() - 6);
  form.elements.dateFrom.value = isoDate(from);
  form.elements.dateTo.value = isoDate(new Date());
  const organizations = await fetch(`${API_ROOT}/admin/organizations`, { credentials: "same-origin" });
  if (organizations.ok) {
    const data = await organizations.json();
    form.elements.tenantId.insertAdjacentHTML("beforeend", data.organizations.map((item) => `<option value="${escapeHtml(item.tenant_id)}">${escapeHtml(item.organization_name)}</option>`).join(""));
    root.dataset.organizations = JSON.stringify(data.organizations);
  }
  const controlForm = root.querySelector("#platform-control-form");
  const setControlTargets = () => {
    const scope = controlForm.elements.scope.value;
    const targets = controlForm.elements.scopeKey;
    if (scope === "PLATFORM") targets.innerHTML = '<option value="">Entire platform</option>';
    else if (scope === "BUSINESS_TYPE") targets.innerHTML = '<option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option>';
    else targets.innerHTML = JSON.parse(root.dataset.organizations || "[]").map((item) => `<option value="${escapeHtml(item.tenant_id)}">${escapeHtml(item.organization_name)}</option>`).join("");
  };
  const loadControls = async () => {
    const response = await fetch(`${API_ROOT}/admin/operations/controls`, { credentials: "same-origin" });
    if (!response.ok) return;
    const data = await response.json();
    root.querySelector("#platform-control-status").innerHTML = `<strong>Platform try-ons: ${data.platform.operational ? "Operational" : "Paused"}</strong>${data.platform.reason ? `<p>Latest reason: ${escapeHtml(data.platform.reason)}</p>` : ""}<p>Paused business types: ${escapeHtml(data.business_types.filter((item) => item.paused).map((item) => displayEnum(item.business_type)).join(", ") || "None")}</p>`;
  };
  controlForm.elements.scope.addEventListener("change", setControlTargets); setControlTargets();
  controlForm.addEventListener("submit", async (event) => {
    event.preventDefault(); const action = event.submitter.value; const values = new FormData(controlForm);
    if (!window.confirm(`${action === "PAUSE" ? "Pause" : "Resume"} try-ons for this scope?`)) return;
    const response = await fetch(`${API_ROOT}/admin/operations/controls`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope: values.get("scope"), scope_key: values.get("scopeKey") || null, action, reason: values.get("reason"), confirmed: values.get("confirmed") === "on" }) });
    const result = await response.json(); const status = controlForm.querySelector(".form-status");
    status.textContent = response.ok ? `Try-ons are now ${result.operational ? "operational" : "paused"} for this scope. Change audited.` : result.message || "Control change failed.";
    if (response.ok) { controlForm.elements.reason.value = ""; controlForm.elements.confirmed.checked = false; loadControls(); }
  });
  const load = async () => {
    const parameters = new URLSearchParams({ date_from: form.elements.dateFrom.value, date_to: form.elements.dateTo.value });
    if (form.elements.tenantId.value) parameters.set("tenant_id", form.elements.tenantId.value);
    if (form.elements.businessType.value) parameters.set("business_type", form.elements.businessType.value);
    const response = await fetch(`${API_ROOT}/admin/operations/try-ons?${parameters}`, { credentials: "same-origin" });
    if (response.status === 401) return redirect("/admin");
    const list = root.querySelector("#tryon-operation-list");
    if (!response.ok) return void (list.textContent = "Try-on operations could not be loaded.");
    const data = await response.json();
    const summary = data.summary;
    root.querySelector("#tryon-operations-metrics").innerHTML = [["Total requests", summary.total_requests], ["Successful", summary.successful_requests], ["Failed", summary.failed_requests], ["Success rate", `${summary.success_rate}%`], ["Average processing time", `${(summary.average_processing_time_ms / 1000).toFixed(2)}s`]].map(([label, value]) => `<article><span>${label}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
    root.querySelector("#tryon-failure-reasons").innerHTML = data.failure_reasons.length ? `<ul>${data.failure_reasons.map((item) => `<li><strong>${escapeHtml(displayEnum(item.reason))}</strong>: ${escapeHtml(item.count)}</li>`).join("")}</ul>` : "<p>No failures in this period.</p>";
    list.innerHTML = data.requests.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Request</th><th>Organization</th><th>Status</th><th>Processing time</th><th>Failure reason</th><th>Provider / model</th><th></th></tr></thead><tbody>${data.requests.map((item) => `<tr><td>${escapeHtml(item.job_id)}</td><td>${escapeHtml(item.organization_name)}</td><td>${escapeHtml(displayEnum(item.status))}</td><td>${item.processing_time_ms == null ? "In progress" : `${(Number(item.processing_time_ms) / 1000).toFixed(2)}s`}</td><td>${escapeHtml(item.error_code ? displayEnum(item.error_code) : "—")}</td><td>${escapeHtml(item.provider || "Not recorded")}<br>${escapeHtml(item.model_version || "Not recorded")}</td><td><button class="admin-history-button" data-operation-id="${escapeHtml(item.job_id)}">Inspect</button></td></tr>`).join("")}</tbody></table></div>` : "<p>No try-on requests match these filters.</p>";
    list.querySelectorAll("[data-operation-id]").forEach((button) => button.addEventListener("click", async () => {
      const detail = root.querySelector("#tryon-operation-detail"); detail.hidden = false; detail.textContent = "Loading request status…";
      const result = await fetch(`${API_ROOT}/admin/operations/try-ons/${encodeURIComponent(button.dataset.operationId)}`, { credentials: "same-origin" });
      if (!result.ok) return void (detail.textContent = "Request status could not be loaded.");
      const item = await result.json();
      detail.innerHTML = `<h3>Request ${escapeHtml(item.job_id)}</h3><p><strong>Status:</strong> ${escapeHtml(displayEnum(item.status))}</p><p><strong>Organization:</strong> ${escapeHtml(item.organization_name)}</p><p><strong>Provider/model:</strong> ${escapeHtml(item.provider || "Not recorded")} / ${escapeHtml(item.model_version || "Not recorded")}</p><p><strong>Failure reason:</strong> ${escapeHtml(item.error_code ? displayEnum(item.error_code) : "None")}</p><p><strong>Attempts:</strong> ${escapeHtml(item.attempts.length)}</p><p class="field-help">No customer images are exposed by this inspection endpoint.</p>`;
    }));
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
  load();
  loadControls();
}

function attachAuditHistory(root) {
  const form = root.querySelector("#admin-audit-filter");
  const load = async () => {
    const parameters = new URLSearchParams();
    for (const [field, parameter] of [["search", "search"], ["dateFrom", "date_from"], ["dateTo", "date_to"]]) if (form.elements[field].value) parameters.set(parameter, form.elements[field].value);
    const list = root.querySelector("#admin-audit-list"); list.textContent = "Loading audit history…";
    const response = await fetch(`${API_ROOT}/admin/audit-history?${parameters}`, { credentials: "same-origin" });
    if (response.status === 401) return redirect("/admin");
    if (!response.ok) return void (list.textContent = "Audit history could not be loaded.");
    const data = await response.json();
    list.innerHTML = data.events.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Organization / target</th><th>Change</th><th>Reason</th></tr></thead><tbody>${data.events.map((event) => `<tr><td>${escapeHtml(new Date(event.occurred_at).toLocaleString())}</td><td>${escapeHtml(event.actor_name)}<br><small>${escapeHtml(event.actor_id || event.actor_type)}</small></td><td>${escapeHtml(displayEnum(event.action))}</td><td>${escapeHtml(event.organization_name || displayEnum(event.target_type))}<br><small>${escapeHtml(event.target_id || "Platform")}</small></td><td><details><summary>View change</summary><strong>Before</strong><pre>${escapeHtml(JSON.stringify(event.before_summary ?? {}, null, 2))}</pre><strong>After</strong><pre>${escapeHtml(JSON.stringify(event.after_summary ?? {}, null, 2))}</pre></details></td><td>${escapeHtml(event.reason || "Not applicable")}</td></tr>`).join("")}</tbody></table></div>` : "<p>No audit events match these filters.</p>";
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
  load();
}

function attachEnquiries(root) {
  const form = root.querySelector("#admin-enquiry-filter");
  const load = async () => {
    const parameters = new URLSearchParams();
    for (const field of ["search", "purpose", "status"]) {
      if (form.elements[field].value) parameters.set(field, form.elements[field].value);
    }
    const list = root.querySelector("#admin-enquiry-list");
    list.textContent = "Loading enquiries…";
    const response = await fetch(`${API_ROOT}/admin/enquiries?${parameters}`, { credentials: "same-origin" });
    if (response.status === 401) return redirect("/admin");
    if (!response.ok) return void (list.textContent = "Enquiries could not be loaded.");
    const data = await response.json();
    Object.entries(data.summary).forEach(([key, value]) => {
      const count = root.querySelector(`[data-enquiry-count="${key}"]`);
      if (count) count.textContent = value;
    });
    list.innerHTML = data.enquiries.length ? `<div class="admin-table-wrap"><table class="admin-table admin-enquiry-table"><thead><tr><th>Received</th><th>Business contact</th><th>Contact details</th><th>Website</th><th>Purpose</th><th>Status</th></tr></thead><tbody>${data.enquiries.map((item) => `<tr><td>${escapeHtml(new Date(item.created_at).toLocaleString())}</td><td><strong>${escapeHtml(item.name)}</strong><br><small>${escapeHtml(item.contact_enquiry_id)}</small></td><td><a href="mailto:${encodeURIComponent(item.email)}">${escapeHtml(item.email)}</a><br><a href="tel:${escapeHtml(item.mobile.replace(/[^0-9+]/g, ""))}">${escapeHtml(item.mobile)}</a></td><td>${item.website_url ? `<a href="${escapeHtml(item.website_url)}" target="_blank" rel="noopener noreferrer">Visit website ↗</a>` : "—"}</td><td>${escapeHtml(displayEnum(item.purpose))}</td><td><span class="admin-status admin-status--${escapeHtml(item.status.toLowerCase())}">${escapeHtml(item.status === "SUBMITTED" ? "New" : displayEnum(item.status))}</span></td></tr>`).join("")}</tbody></table></div>` : "<p>No enquiries match these filters.</p>";
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
  load();
}

async function loadCustomerDashboard(root, status = "") {
  const list = root.querySelector("#admin-customer-list");
  if (!list) return;
  list.textContent = "Loading subscriptions…";
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await fetch(`${API_ROOT}/admin/customers${query}`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  if (!response.ok) return void (list.textContent = "Subscriptions could not be loaded.");
  const data = await response.json();
  Object.entries(data.summary).forEach(([key, value]) => {
    const count = root.querySelector(`[data-customer-count="${key}"]`);
    if (count) count.textContent = value;
  });
  if (!data.customers.length) return void (list.textContent = "No subscriptions match this status.");
  list.innerHTML = `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Business customer</th><th>Business type</th><th>Plan</th><th>Status</th><th></th></tr></thead><tbody>${data.customers.map((customer) => `<tr><td><strong>${escapeHtml(customer.customer_name)}</strong></td><td>${escapeHtml(displayEnum(customer.business_type))}</td><td>${escapeHtml(customer.plan_code || "Unassigned")}</td><td><div class="admin-status-stack">${customer.statuses.length ? customer.statuses.map((item) => `<span class="admin-status admin-status--${escapeHtml(item.toLowerCase())}">${escapeHtml(displayEnum(item))}</span>`).join("") : '<span class="admin-status">Unassigned</span>'}</div></td><td><a href="/admin/organizations/${escapeHtml(customer.tenant_id)}" data-customer-link>Open details</a></td></tr>`).join("")}</tbody></table></div>`;
  list.querySelectorAll("[data-customer-link]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    const target = link.getAttribute("href");
    window.history.pushState({}, "", target);
    renderAuthenticatedSection(root, target);
  }));
}

function attachCustomerControls(root) {
  const form = root.querySelector("#customer-status-filter");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadCustomerDashboard(root, new FormData(form).get("status"));
  });
  loadCustomerDashboard(root);
}

function isoDate(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function dashboardDateRange(period, form) {
  const today = new Date();
  const from = new Date(today);
  if (period === "week") from.setDate(today.getDate() - 6);
  if (period === "month") from.setDate(1);
  if (period === "custom") return { from: form.elements.dateFrom.value, to: form.elements.dateTo.value };
  return { from: isoDate(from), to: isoDate(today) };
}

async function loadPlatformDashboard(root) {
  const form = root.querySelector("#admin-dashboard-filters");
  const metrics = root.querySelector("#admin-platform-metrics");
  if (!form || !metrics) return;
  const period = new FormData(form).get("period");
  const range = dashboardDateRange(period, form);
  if (!range.from || !range.to) {
    metrics.textContent = "Choose both custom dates.";
    return;
  }
  const parameters = new URLSearchParams({ date_from: range.from, date_to: range.to });
  if (form.elements.tenantId.value) parameters.set("tenant_id", form.elements.tenantId.value);
  if (form.elements.businessType.value) parameters.set("business_type", form.elements.businessType.value);
  metrics.textContent = "Loading platform usage…";
  const response = await fetch(`${API_ROOT}/admin/dashboard?${parameters}`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  if (!response.ok) {
    metrics.innerHTML = '<div class="admin-error-state"><strong>Platform metrics are unavailable</strong><p>Check that the API is running and database migrations are applied.</p><button class="button button--quiet" type="button">Try again</button></div>';
    metrics.querySelector("button").addEventListener("click", () => loadPlatformDashboard(root));
    loadUsageAnalytics(root, parameters);
    return;
  }
  const values = await response.json();
  const cards = [
    ["Total businesses", values.total_organizations], ["Active businesses", values.active_organizations],
    ["Total registered consumers", values.total_registered_consumers], ["Total try-ons", values.total_try_ons],
    ["Successful try-ons", values.successful_try_ons], ["Failed try-ons", values.failed_try_ons],
    ["Total tokens consumed", values.total_tokens_consumed], ["Average try-ons per business", values.average_try_ons_per_organization],
  ];
  metrics.innerHTML = cards.map(([label, value], index) => `<article class="admin-metric-card"><span>${label}</span><strong>${escapeHtml(value)}</strong><small>${index < 2 ? "Current platform state" : "Selected date range"}</small></article>`).join("");
  loadUsageAnalytics(root, parameters);
}

async function loadUsageAnalytics(root, dashboardParameters) {
  const list = root.querySelector("#admin-usage-list");
  if (!list) return;
  const parameters = new URLSearchParams({ date_from: dashboardParameters.get("date_from"), date_to: dashboardParameters.get("date_to") });
  if (dashboardParameters.get("business_type")) parameters.set("business_type", dashboardParameters.get("business_type"));
  if (dashboardParameters.get("tenant_id")) parameters.set("tenant_id", dashboardParameters.get("tenant_id"));
  const response = await fetch(`${API_ROOT}/admin/usage/organizations?${parameters}`, { credentials: "same-origin" });
  if (!response.ok) return void (list.innerHTML = '<div class="admin-error-state admin-error-state--compact"><strong>Business analytics are unavailable</strong><p>The rest of the admin app remains available.</p></div>');
  const data = await response.json();
  const organizations = data.organizations;
  if (!organizations.length) return void (list.textContent = "No business usage is available for this period.");
  const mostActive = new Set(data.most_active.map((item) => item.tenant_id));
  list.innerHTML = `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Organization</th><th>Try-ons</th><th>Successful</th><th>Failed</th><th>Purchased</th><th>Consumed</th><th>Adjusted</th><th>Remaining</th><th></th></tr></thead><tbody>${organizations.map((item) => `<tr><td><strong>${escapeHtml(item.organization_name)}</strong>${mostActive.has(item.tenant_id) ? '<small class="admin-active-label">Most active</small>' : ""}</td><td>${escapeHtml(item.total_try_ons)}</td><td>${escapeHtml(item.successful_try_ons)}</td><td>${escapeHtml(item.failed_try_ons)}</td><td>${escapeHtml(item.tokens_purchased)}</td><td>${escapeHtml(item.tokens_consumed)}</td><td>${escapeHtml(item.manually_adjusted)}</td><td>${escapeHtml(item.remaining_tokens)}</td><td><button class="admin-history-button" data-usage-tenant="${escapeHtml(item.tenant_id)}" data-usage-name="${escapeHtml(item.organization_name)}">History</button></td></tr>`).join("")}</tbody></table></div>`;
  list.querySelectorAll("[data-usage-tenant]").forEach((button) => button.addEventListener("click", async () => {
    const history = root.querySelector("#admin-consumption-history");
    history.hidden = false;
    history.textContent = "Loading consumption history…";
    const historyResponse = await fetch(`${API_ROOT}/admin/usage/organizations/${encodeURIComponent(button.dataset.usageTenant)}?${parameters}`, { credentials: "same-origin" });
    if (!historyResponse.ok) return void (history.textContent = "Consumption history could not be loaded.");
    const result = await historyResponse.json();
    history.innerHTML = `<h3>${escapeHtml(button.dataset.usageName)} consumption history</h3>${result.items.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Request</th><th>Date</th><th>Outcome</th><th>Tokens consumed</th></tr></thead><tbody>${result.items.map((item) => `<tr><td>${escapeHtml(item.request_key)}</td><td>${escapeHtml(new Date(item.created_at).toLocaleString())}</td><td>${escapeHtml(displayEnum(item.status))}</td><td>${escapeHtml(item.tokens_consumed)}</td></tr>`).join("")}</tbody></table></div>` : "<p>No try-on attempts in this period.</p>"}`;
  }));
}

async function attachDashboardControls(root) {
  const form = root.querySelector("#admin-dashboard-filters");
  if (!form) return;
  const organizationResponse = await fetch(`${API_ROOT}/admin/organizations`, { credentials: "same-origin" });
  if (organizationResponse.ok) {
    const data = await organizationResponse.json();
    form.elements.tenantId.insertAdjacentHTML("beforeend", data.organizations.map((organization) => `<option value="${escapeHtml(organization.tenant_id)}">${escapeHtml(organization.organization_name)}</option>`).join(""));
  }
  form.addEventListener("change", (event) => {
    if (event.target.name === "period") root.querySelector("#admin-custom-dates").hidden = event.target.value !== "custom";
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); loadPlatformDashboard(root); });
  loadPlatformDashboard(root);
}

function adminHomeView(pathname) {
  const active = adminSection(pathname);
  const navigation = ADMIN_SECTIONS.map((section) => `<a href="/admin/${section.slug}" ${section.slug === active.slug ? 'aria-current="page"' : ""}><span aria-hidden="true">${section.icon}</span><span>${section.label}</span></a>`).join("");
  return `<div class="business-app admin-app">
    <aside class="business-sidebar admin-sidebar">
      <div class="business-sidebar__brand admin-sidebar__brand"><a href="/admin/dashboard"><img src="/wearo-brand.png" alt="Wearo.ai" /></a><span>Admin</span></div>
      <div class="workspace-switcher"><span class="workspace-switcher__mark">WA</span><span><small>Workspace</small><strong>Wearo Platform</strong></span><span aria-hidden="true">⌄</span></div>
      <p class="business-sidebar__label">Manage</p>
      <nav class="business-nav admin-navigation" aria-label="Admin sections">${navigation}</nav>
      <div class="business-sidebar__footer"><div class="admin-sidebar-user"><span>SA</span><div><strong>Wearo Super Admin</strong><small>Platform administrator</small></div></div></div>
    </aside>
    <div class="business-workspace admin-workspace">
      <header class="business-topbar"><div class="business-breadcrumb"><strong>Platform workspace</strong><span>/</span><span>${active.label}</span></div><div class="business-topbar__actions"><span class="environment-badge"><span class="availability-dot" aria-hidden="true"></span>Operational</span><div class="business-user" aria-label="Current user"><span>SA</span><div><strong>Super Admin</strong><small>Platform administrator</small></div></div><button id="admin-logout" class="button button--quiet admin-topbar-logout" type="button">Sign out</button></div></header>
      <main id="main" class="business-main admin-dashboard" aria-labelledby="admin-page-title">
        <div class="page-heading"><div><p class="eyebrow">Platform administration</p><h1 id="admin-page-title">${active.label}</h1><p class="admin-page-description">${active.description}</p></div></div>
        ${sectionContent(active, pathname)}
      </main>
      <footer class="business-footer">Wearo Platform Administration · Secure internal workspace</footer>
    </div>
  </div>`;
}

async function hasAdminSession() {
  const response = await fetch(`${API_ROOT}/admin/session`, { credentials: "same-origin" });
  return response.ok;
}

function redirect(path) {
  window.location.replace(path);
}

function attachLogin(root) {
  root.querySelector("#admin-login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const error = root.querySelector("#admin-login-error");
    const submit = form.querySelector("button[type=submit]");
    error.textContent = "";
    submit.disabled = true;
    try {
      const data = new FormData(form);
      const response = await fetch(`${API_ROOT}/admin/login`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
      });
      if (!response.ok) throw new Error("login rejected");
      const result = await response.json();
      redirect(result.redirect_to);
    } catch {
      error.textContent = "Invalid email or password.";
      submit.disabled = false;
    }
  });
}

async function loadOrganizations(root, query = "") {
  const list = root.querySelector("#organization-list");
  if (!list) return;
  list.textContent = "Loading businesses…";
  const response = await fetch(`${API_ROOT}/admin/organizations${query}`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  if (!response.ok) {
    list.textContent = "Businesses could not be loaded.";
    return;
  }
  const result = await response.json();
  root.querySelector("#organization-total").textContent = result.summary.total;
  root.querySelector("#organization-active").textContent = result.summary.active;
  root.querySelector("#organization-paused").textContent = result.summary.paused;
  if (!result.organizations.length) {
    list.innerHTML = '<p class="admin-empty">No businesses match these filters.</p>';
    return;
  }
  list.innerHTML = `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Organization</th><th>Business type</th><th>Onboarded</th><th>Subscription</th><th>Operational status</th><th><span class="sr-only">Action</span></th></tr></thead><tbody>${result.organizations.map((organization) => `<tr><td><strong>${escapeHtml(organization.organization_name)}</strong></td><td>${escapeHtml(displayEnum(organization.business_type))}</td><td>${escapeHtml(new Date(organization.onboarding_date).toLocaleDateString())}</td><td><span class="admin-status">${escapeHtml(displayEnum(organization.subscription_status))}</span></td><td><span class="admin-status admin-status--${escapeHtml(String(organization.operational_status).toLowerCase())}">${escapeHtml(displayEnum(organization.operational_status))}</span></td><td><a href="/admin/organizations/${escapeHtml(organization.tenant_id)}" data-organization-link>View</a></td></tr>`).join("")}</tbody></table></div>`;
  list.querySelectorAll("[data-organization-link]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    const target = link.getAttribute("href");
    window.history.pushState({}, "", target);
    renderAuthenticatedSection(root, target);
  }));
}

async function loadOrganizationDetail(root) {
  const panel = root.querySelector("#admin-organization-detail");
  if (!panel) return;
  const response = await fetch(`${API_ROOT}/admin/organizations/${encodeURIComponent(panel.dataset.tenantId)}`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  if (!response.ok) {
    panel.textContent = "Business details could not be loaded.";
    return;
  }
  const organization = await response.json();
  const subscriptionResponse = await fetch(`${API_ROOT}/admin/subscriptions/${encodeURIComponent(panel.dataset.tenantId)}`, { credentials: "same-origin" });
  const subscription = subscriptionResponse.ok ? await subscriptionResponse.json() : null;
  const payments = organization.payment_history.length
    ? organization.payment_history.map((payment) => `<tr><td>${escapeHtml(payment.receipt_number)}</td><td>${escapeHtml(new Date(payment.issued_at).toLocaleDateString())}</td><td>${escapeHtml(payment.currency)} ${(Number(payment.amount_minor) / 100).toFixed(2)}</td><td>${escapeHtml(payment.tokens_credited)}</td></tr>`).join("")
    : '<tr><td colspan="4">No payments recorded.</td></tr>';
  panel.innerHTML = `<a class="admin-back-link" href="/admin/organizations">← All businesses</a><h2>${escapeHtml(organization.organization_name)}</h2>
    <div class="admin-stat-grid"><article><span>Available tokens</span><strong id="detail-token-balance">${escapeHtml(organization.available_tokens)}</strong></article><article><span>Tokens consumed</span><strong>${escapeHtml(organization.tokens_consumed)}</strong></article><article><span>Total try-ons</span><strong>${escapeHtml(organization.total_try_ons)}</strong></article></div>
    <dl class="admin-detail-grid"><div><dt>Business type</dt><dd>${escapeHtml(displayEnum(organization.business_type))}</dd></div><div><dt>Onboarding date</dt><dd>${escapeHtml(new Date(organization.onboarding_date).toLocaleDateString())}</dd></div><div><dt>Subscription plan</dt><dd>${escapeHtml(organization.plan_code || "Unassigned")}</dd></div><div><dt>Subscription status</dt><dd>${escapeHtml(displayEnum(organization.subscription_status))}</dd></div><div><dt>Operational status</dt><dd id="detail-operational-status">${escapeHtml(displayEnum(organization.operational_status))}</dd></div><div><dt>Billing status</dt><dd>${escapeHtml(displayEnum(organization.billing_status))}</dd></div><div><dt>Legal name</dt><dd>${escapeHtml(organization.legal_name)}</dd></div><div><dt>Jurisdiction</dt><dd>${escapeHtml(organization.jurisdiction)}</dd></div><div><dt>Billing email</dt><dd>${escapeHtml(organization.billing_email)}</dd></div><div><dt>Billing phone</dt><dd>${escapeHtml(organization.billing_phone || "Not provided")}</dd></div><div><dt>Website</dt><dd>${escapeHtml(organization.website_url || "Not provided")}</dd></div></dl>
    ${subscription ? `<section class="admin-subscription-panel"><h3>Subscription lifecycle</h3><dl class="admin-detail-grid"><div><dt>State</dt><dd id="subscription-state">${escapeHtml(displayEnum(subscription.state))}</dd></div><div><dt>Plan</dt><dd id="subscription-plan">${escapeHtml(subscription.plan_code)}</dd></div><div><dt>Start date</dt><dd>${escapeHtml(new Date(subscription.started_at).toLocaleDateString())}</dd></div><div><dt>Next billing date</dt><dd id="subscription-next-billing">${subscription.next_billing_at ? escapeHtml(new Date(subscription.next_billing_at).toLocaleDateString()) : "Not scheduled"}</dd></div><div><dt>Trial ends</dt><dd id="subscription-trial-end">${subscription.trial_ends_at ? escapeHtml(new Date(subscription.trial_ends_at).toLocaleDateString()) : "Not applicable"}</dd></div><div><dt>Admin operational state</dt><dd>${escapeHtml(displayEnum(organization.operational_status))}</dd></div></dl>
    <form id="subscription-transition-form"><label>Reason<input name="reason" required maxlength="500" /></label><div class="admin-action-row"><button name="action" value="START_TRIAL" class="button button--quiet">Start trial</button><button name="action" value="ACTIVATE" class="button button--quiet">Activate / Reactivate</button><button name="action" value="MARK_PAYMENT_DUE" class="button button--quiet">Mark payment due</button><button name="action" value="PAUSE" class="button button--quiet">Customer pause</button><button name="action" value="CANCEL" class="button button--danger">Cancel</button><button name="action" value="EXPIRE" class="button button--quiet">Expire</button></div><p class="form-status" role="status"></p></form>
    <div class="admin-control-grid"><form id="subscription-plan-form"><h3>Assign or change plan</h3><label>Plan code<input name="planCode" value="${escapeHtml(subscription.plan_code)}" required maxlength="40" /></label><label>Next billing date<input name="nextBilling" type="datetime-local" /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Save plan</button><p class="form-status" role="status"></p></form><form id="trial-extension-form"><h3>Extend trial</h3><label>Additional days<input name="days" type="number" min="1" max="365" required /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Extend trial</button><p class="form-status" role="status"></p></form></div></section>` : ""}
    <section class="admin-control-grid"><form id="organization-status-control"><h3>Admin operational controls</h3><p class="field-help">This pause is independent from a customer-paused subscription.</p><label>Reason<input name="reason" required maxlength="500" /></label><div class="admin-action-row"><button name="action" value="ACTIVATE" class="button button--quiet">Activate</button><button name="action" value="PAUSE" class="button button--quiet">Admin pause</button><button name="action" value="RESUME" class="button button--quiet">Resume</button><button name="action" value="DEACTIVATE" class="button button--danger">Deactivate</button></div><p class="form-status" role="status"></p></form>
    <form id="organization-token-control"><h3>Manual token adjustment</h3><label>Token amount<input name="amount" type="number" min="-1000000" max="1000000" required /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Apply adjustment</button><p class="form-status" role="status"></p></form></section>
    <section class="admin-payment-history"><h3>Payment history</h3><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Receipt</th><th>Date</th><th>Amount</th><th>Tokens</th></tr></thead><tbody>${payments}</tbody></table></div></section>`;
  panel.querySelector(".admin-back-link").addEventListener("click", (event) => {
    event.preventDefault();
    window.history.pushState({}, "", "/admin/organizations");
    renderAuthenticatedSection(root, "/admin/organizations");
  });
  const statusForm = panel.querySelector("#organization-status-control");
  statusForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(statusForm);
    const status = statusForm.querySelector(".form-status");
    const update = await fetch(`${API_ROOT}/admin/organizations/${encodeURIComponent(panel.dataset.tenantId)}/status`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: submitter.value, reason: data.get("reason") }) });
    const result = await update.json();
    if (!update.ok) return void (status.textContent = result.message || "Status change failed.");
    panel.querySelector("#detail-operational-status").textContent = displayEnum(result.operational_status);
    status.textContent = "Business status updated and audited.";
    statusForm.reset();
  });
  const tokenForm = panel.querySelector("#organization-token-control");
  tokenForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(tokenForm);
    const status = tokenForm.querySelector(".form-status");
    const update = await fetch(`${API_ROOT}/admin/organizations/${encodeURIComponent(panel.dataset.tenantId)}/token-adjustments`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount: Number(data.get("amount")), reason: data.get("reason") }) });
    const result = await update.json();
    if (!update.ok) return void (status.textContent = result.message || "Token adjustment failed.");
    panel.querySelector("#detail-token-balance").textContent = result.available_tokens;
    status.textContent = "Token balance adjusted and audited.";
    tokenForm.reset();
  });
  const postSubscription = async (path, body, form) => {
    const status = form.querySelector(".form-status");
    const update = await fetch(`${API_ROOT}/admin/subscriptions/${encodeURIComponent(panel.dataset.tenantId)}${path}`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const result = await update.json();
    if (!update.ok) return void (status.textContent = result.message || "Subscription update failed.");
    panel.querySelector("#subscription-state").textContent = displayEnum(result.state);
    panel.querySelector("#subscription-plan").textContent = result.plan_code;
    panel.querySelector("#subscription-next-billing").textContent = result.next_billing_at ? new Date(result.next_billing_at).toLocaleDateString() : "Not scheduled";
    panel.querySelector("#subscription-trial-end").textContent = result.trial_ends_at ? new Date(result.trial_ends_at).toLocaleDateString() : "Not applicable";
    status.textContent = "Subscription updated and audited.";
  };
  const transitionForm = panel.querySelector("#subscription-transition-form");
  transitionForm?.addEventListener("submit", (event) => { event.preventDefault(); const data = new FormData(transitionForm); postSubscription("/transitions", { action: event.submitter.value, reason: data.get("reason") }, transitionForm); });
  const planForm = panel.querySelector("#subscription-plan-form");
  planForm?.addEventListener("submit", (event) => { event.preventDefault(); const data = new FormData(planForm); postSubscription("/plan", { plan_code: data.get("planCode"), next_billing_at: data.get("nextBilling") || null, reason: data.get("reason") }, planForm); });
  const trialForm = panel.querySelector("#trial-extension-form");
  trialForm?.addEventListener("submit", (event) => { event.preventDefault(); const data = new FormData(trialForm); postSubscription("/trial-extension", { days: Number(data.get("days")), reason: data.get("reason") }, trialForm); });
}

function attachOrganizationControls(root, pathname) {
  if (pathname.split("/")[3]) {
    loadOrganizationDetail(root);
    return;
  }
  const filters = root.querySelector("#organization-filters");
  filters?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(filters);
    const parameters = new URLSearchParams();
    if (data.get("search")) parameters.set("search", data.get("search"));
    if (data.get("businessType")) parameters.set("business_type", data.get("businessType"));
    if (data.get("status")) parameters.set("status", data.get("status"));
    loadOrganizations(root, parameters.size ? `?${parameters}` : "");
  });
  loadOrganizations(root);
}

function renderAuthenticatedSection(root, pathname) {
  root.innerHTML = adminHomeView(pathname);
  root.querySelectorAll(".admin-navigation a, .admin-sidebar__brand a").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = link.getAttribute("href");
      window.history.pushState({}, "", target);
      renderAuthenticatedSection(root, target);
    });
  });
  root.querySelector("#admin-logout").addEventListener("click", async () => {
    await fetch(`${API_ROOT}/admin/logout`, { method: "POST", credentials: "same-origin" });
    redirect("/admin");
  });
  if (adminSection(pathname).slug === "organizations") attachOrganizationControls(root, pathname);
  if (adminSection(pathname).slug === "enquiries") attachEnquiries(root);
  if (adminSection(pathname).slug === "dashboard") attachDashboardControls(root);
  if (adminSection(pathname).slug === "realtime") attachRealtimeDashboard(root);
  if (adminSection(pathname).slug === "ai-models-cost") attachAiCostDashboard(root);
  if (adminSection(pathname).slug === "customers-subscriptions") attachCustomerControls(root);
  if (adminSection(pathname).slug === "billing-pricing") attachPricingControls(root);
  if (adminSection(pathname).slug === "platform-operations") attachTryOnOperations(root);
  if (adminSection(pathname).slug === "audit-history") attachAuditHistory(root);
}

export async function renderAdminApp(root, pathname) {
  if (pathname !== "/admin" && pathname !== "/admin/") {
    if (!(await hasAdminSession())) {
      redirect("/admin");
      return;
    }
    renderAuthenticatedSection(root, pathname);
    window.addEventListener("popstate", () => renderAuthenticatedSection(root, window.location.pathname));
    return;
  }
  if (await hasAdminSession()) {
    redirect("/admin/dashboard");
    return;
  }
  root.innerHTML = loginView();
  attachLogin(root);
}
