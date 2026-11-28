import { wearoAlert, wearoConfirm } from "./wearo-dialog.js";

const API_ROOT = "/api/v1";

const ADMIN_SECTIONS = [
  { slug: "dashboard", label: "Dashboard", icon: "▦", description: "Platform overview and key operational signals." },
  { slug: "realtime", label: "Realtime", icon: "◉", description: "Live try-on volume, generation time, and AI cost." },
  { slug: "organizations", label: "Businesses", icon: "◇", description: "Manage business profiles, usage, tokens, and operational access." },
  { slug: "support", label: "Support", icon: "?", description: "Find customers, inspect payment status, and add audited token credits." },
  { slug: "enquiries", label: "Enquiries", icon: "✦", description: "Review business enquiries submitted through the public contact page." },
  { slug: "customers-subscriptions", label: "Subscriptions", icon: "◎", description: "Manage plans, trials, billing status, cancellations, and renewals." },
  { slug: "payments", label: "Payments", icon: "₹", description: "Review B2C and B2B collections, payment outcomes, and transaction reports." },
  { slug: "billing-pricing", label: "Billing & Pricing", icon: "₹", description: "Review platform billing and pricing configuration." },
  { slug: "notifications", label: "Notifications", icon: "✉", description: "Create and publish Email, SMS, and WhatsApp communication templates." },
  { slug: "platform-operations", label: "Platform Operations", icon: "⚙", description: "Monitor the services that operate Wearo." },
  { slug: "service-health", label: "Service Health", icon: "♥", description: "Run live health checks for every Wearo service and worker." },
  { slug: "audit-history", label: "Audit History", icon: "≡", description: "Review administrator and platform audit events." },
  { slug: "ai-models-cost", label: "AI Models & Cost", icon: "$", description: "Review production models and pricing promoted from Cost Lab." },
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

function supportView() {
  return `<section class="admin-support-hero"><div class="admin-support-hero__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4M11 8.5v5M8.5 11h5"/></svg></div><div class="admin-support-hero__copy"><p class="eyebrow">Customer support</p><h2>Find a Wearo account</h2><p>Search a verified email address or phone number to review identity, balance, and payment activity.</p></div><form id="admin-support-search" class="admin-support-search" role="search"><label><span>Email or phone</span><div class="admin-support-search__field"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></svg><input name="identity" type="search" required maxlength="320" autocomplete="off" placeholder="user@example.com or +91 98765 43210" /></div></label><button class="button button--primary admin-action-with-icon" type="submit"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></svg><span>Search account</span></button></form><p id="admin-support-status" class="admin-support-search__status" role="status" aria-live="polite"></p></section><div id="admin-support-results" class="admin-support-results" aria-live="polite"></div>`;
}

function platformDashboardView() {
  const metricLabels = ["Total businesses", "Active businesses", "Registered consumers", "Total try-ons", "Successful try-ons", "Failed try-ons", "Wearo tokens consumed", "Provider tokens", "Provider cost", "Average cost / generation", "Try-ons / second", "Average try-ons per business"];
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

function paymentAudience(pathname) {
  return pathname.split("/")[3]?.toLowerCase() === "b2b" ? "b2b" : "b2c";
}

function paymentsView(pathname) {
  const audience = paymentAudience(pathname);
  const title = audience === "b2c" ? "B2C payments" : "B2B payments";
  const description = audience === "b2c"
    ? "Consumer package purchases and the tokens credited after successful payment."
    : "Business token-package collections, invoices, and the tokens credited to organizations.";
  const metricLabels = ["Total collected", "Successful payments", "Pending payments", "Failed / refunded", "Average payment", "Tokens credited"];
  return `<section class="admin-payments" data-payment-audience="${audience}">
    <nav class="admin-payment-tabs" aria-label="Payment audience"><a class="admin-route-link" href="/admin/payments/b2c" ${audience === "b2c" ? 'aria-current="page"' : ""}>B2C payments</a><a class="admin-route-link" href="/admin/payments/b2b" ${audience === "b2b" ? 'aria-current="page"' : ""}>B2B payments</a></nav>
    <div class="admin-section-heading admin-payment-heading"><div><p class="eyebrow">Payment reports</p><h2>${title}</h2><p>${description}</p></div><span id="admin-payment-period-label">Today</span></div>
    <form id="admin-payment-report-filter" class="admin-dashboard-filters">
      <fieldset><legend>Date range</legend><div class="admin-period-options"><label><input type="radio" name="period" value="today" checked /> Today</label><label><input type="radio" name="period" value="week" /> Last 7 Days</label><label><input type="radio" name="period" value="month" /> This Month</label><label><input type="radio" name="period" value="custom" /> Custom</label></div></fieldset>
      <div id="admin-payment-custom-dates" class="admin-custom-dates" hidden><label>From<input name="dateFrom" type="date" /></label><label>To<input name="dateTo" type="date" /></label></div>
      <label>Payment status<select name="status"><option value="">All payments</option><option value="PAID">Paid</option><option value="PENDING">Pending</option>${audience === "b2b" ? '<option value="OVERDUE">Overdue</option>' : ""}<option value="FAILED">Failed</option><option value="REFUNDED">Refunded</option></select></label>
      <button class="button button--primary" type="submit">Apply filters</button>
    </form>
    <div id="admin-payment-report-summary" class="admin-stat-grid admin-payment-summary" aria-live="polite">${metricLabels.map((label) => `<article class="is-loading"><span>${label}</span><strong>—</strong><small>Loading report</small></article>`).join("")}</div>
    <section class="admin-payment-transactions"><div class="admin-section-heading"><div><p class="eyebrow">Transactions</p><h2>Payment activity</h2></div><span>Latest payment activity in the selected period</span></div><div id="admin-payment-report-list" class="admin-data-panel" aria-live="polite"><div class="admin-loading-state"><span></span><strong>Loading payments</strong></div></div></section>
  </section>`;
}

function pricingSettingsView() {
  const businessTypes = '<option value="">All business types</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option>';
  return `<section class="admin-data-panel admin-retail-pricing"><div><p class="eyebrow">Website price</p><h2>Publish retail try-on price</h2><p>Set the rupee price shown in B2C and B2B. This does not change existing action rates, wallets, plans, packages, or past transactions.</p></div><form id="retail-tryon-price-form"><label>Price per try-on (INR)<input name="price" type="number" min="0.20" max="100000" step="0.20" required placeholder="3.00" /></label><div class="admin-retail-pricing__preview"><small>Automatic conversion</small><strong id="retail-token-preview">Enter a price</strong><span>(price × 10) ÷ 2</span></div><label>Reason for publishing<input name="reason" required maxlength="500" placeholder="Approved retail price" /></label><button class="button button--primary">Publish website price</button><p class="form-status" role="status" aria-live="polite"></p></form><div id="admin-retail-pricing-current" class="admin-retail-pricing__current" aria-live="polite">Loading current website price…</div></section>
  <section class="admin-data-panel admin-retail-package"><div><p class="eyebrow">B2C packages</p><h2 id="retail-package-form-title">Create try-on package</h2><p>The package receives 5 tokens for every ₹1 before tax. Estimated try-ons use the currently published tokens-per-try-on rate.</p></div><form id="retail-tryon-package-form"><label>Package name<input name="name" required maxlength="80" placeholder="Starter" /></label><label>Minimum amount before tax (INR)<input name="amount" type="number" min="0.20" max="10000000" step="0.20" required placeholder="100.00" /></label><label>GST rate (%)<input name="gst" type="number" min="0" max="100" step="0.01" value="18" required /></label><div class="admin-retail-pricing__preview"><small>Automatic package calculation</small><strong id="retail-package-preview">Enter a minimum amount</strong><span>5 tokens per ₹1 before tax · try-ons use the published token rate</span></div><label>Reason for change<input name="reason" required maxlength="500" placeholder="Approved B2C package" /></label><div class="form-actions"><button id="retail-package-submit" class="button button--primary admin-action-with-icon"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg><span>Create package</span></button><button id="retail-package-cancel-edit" class="button button--quiet admin-action-with-icon" type="button" hidden><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18"/></svg><span>Cancel edit</span></button></div><p class="form-status" role="status" aria-live="polite"></p></form><div id="admin-retail-package-list" class="admin-retail-pricing__current" aria-live="polite">Loading packages…</div></section>
  <section class="admin-revenue-dashboard"><h2>Platform revenue</h2><form id="admin-revenue-filter" class="admin-filters"><label>From<input name="dateFrom" type="date" required /></label><label>To<input name="dateTo" type="date" required /></label><label>Organization<select name="tenantId"><option value="">All organizations</option></select></label><button class="button button--primary">Apply filters</button></form><div id="admin-revenue-metrics" class="admin-platform-metrics" aria-live="polite">Loading revenue…</div><p class="field-help">Received revenue includes completed payments only. Pending collections are shown separately. Estimated AI cost and margin use the configured cost per generation attempt; actual recorded provider costs are shown independently.</p></section>
  <div class="admin-pricing-grid"><form id="pricing-settings-form" class="admin-data-panel"><h2>Platform subscription pricing</h2><label>Plan code<input name="planCode" required maxlength="40" /></label><label>Business type<select name="businessType">${businessTypes}</select></label><label>Monthly fee (INR)<input name="monthlyFee" type="number" min="0" step="0.01" required /></label><label>Tokens per try-on<input name="tryOnCost" type="number" min="1" required /></label><label>Free trial tokens<input name="trialTokens" type="number" min="0" required /></label><label>Trial duration (days)<input name="trialDays" type="number" min="1" max="365" required /></label><label>Payment grace period (days)<input name="graceDays" type="number" min="0" max="90" required /></label><label>GST / tax rate (%)<input name="gst" type="number" min="0" max="100" step="0.01" required /></label><label>Reason for pricing change<input name="reason" required maxlength="500" /></label><button class="button button--primary">Publish pricing</button><p class="form-status" role="status"></p></form>
  <form id="token-package-form" class="admin-data-panel"><h2>Create or replace token package</h2><label>Package code<input name="code" required maxlength="40" /></label><label>Business type<select name="businessType">${businessTypes}</select></label><label>Purchased tokens<input name="purchased" type="number" min="1" required /></label><label>Bonus tokens<input name="promo" type="number" min="0" required /></label><label>Package price (INR)<input name="amount" type="number" min="0.01" step="0.01" required /></label><label>Bulk discount (%)<input name="discount" type="number" min="0" max="100" step="0.01" required /></label><label>GST / tax rate (%)<input name="gst" type="number" min="0" max="100" step="0.01" required /></label><label>Reason for package change<input name="reason" required maxlength="500" /></label><button class="button button--primary">Publish package</button><p class="form-status" role="status"></p></form></div><section class="admin-pricing-current"><h2>Current pricing</h2><div id="admin-pricing-current" class="admin-data-panel">Loading pricing…</div></section>`;
}

function tryOnOperationsView() {
  return `<section><h2>Try-on controls</h2><div id="platform-control-status" class="admin-data-panel" aria-live="polite">Loading platform status…</div><form id="platform-control-form" class="admin-filters"><label>Scope<select name="scope"><option value="PLATFORM">Entire platform</option><option value="BUSINESS_TYPE">Business type</option><option value="ORGANIZATION">One organization</option></select></label><label>Target<select name="scopeKey"><option value="">All</option></select></label><label>Reason<input name="reason" required maxlength="500" /></label><label class="admin-confirm"><input name="confirmed" type="checkbox" required /> I confirm this control change</label><div><button name="action" value="PAUSE" class="button button--danger">Pause try-ons</button><button name="action" value="RESUME" class="button button--quiet">Resume try-ons</button></div><p class="form-status" role="status"></p></form><p class="field-help">Controls affect new try-ons only. Login, payments, history, and existing try-on results remain available.</p></section><form id="tryon-operations-filter" class="admin-dashboard-filters"><label>From<input name="dateFrom" type="date" required /></label><label>To<input name="dateTo" type="date" required /></label><label>Organization<select name="tenantId"><option value="">All organizations</option></select></label><label>Business type<select name="businessType"><option value="">All business types</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label><button class="button button--primary">Apply filters</button></form><div id="tryon-operations-metrics" class="admin-platform-metrics" aria-live="polite">Loading try-on operations…</div><section><h2>Failure reasons</h2><div id="tryon-failure-reasons" class="admin-data-panel"></div></section><section><h2>Request status</h2><p class="field-help">Operational metadata only. Customer images are not loaded or displayed.</p><div id="tryon-operation-list" class="admin-data-panel"></div><div id="tryon-operation-detail" class="admin-data-panel" hidden></div></section>`;
}

function serviceHealthView() {
  return `<section class="service-health">
    <div class="service-health__toolbar"><div><p class="eyebrow">Platform monitoring</p><h2>Services and workers</h2><p>Run an on-demand check across the Wearo runtime. Results are live and are not stored.</p></div><button id="service-health-sync" class="button button--primary admin-action-with-icon" type="button"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/></svg><span>Refresh status</span></button></div>
    <div id="service-health-summary" class="service-health__summary is-loading" aria-live="polite"><span class="service-health__summary-icon"><i></i></span><div><small>Overall platform status</small><strong>Checking services…</strong><p>Contacting each configured health endpoint.</p></div></div>
    <div class="service-health__section-heading"><div><h3>Runtime services</h3><p>API processes and background workers</p></div><span id="service-health-count">Checking 5 services</span></div>
    <div class="service-health__table"><div class="service-health__table-head" aria-hidden="true"><span>Service</span><span>Status</span><span>Endpoint</span><span>Response time</span></div><div id="service-health-list" class="service-health__grid">${Array.from({ length: 5 }, () => '<article class="service-health__card is-loading"><div class="service-health__card-heading"><span class="service-health__service-icon"></span><div><small>Runtime service</small><h3>Loading service…</h3></div></div><span class="service-health__skeleton service-health__skeleton--status"></span><span class="service-health__skeleton"></span><span class="service-health__skeleton service-health__skeleton--time"></span></article>').join("")}</div></div>
  </section>`;
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
  if (active.slug === "support") return supportView();
  if (active.slug === "enquiries") return enquiriesView();
  if (active.slug === "customers-subscriptions") return customerDashboardView();
  if (active.slug === "payments") return paymentsView(pathname);
  if (active.slug === "billing-pricing") return pricingSettingsView();
  if (active.slug === "notifications") return notificationsView();
  if (active.slug === "platform-operations") return tryOnOperationsView();
  if (active.slug === "service-health") return serviceHealthView();
  if (active.slug === "audit-history") return auditHistoryView();
  return `<article class="admin-welcome-panel"><h2>${active.slug === "dashboard" ? "Wearo Admin home" : `${active.label} overview`}</h2><p>${active.slug === "dashboard" ? "Choose a section from the navigation to manage the Wearo platform." : "This section is ready for its dedicated administration capabilities."}</p></article>`;
}

const NOTIFICATION_PURPOSES = [
  ["WELCOME", "NOTIFICATION", "Welcome"],
  ["NEW_FEATURES", "NOTIFICATION", "New features"],
  ["MONTHLY_REPORT", "NOTIFICATION", "Monthly report"],
  ["SUPPORT_DEFAULT_RESPONSE", "SUPPORT", "Default support response"],
  ["BILLING_MONTH_START", "BILLING", "Monthly first billing notification"],
  ["BILLING_DAY_BEFORE", "BILLING", "Day before billing notification"],
  ["BILLING_DUE_DAY", "BILLING", "Due-day billing notification"],
  ["BILLING_PAUSE_DAY_1", "BILLING", "One day after due date"],
  ["BILLING_PAUSE_DAY_3", "BILLING", "Three days after due date"],
  ["BILLING_ACCOUNT_PAUSED_DAY_7", "BILLING", "Account paused after seven days"],
];

function notificationsView() {
  const purposes = `<option value="ALL" data-category="ALL">All templates</option>${NOTIFICATION_PURPOSES.map(([key, category, label]) => `<option value="${key}" data-category="${category}">${label}</option>`).join("")}`;
  return `<div class="admin-notifications">
    <form id="notification-template-form" class="notification-editor">
      <header class="notification-editor__header"><div><p class="eyebrow">Communication studio</p><h2>Template editor</h2><p>Generate with AI, review the customer experience, and publish when ready.</p></div><span class="notification-editor__badge">AI assisted</span></header>
      <section class="notification-editor__section"><div class="notification-editor__section-heading"><span>1</span><div><h3>Template configuration</h3><p>Choose where this communication is delivered and what triggers it.</p></div></div><div class="notification-editor__config"><label>Channel<select name="channel"><option>EMAIL</option><option>SMS</option><option>WHATSAPP</option></select></label><label>Purpose<select name="templateKey">${purposes}</select></label><label>Display name<input name="displayName" required maxlength="160" /></label></div></section>
      <section class="notification-editor__section notification-editor__ai"><div class="notification-editor__section-heading"><span>2</span><div><h3>AI creative brief</h3><p>Describe the audience, tone, and message. Wearo layout and safety rules are applied automatically.</p></div></div><label><span class="sr-only">AI generation prompt</span><textarea name="prompt" rows="5" maxlength="4000" placeholder="Example: Welcome a new business owner with a warm, premium tone. Encourage them to sign in and explore their dashboard."></textarea></label><div class="notification-reference"><label>Reference image <small>Optional visual inspiration for layout and tone</small><input name="referenceImage" type="file" accept="image/png,image/jpeg,image/webp,image/gif" /></label><div class="notification-reference__preview" hidden><img alt="Selected template reference"><div><strong data-reference-name></strong><small>PNG, JPEG, WEBP or GIF · maximum 5 MB</small><button type="button" data-remove-reference>Remove image</button></div></div></div><div class="notification-editor__inline-actions"><small>AI creates drafts only. You remain in control of publishing.</small><div><button id="generate-notification-template" class="button button--primary" type="button"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m12 3 1.35 4.15L17.5 8.5l-4.15 1.35L12 14l-1.35-4.15L6.5 8.5l4.15-1.35L12 3Z"/><path d="m18.5 14 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z"/></svg><span>Generate drafts</span></button></div></div></section>
      <section class="notification-editor__section notification-editor__message-section"><div class="notification-editor__section-heading"><span>3</span><div><h3>Message content</h3><p data-message-help>Review the generated content or edit it directly before previewing.</p></div></div><div class="notification-editor__content"><label class="notification-subject">Subject<input name="subject" maxlength="998" placeholder="Customer-facing email subject" /></label><label>Body <small data-body-help>Email-safe HTML is supported</small><textarea class="notification-code-field" name="body" rows="9" required maxlength="20000" placeholder="Your message body will appear here."></textarea></label><label class="notification-signature">Signature <small>Displayed once beneath the message</small><textarea class="notification-code-field" name="signature" rows="4" maxlength="2000" placeholder="Your sign-off will appear here."></textarea></label></div></section>
      <section class="notification-editor__publish"><label>Publishing status<select name="status"><option value="DRAFT">Save as draft</option><option value="ACTIVE">Publish active version</option></select></label><div class="notification-editor__publish-actions"><button id="preview-notification-template" class="button button--quiet notification-editor__icon-action" type="button" aria-label="Preview email" title="Preview email"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.75"/></svg></button><button class="button button--primary notification-editor__icon-action" type="submit" aria-label="Save template version" title="Save template version"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 3h11l3 3v15H5V3Z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/></svg></button></div><p class="form-status" role="status"></p></section>
    </form>
    <section class="notification-versions"><div class="admin-section-heading"><div><p class="eyebrow">Version control</p><h2>Template versions</h2><p>Only one active version is used for each channel and purpose.</p></div><div class="notification-version-tools"><label>Notification type<select id="notification-channel-filter"><option value="ALL">All types</option><option value="SMS">SMS</option><option value="EMAIL">Email</option><option value="WHATSAPP">WhatsApp</option></select></label><button id="delete-all-email-templates" class="button button--quiet notification-delete-all" type="button"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/></svg><span>Delete all email templates</span></button></div></div><div id="notification-template-list" class="admin-data-panel">Loading templates…</div></section>
    <dialog id="notification-email-preview" class="notification-preview-dialog"><div class="notification-preview-dialog__panel"><header><div><p class="eyebrow">Email preview</p><h2>Recipient view</h2></div><button class="notification-preview-dialog__close" type="button" aria-label="Close preview">×</button></header><div class="notification-preview-envelope"><div class="notification-preview-envelope__header"><p><span>From</span><strong data-preview-from></strong></p><p><span>To</span><strong data-preview-to></strong></p><p><span>Subject</span><strong data-preview-subject></strong></p></div><div class="notification-preview-envelope__body" data-preview-body></div></div><p class="field-help">Names, addresses, links, amounts, and images are realistic preview samples. Actual delivery uses API-provided values.</p></div></dialog>
  </div>`;
}

function notificationSamples() {
  const people = [{ firstName: "Aarav", fullName: "Aarav Sharma", email: "aarav.sharma@example.com" }, { firstName: "Ananya", fullName: "Ananya Iyer", email: "ananya.iyer@example.com" }, { firstName: "Diya", fullName: "Diya Mehta", email: "diya.mehta@example.com" }, { firstName: "Kabir", fullName: "Kabir Rao", email: "kabir.rao@example.com" }, { firstName: "Meera", fullName: "Meera Nair", email: "meera.nair@example.com" }];
  const person = people[Math.floor(Math.random() * people.length)];
  return { person, values: { name: person.fullName, first_name: person.firstName, full_name: person.fullName, account_email: person.email, email: person.email, features: "Faster virtual try-ons and new reporting tools", report_month: "November 2026", report_summary: "Your business completed 248 try-ons this month.", original_subject: "Help with my account", support_reference: "SUP-2026-1042", support_email: "support@wearo.ai", billing_month: "November 2026", amount_due: "₹4,999.00", due_date: "15 November 2026", customer_login_url: `${window.location.origin}/business/sign-in`, dashboard_url: `${window.location.origin}/business/sign-in`, help_center_url: `${window.location.origin}/business/support`, lady_image_url: `${window.location.origin}/wearo-hero-campaign.webp`, wearo_logo_url: `${window.location.origin}/wearo-brand_white_bg.png?v=20261114-email-2` } };
}

function notificationSample(value, samples) {
  return String(value || "")
    .replace(/{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}/g, (_, key) => samples[key] || `[${key}]`)
    .replace(/\[([a-zA-Z][a-zA-Z0-9_]*)\]/g, (_, key) => samples[key] || `[${key}]`);
}

function safeEmailPreview(markup) {
  if (!/<[a-z][\s\S]*>/i.test(markup)) return escapeHtml(markup).replaceAll("\n", "<br>");
  const documentPreview = new DOMParser().parseFromString(markup, "text/html");
  documentPreview.querySelectorAll("script, iframe, object, embed, form, meta, base, img").forEach((node) => node.remove());
  documentPreview.querySelectorAll("*").forEach((node) => [...node.attributes].forEach((attribute) => {
    if (attribute.name.toLowerCase().startsWith("on") || /javascript:/i.test(attribute.value)) node.removeAttribute(attribute.name);
  }));
  documentPreview.querySelectorAll("a").forEach((link) => {
    if (/sign in|dashboard|view report|pay now/i.test(link.textContent || "")) link.classList.add("notification-preview-cta");
  });
  return documentPreview.body.innerHTML;
}

function cleanNotificationSignature(markup) {
  const value = String(markup || "").replace(/<img\b[^>]*>/gi, "").trim();
  if (!/\bteam\s+wearo(?:\.ai)?\b/i.test(value)) return value;
  return value.replace(/<(p|div|span)\b[^>]*>\s*(?:https?:\/\/)?(?:www\.)?wearo\.ai\/?\s*<\/\1>/gi, "").trim();
}

function showNotificationPreview(root, template) {
  if (template.channel !== "EMAIL") return;
  const dialog = root.querySelector("#notification-email-preview");
  const sample = notificationSamples();
  const category = template.category || "NOTIFICATION";
  dialog.querySelector("[data-preview-from]").textContent = category === "BILLING" ? "Wearo.ai Billing" : category === "SUPPORT" ? "Wearo.ai Support" : "Wearo.ai Notifications";
  dialog.querySelector("[data-preview-to]").textContent = `${sample.person.fullName} <${sample.person.email}>`;
  dialog.querySelector("[data-preview-subject]").textContent = notificationSample(template.subject, sample.values) || "(No subject)";
  const sampledBody = notificationSample(template.body, sample.values).trim();
  const body = safeEmailPreview(sampledBody);
  const bodyHasSignature = /\b(from the (?:wearo\.ai )?team|team wearo(?:\.ai)?)\b/i.test(sampledBody);
  const signature = template.signature && !bodyHasSignature ? safeEmailPreview(cleanNotificationSignature(notificationSample(template.signature, sample.values))) : "";
  const logo = '<div class="notification-preview-email-logo"><img src="/wearo-brand_white_bg.png?v=20261114-email-2" alt="Wearo.ai"></div>';
  const messageContent = `<div class="notification-preview-email-copy">${body}${signature ? `<div class="notification-preview-email-signature">${signature}</div>` : ""}</div>`;
  const message = `<div class="notification-preview-email-campaign"><div class="notification-preview-email-overlay">${logo}${messageContent}</div></div>`;
  dialog.querySelector("[data-preview-body]").innerHTML = `<div class="notification-preview-email-content"><div class="notification-preview-email-message">${message}</div></div>`;
  dialog.showModal();
}

async function loadNotificationTemplates(root) {
  const list = root.querySelector("#notification-template-list");
  const response = await fetch(`${API_ROOT}/admin/notifications/templates`, { credentials: "same-origin" });
  if (!response.ok) return void (list.textContent = "Templates could not be loaded.");
  const data = await response.json();
  const allTemplates = data.templates;
  const channelFilter = root.querySelector("#notification-channel-filter").value;
  data.templates = channelFilter === "ALL" ? allTemplates : allTemplates.filter((item) => item.channel === channelFilter);
  const deleteAll = root.querySelector("#delete-all-email-templates");
  deleteAll.disabled = !allTemplates.some((item) => item.channel === "EMAIL");
  list.innerHTML = data.templates.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Channel</th><th>Purpose</th><th>Category</th><th>Version</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead><tbody>${data.templates.map((item, index) => `<tr><td>${escapeHtml(item.channel)}</td><td><strong>${escapeHtml(item.display_name)}</strong><br><small>${escapeHtml(item.template_key)}</small></td><td>${escapeHtml(displayEnum(item.category))}</td><td>${escapeHtml(item.version)}</td><td><span class="admin-status">${escapeHtml(displayEnum(item.status))}</span></td><td>${escapeHtml(new Date(item.updated_at).toLocaleString())}</td><td><div class="admin-ai-row-actions notification-template-actions"><button class="advertisement-icon-button" type="button" data-edit-template="${index}" aria-label="Edit template" title="Edit template"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"/></svg></button>${item.channel === "EMAIL" ? `<button class="advertisement-icon-button" type="button" data-preview-template="${index}" aria-label="Preview template" title="Preview template"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.75"/></svg></button><button class="advertisement-icon-button advertisement-icon-button--primary" type="button" data-send-test-template="${escapeHtml(item.template_id)}" data-send-test-template-name="${escapeHtml(item.display_name)}" aria-label="Send test email" title="Send test email"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m3 11 18-8-8 18-2.5-7.5L3 11Z"/><path d="M10.5 13.5 21 3"/></svg></button>` : ""}${item.status === "DRAFT" ? `<button class="advertisement-icon-button" type="button" data-activate-template="${escapeHtml(item.template_id)}" data-activate-template-name="${escapeHtml(item.display_name)}" data-activate-template-version="${escapeHtml(item.version)}" aria-label="Make template active" title="Make active"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg></button>` : ""}<button class="advertisement-icon-button advertisement-icon-button--danger" type="button" data-delete-template="${escapeHtml(item.template_id)}" data-delete-template-name="${escapeHtml(item.display_name)}" data-delete-template-version="${escapeHtml(item.version)}" data-delete-template-status="${escapeHtml(item.status)}" aria-label="Delete template" title="Delete template"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></button></div></td></tr>`).join("")}</tbody></table></div>` : '<p class="admin-empty">No templates configured.</p>';
  list.querySelectorAll("[data-edit-template]").forEach((button) => button.addEventListener("click", () => {
    const template = data.templates[Number(button.dataset.editTemplate)];
    const form = root.querySelector("#notification-template-form");
    form.elements.channel.value = template.channel;
    form.elements.templateKey.value = template.template_key;
    form.elements.templateKey.dispatchEvent(new Event("change"));
    form.elements.displayName.value = template.display_name;
    form.elements.prompt.value = template.generation_prompt || "";
    form.elements.subject.value = template.subject || "";
    form.elements.body.value = template.body || "";
    form.elements.signature.value = template.signature || "";
    form.elements.status.value = "DRAFT";
    form.querySelector(".form-status").textContent = `Editing ${template.display_name} version ${template.version}. Saving creates a new draft version.`;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    (template.channel === "EMAIL" ? form.elements.subject : form.elements.body).focus({ preventScroll: true });
  }));
  list.querySelectorAll("[data-preview-template]").forEach((button) => button.addEventListener("click", () => showNotificationPreview(root, data.templates[Number(button.dataset.previewTemplate)])));
  list.querySelectorAll("[data-send-test-template]").forEach((button) => button.addEventListener("click", async () => {
    const confirmed = await wearoConfirm({ eyebrow: "Test email", title: `Send ${button.dataset.sendTestTemplateName}?`, message: "This exact saved template version will be queued for delivery to the configured super-admin email address.", note: "The notification worker must be running and Amazon SES must allow the recipient address.", confirmLabel: "Send test email", cancelLabel: "Cancel", tone: "info" });
    if (!confirmed) return;
    button.disabled = true;
    try {
      const response = await fetch(`${API_ROOT}/admin/notifications/templates/${encodeURIComponent(button.dataset.sendTestTemplate)}/send-test`, { method: "POST", credentials: "same-origin" });
      const result = await response.json();
      if (!response.ok) return void (await wearoAlert({ eyebrow: "Test email not queued", title: "Unable to send the test", message: result.message || result.detail || "Check the email and SES configuration, then try again.", confirmLabel: "Understood" }));
      await wearoAlert({ eyebrow: "Test email queued", title: "Check the super-admin inbox", message: `The saved template was queued for ${result.recipient}.`, confirmLabel: "Done" });
    } finally {
      button.disabled = false;
    }
  }));
  list.querySelectorAll("[data-activate-template]").forEach((button) => button.addEventListener("click", async () => {
    const confirmed = await wearoConfirm({ eyebrow: "Template version", title: `Make ${button.dataset.activateTemplateName} version ${button.dataset.activateTemplateVersion} active?`, message: "This draft will be used for future notifications of this purpose.", note: "The currently active version will automatically return to draft status.", confirmLabel: "Make active", cancelLabel: "Keep as draft", tone: "info" });
    if (!confirmed) return;
    button.disabled = true;
    try {
      const response = await fetch(`${API_ROOT}/admin/notifications/templates/${encodeURIComponent(button.dataset.activateTemplate)}/activate`, { method: "POST", credentials: "same-origin" });
      const result = await response.json();
      if (!response.ok) return void (await wearoAlert({ eyebrow: "Template not activated", title: "Unable to change the active version", message: result.message || result.detail || "Refresh the templates and try again.", confirmLabel: "Understood" }));
      await loadNotificationTemplates(root);
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }));
  list.querySelectorAll("[data-delete-template]").forEach((button) => button.addEventListener("click", async () => {
    const isActive = button.dataset.deleteTemplateStatus === "ACTIVE";
    const confirmed = await wearoConfirm({ eyebrow: "Notification template", title: isActive ? "Delete the active template?" : "Delete this template version?", message: `${button.dataset.deleteTemplateName} version ${button.dataset.deleteTemplateVersion} will be permanently deleted.`, note: isActive ? "Pending notifications using this active template will be cancelled. Publish another version before sending this notification type again." : "This action cannot be undone.", confirmLabel: "Delete version", cancelLabel: "Keep template" });
    if (!confirmed) return;
    const deleteResponse = await fetch(`${API_ROOT}/admin/notifications/templates/${encodeURIComponent(button.dataset.deleteTemplate)}`, { method: "DELETE", credentials: "same-origin" });
    if (!deleteResponse.ok) return void (await wearoAlert({ eyebrow: "Template not deleted", title: "This version is currently in use", message: "Wait for the notification worker to finish its current delivery, then try again.", confirmLabel: "Understood" }));
    loadNotificationTemplates(root);
  }));
}

function attachNotificationControls(root) {
  const form = root.querySelector("#notification-template-form");
  const purpose = form.elements.templateKey;
  const referenceInput = form.elements.referenceImage;
  const referencePreview = form.querySelector(".notification-reference__preview");
  let referenceImage = null;
  const standardPurposes = purpose.innerHTML;
  const otpPurpose = '<option value="OTP" data-category="NOTIFICATION">OTP</option>';
  const clearReference = () => {
    referenceImage = null;
    referenceInput.value = "";
    referencePreview.hidden = true;
    referencePreview.querySelector("img").removeAttribute("src");
  };
  referenceInput.addEventListener("change", () => {
    const file = referenceInput.files[0];
    if (!file) return clearReference();
    const allowed = ["image/png", "image/jpeg", "image/webp", "image/gif"];
    if (!allowed.includes(file.type) || file.size > 5 * 1024 * 1024) {
      clearReference();
      form.querySelector(".form-status").textContent = "Choose a PNG, JPEG, WEBP, or GIF image no larger than 5 MB.";
      return;
    }
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      referenceImage = String(reader.result);
      referencePreview.querySelector("img").src = referenceImage;
      referencePreview.querySelector("[data-reference-name]").textContent = file.name;
      referencePreview.hidden = false;
    });
    reader.readAsDataURL(file);
  });
  referencePreview.querySelector("[data-remove-reference]").addEventListener("click", clearReference);
  const syncPurpose = () => {
    const isSms = form.elements.channel.value === "SMS";
    const needsSmsPurpose = isSms && purpose.value !== "OTP";
    const needsStandardPurpose = !isSms && purpose.value === "OTP";
    if (needsSmsPurpose || needsStandardPurpose) {
      purpose.innerHTML = isSms ? otpPurpose : standardPurposes;
    }
    const selected = purpose.selectedOptions[0];
    const isAll = purpose.value === "ALL";
    form.elements.displayName.value = selected.textContent;
    form.elements.displayName.disabled = isAll || isSms;
    form.querySelector(".notification-editor__ai").hidden = isSms;
    form.querySelector(".notification-editor__message-section").hidden = isAll;
    form.querySelector(".notification-editor__publish").classList.toggle("is-batch", isAll);
    form.querySelector(".notification-subject").hidden = form.elements.channel.value !== "EMAIL";
    form.querySelector(".notification-signature").hidden = isSms;
    form.querySelector("[data-message-help]").textContent = isSms ? "Enter the OTP message exactly as it should be sent, then save it." : "Review the generated content or edit it directly before previewing.";
    form.querySelector("[data-body-help]").textContent = isSms ? "Use {{otp}} where the one-time password should appear" : "Email-safe HTML is supported";
    form.elements.body.placeholder = isSms ? "Your Wearo OTP is {{otp}}." : "Your message body will appear here.";
    root.querySelector("#preview-notification-template").hidden = isAll || form.elements.channel.value !== "EMAIL";
    root.querySelector("#generate-notification-template span").textContent = isAll ? "Generate all drafts" : "Generate selected draft";
  };
  purpose.addEventListener("change", syncPurpose);
  form.elements.channel.addEventListener("change", syncPurpose);
  root.querySelector("#notification-channel-filter").addEventListener("change", () => loadNotificationTemplates(root));
  root.querySelector("#generate-notification-template").addEventListener("click", async () => {
    const status = form.querySelector(".form-status");
    const prompt = form.elements.prompt.value.trim();
    if (!prompt) return void (status.textContent = "Enter an AI creative brief first.");
    const channel = form.elements.channel.value;
    const isAll = purpose.value === "ALL";
    const button = root.querySelector("#generate-notification-template");
    if (!isAll) {
      button.disabled = true;
      status.textContent = "Generating the selected draft…";
      try {
        const response = await fetch(`${API_ROOT}/admin/notifications/templates/generate`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, template_key: purpose.value, prompt, reference_image: referenceImage }) });
        const result = await response.json();
        if (!response.ok) return void (status.textContent = result.detail || "The draft could not be generated.");
        form.elements.subject.value = result.subject;
        form.elements.body.value = result.body;
        form.elements.signature.value = result.signature;
        status.textContent = `Version ${result.version} generated and saved as a draft. Review it before publishing.`;
        loadNotificationTemplates(root);
        if (channel === "EMAIL") showNotificationPreview(root, { channel: "EMAIL", category: purpose.selectedOptions[0].dataset.category, subject: result.subject, body: result.body, signature: result.signature });
      } finally {
        button.disabled = false;
      }
      return;
    }
    const confirmed = await wearoConfirm({ eyebrow: "AI template batch", title: `Generate every ${displayEnum(channel)} template?`, message: "The same creative brief will be applied to all notification, support, and billing purposes.", note: "Ten new versions will be saved as drafts. Existing active templates will not change.", confirmLabel: "Generate all drafts", cancelLabel: "Not now", tone: "info" });
    if (!confirmed) return;
    button.disabled = true;
    status.textContent = "Generating all template drafts… This can take up to two minutes.";
    try {
      const response = await fetch(`${API_ROOT}/admin/notifications/templates/generate-all`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, template_key: purpose.value, prompt, reference_image: referenceImage }) });
      const result = await response.json();
      if (!response.ok) return void (status.textContent = result.detail || "The template drafts could not be generated.");
      status.textContent = `${result.count} template drafts generated and saved.`;
      loadNotificationTemplates(root);
    } finally {
      button.disabled = false;
    }
  });
  root.querySelector("#preview-notification-template").addEventListener("click", () => {
    const status = form.querySelector(".form-status");
    if (!form.elements.body.value.trim()) return void (status.textContent = "Add or generate the email body before previewing it.");
    showNotificationPreview(root, { channel: "EMAIL", category: purpose.selectedOptions[0].dataset.category, subject: form.elements.subject.value, body: form.elements.body.value, signature: form.elements.signature.value });
  });
  const previewDialog = root.querySelector("#notification-email-preview");
  previewDialog.querySelector(".notification-preview-dialog__close").addEventListener("click", () => previewDialog.close());
  previewDialog.addEventListener("click", (event) => { if (event.target === previewDialog) previewDialog.close(); });
  root.querySelector("#delete-all-email-templates").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const confirmed = await wearoConfirm({ eyebrow: "Email templates", title: "Delete every email template?", message: "All saved email drafts, active versions, and archived versions will be permanently deleted.", note: "Queued and retrying email notifications will be cancelled. SMS and WhatsApp templates will not be affected.", confirmLabel: "Delete all email templates", cancelLabel: "Keep templates" });
    if (!confirmed) return;
    button.disabled = true;
    try {
      const response = await fetch(`${API_ROOT}/admin/notifications/templates?channel=EMAIL`, { method: "DELETE", credentials: "same-origin" });
      const result = await response.json();
      if (!response.ok) return void (await wearoAlert({ eyebrow: "Templates not deleted", title: "Email delivery is currently active", message: result.message || result.detail || "Wait for current deliveries to finish, then try again.", confirmLabel: "Understood" }));
      await wearoAlert({ eyebrow: "Email templates deleted", title: `${result.deleted} template versions removed`, message: "You can generate a fresh set of email templates whenever you are ready.", confirmLabel: "Done" });
      loadNotificationTemplates(root);
    } finally {
      if (root.querySelector("#notification-template-list")) button.disabled = false;
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = form.querySelector(".form-status");
    if (purpose.value === "ALL") return void (status.textContent = "Use Generate all drafts for the All templates selection.");
    const selected = purpose.selectedOptions[0];
    const isSms = form.elements.channel.value === "SMS";
    const response = await fetch(`${API_ROOT}/admin/notifications/templates`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel: form.elements.channel.value, template_key: purpose.value, category: selected.dataset.category, display_name: form.elements.displayName.value, subject: form.elements.channel.value === "EMAIL" ? form.elements.subject.value : null, body: form.elements.body.value, signature: isSms ? null : (form.elements.signature.value || null), generation_prompt: isSms ? null : (form.elements.prompt.value || null), status: form.elements.status.value }) });
    const result = await response.json();
    status.textContent = response.ok ? `Version ${result.version} saved.` : (result.detail || "Template could not be saved.");
    if (response.ok) loadNotificationTemplates(root);
  });
  syncPurpose();
  loadNotificationTemplates(root);
}

function aiCostDashboardView() {
  return `<div class="admin-ai-costs">
    <section class="admin-ai-source"><div><p class="eyebrow">Read-only production registry</p><h2>Promoted models from Cost Lab</h2><p>Providers, models, approved qualities, priority, and pricing shown here come directly from the active Cost Lab production registry.</p></div><a class="button button--primary" href="/admin/cost-lab/promoted-models">Open Cost Lab to add or edit</a></section>
    <div id="admin-ai-cost-summary" class="admin-platform-metrics admin-ai-summary">Loading AI cost data…</div>
    <section class="admin-ai-section"><div class="admin-section-heading"><div><h2>Model providers</h2><p>Providers represented by active promoted models.</p></div><span>Managed in Cost Lab</span></div><div id="admin-ai-providers" class="admin-data-panel"></div></section>
    <section class="admin-ai-section"><div class="admin-section-heading"><div><h2>Promoted models and cost</h2><p>Only active production releases are displayed. Pricing is the current Cost Lab promotion snapshot.</p></div><span>Read only</span></div><div id="admin-ai-models" class="admin-data-panel"></div></section>
  </div>`;
}

const usdMicros = (value) => `$${(Number(value || 0) / 1000000).toFixed(4)}`;
const promotedPrice = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(Number(value || 0));

function promotedPricing(model) {
  const prices = model.pricing_snapshot || [];
  if (!prices.length) return '<span class="admin-model-price"><small>No pricing snapshot</small></span>';
  return `<span class="admin-model-price">${prices.map((item) => {
    const unit = item.unit === "output_images" ? `${displayEnum(item.quality || "Any")} image` : `${displayEnum(item.unit)} / 1M`;
    return `<small>${escapeHtml(unit)}</small><strong>${escapeHtml(promotedPrice(item.price_usd))}</strong>`;
  }).join("")}</span>`;
}

async function loadAiCosts(root) {
  const response = await fetch(`${API_ROOT}/admin/ai-costs`, { credentials: "same-origin" });
  if (!response.ok) {
    root.querySelector("#admin-ai-cost-summary").innerHTML = '<div class="admin-error-state"><strong>Promoted models could not be loaded.</strong><p>Refresh the page or open Cost Lab to verify the production registry.</p></div>';
    return;
  }
  const data = await response.json();
  const pricedModels = data.models.filter((model) => (model.pricing_snapshot || []).length).length;
  root.querySelector("#admin-ai-cost-summary").innerHTML = `<article class="admin-metric-card"><span>Production providers</span><strong>${data.providers.length}</strong><small>From promoted models</small></article><article class="admin-metric-card"><span>Promoted models</span><strong>${data.models.length}</strong><small>Active production releases</small></article><article class="admin-metric-card"><span>Models with pricing</span><strong>${pricedModels}</strong><small>Cost Lab pricing snapshots</small></article>`;
  root.querySelector("#admin-ai-providers").innerHTML = data.providers.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Provider</th><th>Type</th><th>Promoted models</th><th>Cost Lab status</th></tr></thead><tbody>${data.providers.map((provider) => `<tr><td><strong>${escapeHtml(provider.provider_name)}</strong>${provider.api_base_url ? `<br><small>${escapeHtml(provider.api_base_url)}</small>` : ""}</td><td>${escapeHtml(displayEnum(provider.provider_type))}</td><td>${escapeHtml(provider.promoted_model_count)}</td><td><span class="admin-status admin-status--${provider.provider_enabled ? "active" : "failed"}">${provider.provider_enabled ? "Enabled" : "Disabled"}</span></td></tr>`).join("")}</tbody></table></div>` : '<div class="admin-ai-empty"><span>◇</span><div><strong>No production providers</strong><p>Promote a model in Cost Lab to display its provider here.</p></div><a class="button button--quiet" href="/admin/cost-lab/promoted-models">Open Cost Lab</a></div>';
  root.querySelector("#admin-ai-models").innerHTML = data.models.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Priority</th><th>Provider</th><th>Model</th><th>Approved qualities</th><th>Cost</th><th>Promoted</th></tr></thead><tbody>${data.models.map((model) => `<tr><td><strong>${escapeHtml(model.priority ?? "—")}</strong></td><td><strong>${escapeHtml(model.provider_name)}</strong><br><small>${escapeHtml(displayEnum(model.provider_type))}</small></td><td><strong>${escapeHtml(model.model_name)}</strong><br><code>${escapeHtml(model.api_identifier)}</code>${model.model_version ? `<br><small>Version ${escapeHtml(model.model_version)}</small>` : ""}${!model.model_enabled ? '<br><span class="admin-status admin-status--failed">Disabled in Cost Lab</span>' : ""}</td><td>${(model.approved_quality_levels || []).map((quality) => `<span class="admin-status cost-quality-badge">${escapeHtml(quality)}</span>`).join(" ")}</td><td>${promotedPricing(model)}${model.pricing_effective_at ? `<small class="admin-ai-price-date">Effective ${escapeHtml(new Date(model.pricing_effective_at).toLocaleString())}</small>` : ""}</td><td>${escapeHtml(new Date(model.promoted_at).toLocaleString())}<br><small>by ${escapeHtml(model.promoted_by)}</small></td></tr>`).join("")}</tbody></table></div>` : '<div class="admin-ai-empty"><span>◎</span><div><strong>No promoted models</strong><p>Complete a final check and promote a model in Cost Lab to display it here.</p></div><a class="button button--primary" href="/admin/cost-lab/promoted-models">Open Cost Lab</a></div>';
}

function attachAiCostDashboard(root) {
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
  table.innerHTML = data.try_ons.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Started</th><th>Try-on</th><th>Status</th><th>Generation time</th><th>Input tokens</th><th>Output tokens</th><th>Cost</th><th>Provider / model</th><th>Failure</th></tr></thead><tbody>${data.try_ons.map((item) => `<tr><td>${escapeHtml(new Date(item.created_at).toLocaleTimeString())}</td><td><small>${escapeHtml(item.job_id)}</small></td><td><span class="admin-status admin-status--${escapeHtml(String(item.status).toLowerCase())}">${escapeHtml(displayEnum(item.status))}</span></td><td>${["PENDING", "PROCESSING"].includes(item.status) ? "In progress" : escapeHtml(formatDuration(item.generation_time_ms))}</td><td>${escapeHtml(Number(item.input_tokens || 0).toLocaleString())}</td><td>${escapeHtml(Number(item.output_tokens || 0).toLocaleString())}</td><td>${usdMicros(item.cost_usd_micros)} <small>${escapeHtml(String(item.cost_basis).toLowerCase())}</small></td><td>${escapeHtml(item.provider)}<br><small>${escapeHtml(item.model_version)}</small></td><td>${escapeHtml(item.error_code ? displayEnum(item.error_code) : "—")}</td></tr>`).join("")}</tbody></table></div>` : '<p class="admin-empty">No try-ons in this window.</p>';
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
  const retailForm = root.querySelector("#retail-tryon-price-form");
  const retailPreview = root.querySelector("#retail-token-preview");
  const retailCurrent = root.querySelector("#admin-retail-pricing-current");
  const packageForm = root.querySelector("#retail-tryon-package-form");
  const packagePreview = root.querySelector("#retail-package-preview");
  const packageList = root.querySelector("#admin-retail-package-list");
  let currentTokensPerTryOn = 0;
  let retailPackages = [];
  let editingPackageId = null;
  const resetPackageForm = () => {
    editingPackageId = null;
    packageForm.reset();
    packageForm.elements.gst.value = "18";
    root.querySelector("#retail-package-form-title").textContent = "Create try-on package";
    root.querySelector("#retail-package-submit").innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg><span>Create package</span>';
    root.querySelector("#retail-package-cancel-edit").hidden = true;
    renderPackagePreview();
  };
  const renderPackagePreview = () => {
    const amount = Number(packageForm.elements.amount.value);
    if (!(amount > 0)) return void (packagePreview.textContent = "Enter a minimum amount");
    const gst = Number(packageForm.elements.gst.value || 0);
    const tokens = amount * 5;
    const finalAmount = amount * (1 + gst / 100);
    packagePreview.textContent = currentTokensPerTryOn
      ? `${tokens} tokens · ${Math.floor(tokens / currentTokensPerTryOn)} try-ons · ₹${finalAmount.toFixed(2)} including GST`
      : `${tokens} tokens · ₹${finalAmount.toFixed(2)} including GST · publish a try-on price to calculate try-ons`;
  };
  const renderRetailPreview = () => {
    const price = Number(retailForm.elements.price.value);
    retailPreview.textContent = price > 0 ? `${(price * 10) / 2} tokens per try-on` : "Enter a price";
  };
  const loadRetailPrice = async () => {
    const response = await fetch(`${API_ROOT}/admin/pricing/retail-tryon`, { credentials: "same-origin" });
    if (response.status === 401) return redirect("/admin");
    if (!response.ok) return void (retailCurrent.textContent = "Website price could not be loaded.");
    const data = await response.json();
    currentTokensPerTryOn = Number(data.current?.tokens_per_tryon || 0);
    retailPackages = data.packages || [];
    retailCurrent.innerHTML = data.current
      ? `<small>Currently published</small><strong>₹${(Number(data.current.price_minor) / 100).toFixed(2)} · ${escapeHtml(data.current.tokens_per_tryon)} tokens per try-on</strong><span>Effective ${escapeHtml(new Date(data.current.effective_from).toLocaleString())}</span>`
      : "No retail try-on price is currently published.";
    packageList.innerHTML = retailPackages.length
      ? retailPackages.map((item) => `<div class="admin-retail-package__row"><span><strong>${escapeHtml(item.name)}</strong><small>₹${(Number(item.final_amount_minor) / 100).toFixed(2)} including ${(Number(item.gst_basis_points) / 100).toFixed(2)}% GST · ${escapeHtml(item.total_tokens)} tokens · ${escapeHtml(item.number_of_tryons)} try-ons</small></span><span class="form-actions"><button class="admin-icon-action admin-icon-action--edit" type="button" data-package-edit="${escapeHtml(item.retail_package_id)}" aria-label="Edit ${escapeHtml(item.name)} package" title="Edit package"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg></button><button class="admin-icon-action admin-icon-action--delete" type="button" data-package-delete="${escapeHtml(item.retail_package_id)}" aria-label="Delete ${escapeHtml(item.name)} package" title="Delete package"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="m19 6-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></button></span></div>`).join("")
      : "No B2C packages created yet.";
    renderPackagePreview();
  };
  retailForm.elements.price.addEventListener("input", renderRetailPreview);
  retailForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = retailForm.querySelector(".form-status");
    const priceMinor = Math.round(Number(retailForm.elements.price.value) * 100);
    status.textContent = "Publishing website price…";
    const response = await fetch(`${API_ROOT}/admin/pricing/retail-tryon`, {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ price_minor: priceMinor, reason: retailForm.elements.reason.value }),
    });
    const result = await response.json();
    status.textContent = response.ok
      ? `Published ₹${(Number(result.price_minor) / 100).toFixed(2)} as ${result.tokens_per_tryon} tokens per try-on. Existing pricing was not changed.`
      : result.message || "Website price could not be published.";
    if (response.ok) { retailForm.reset(); renderRetailPreview(); loadRetailPrice(); }
  });
  packageForm.elements.amount.addEventListener("input", renderPackagePreview);
  packageForm.elements.gst.addEventListener("input", renderPackagePreview);
  root.querySelector("#retail-package-cancel-edit").addEventListener("click", resetPackageForm);
  packageList.addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-package-edit]");
    const remove = event.target.closest("[data-package-delete]");
    if (edit) {
      const item = retailPackages.find((value) => value.retail_package_id === edit.dataset.packageEdit);
      if (!item) return;
      editingPackageId = item.retail_package_id;
      packageForm.elements.name.value = item.name;
      packageForm.elements.amount.value = (Number(item.minimum_amount_minor) / 100).toFixed(2);
      packageForm.elements.gst.value = (Number(item.gst_basis_points) / 100).toFixed(2);
      packageForm.elements.reason.value = "";
      root.querySelector("#retail-package-form-title").textContent = `Edit ${item.name}`;
      root.querySelector("#retail-package-submit").innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg><span>Save changes</span>';
      root.querySelector("#retail-package-cancel-edit").hidden = false;
      renderPackagePreview();
      packageForm.elements.name.focus();
      return;
    }
    if (!remove) return;
    const item = retailPackages.find((value) => value.retail_package_id === remove.dataset.packageDelete);
    if (!item || !(await wearoConfirm({ eyebrow: "B2C packages", title: `Delete ${item.name}?`, message: "This package will immediately disappear from the B2C pricing page.", note: "The audit record is retained and existing historical records are not deleted.", confirmLabel: "Delete package" }))) return;
    const response = await fetch(`${API_ROOT}/admin/pricing/retail-tryon/packages/${encodeURIComponent(item.retail_package_id)}`, { method: "DELETE", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Deleted by super admin from the pricing console." }) });
    const result = await response.json();
    if (!response.ok) return void wearoAlert({ title: "Package was not deleted", message: result.message || "Try again." });
    if (editingPackageId === item.retail_package_id) resetPackageForm();
    await loadRetailPrice();
  });
  packageForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = packageForm.querySelector(".form-status");
    status.textContent = "Creating package…";
    const path = editingPackageId ? `/admin/pricing/retail-tryon/packages/${encodeURIComponent(editingPackageId)}` : "/admin/pricing/retail-tryon/packages";
    const response = await fetch(`${API_ROOT}${path}`, {
      method: editingPackageId ? "PUT" : "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: packageForm.elements.name.value, minimum_amount_minor: Math.round(Number(packageForm.elements.amount.value) * 100), gst_basis_points: Math.round(Number(packageForm.elements.gst.value) * 100), reason: packageForm.elements.reason.value }),
    });
    const result = await response.json();
    status.textContent = response.ok
      ? `${result.name} ${editingPackageId ? "updated" : "created"} with ${result.total_tokens} tokens and ${result.number_of_tryons} try-ons.`
      : result.message || "Package could not be created.";
    if (response.ok) { resetPackageForm(); loadRetailPrice(); }
  });
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
  loadRetailPrice();
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
    if (!await wearoConfirm({ eyebrow: "Platform operations", title: `${action === "PAUSE" ? "Pause" : "Resume"} try-ons?`, message: `This will ${action === "PAUSE" ? "stop new" : "allow new"} try-ons for the selected scope.`, note: "The change is recorded in the audit history.", confirmLabel: action === "PAUSE" ? "Pause try-ons" : "Resume try-ons", cancelLabel: "Keep current state", tone: action === "PAUSE" ? "danger" : "info" })) return;
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

function attachServiceHealth(root) {
  const button = root.querySelector("#service-health-sync");
  const buttonLabel = button.querySelector("span");
  const summary = root.querySelector("#service-health-summary");
  const list = root.querySelector("#service-health-list");
  const count = root.querySelector("#service-health-count");
  const sync = async () => {
    button.disabled = true;
    button.classList.add("is-syncing");
    buttonLabel.textContent = "Refreshing…";
    summary.className = "service-health__summary is-loading";
    summary.innerHTML = '<span class="service-health__summary-icon"><i></i></span><div><small>Overall platform status</small><strong>Checking services…</strong><p>Contacting each configured health endpoint.</p></div>';
    try {
      const response = await fetch(`${API_ROOT}/admin/service-health`, { credentials: "same-origin", cache: "no-store" });
      if (response.status === 401) return redirect("/admin");
      if (!response.ok) throw new Error("Health API unavailable");
      const data = await response.json();
      const healthyCount = data.services.filter((service) => service.healthy).length;
      const healthy = healthyCount === data.services.length;
      summary.className = `service-health__summary ${healthy ? "is-healthy" : "is-unhealthy"}`;
      summary.innerHTML = `<span class="service-health__summary-icon">${healthy ? '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg>' : '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 8v5M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>'}</span><div><small>Overall platform status</small><strong>${healthy ? "All systems operational" : "Attention required"}</strong><p>${healthyCount} of ${data.services.length} services healthy · Checked ${escapeHtml(new Date(data.checked_at).toLocaleString())}</p></div>`;
      count.textContent = `${healthyCount} of ${data.services.length} healthy`;
      list.innerHTML = data.services.map((service) => `<article class="service-health__card ${service.healthy ? "is-healthy" : "is-unhealthy"}"><div class="service-health__card-heading"><span class="service-health__service-icon"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="16" height="6" rx="2"/><rect x="4" y="14" width="16" height="6" rx="2"/><path d="M8 7h.01M8 17h.01M12 7h5M12 17h5"/></svg></span><div><small>Runtime service</small><h3>${escapeHtml(service.name)}</h3></div></div><div class="service-health__status-cell"><span class="service-health__indicator" aria-hidden="true"></span><span class="service-health__badge">${service.healthy ? "Healthy" : "Issue"}</span></div><div class="service-health__card-detail"><p>${escapeHtml(service.detail)}</p></div><div class="service-health__card-meta"><strong>${escapeHtml(service.response_time_ms)} ms</strong></div></article>`).join("");
    } catch (_) {
      summary.className = "service-health__summary is-unavailable";
      summary.innerHTML = '<span class="service-health__summary-icon"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 8v5M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg></span><div><small>Health check unavailable</small><strong>Could not reach the monitoring API</strong><p>Confirm the latest API version is running, then refresh the status again.</p></div>';
      count.textContent = "Status unavailable";
      list.innerHTML = '<div class="service-health__empty"><span><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 17h16M6 17V7h12v10M9 10h6M9 13h4"/></svg></span><div><h3>No service result received</h3><p>The monitoring endpoint did not return service data. Use Refresh status after the API has restarted.</p></div></div>';
    }
    button.disabled = false;
    button.classList.remove("is-syncing");
    buttonLabel.textContent = "Refresh status";
  };
  button.addEventListener("click", sync);
  sync();
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

function paymentMoney(minor) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(minor || 0) / 100);
}

function renderPaymentReport(root, data) {
  const summary = data.summary;
  const audience = data.audience.toLowerCase();
  const cards = [
    ["Total collected", paymentMoney(summary.collected_minor), `${summary.transactions} total transactions`],
    ["Successful payments", Number(summary.paid).toLocaleString("en-IN"), "Gateway-confirmed payments"],
    ["Pending payments", Number(summary.pending).toLocaleString("en-IN"), audience === "b2b" ? `${summary.overdue} overdue` : "Awaiting confirmation"],
    ["Failed / refunded", `${summary.failed} / ${summary.refunded}`, `${paymentMoney(summary.refunded_minor)} refunded`],
    ["Average payment", paymentMoney(summary.average_payment_minor), "Across successful payments"],
    ["Tokens credited", Number(summary.tokens_credited).toLocaleString("en-IN"), "Credited after confirmation"],
  ];
  root.querySelector("#admin-payment-report-summary").innerHTML = cards.map(([label, value, detail]) => `<article><span>${label}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
  const list = root.querySelector("#admin-payment-report-list");
  if (!data.items.length) {
    list.innerHTML = '<p class="admin-empty">No payments match this reporting period and status.</p>';
    return;
  }
  const counterparty = audience === "b2c" ? "Consumer" : "Business";
  list.innerHTML = `<div class="admin-table-wrap"><table class="admin-table admin-payment-table"><thead><tr><th>${counterparty}</th><th>Package / type</th><th>Status</th><th>Amount</th><th>Tokens</th><th>Receipt / invoice</th><th>Created</th><th>Paid / refunded</th></tr></thead><tbody>${data.items.map((item) => {
    const reference = item.invoice_id
      ? `<a href="${API_ROOT}/admin/billing/invoices/${encodeURIComponent(item.invoice_id)}.txt">${escapeHtml(item.invoice_number)}</a>`
      : escapeHtml(item.receipt_number || item.provider_payment_id || item.provider_order_id || "Awaiting payment");
    const tokenDetail = item.payment_status === "REFUNDED" ? `${Number(item.tokens_reversed || 0).toLocaleString("en-IN")} reversed` : Number(item.tokens_credited || item.ordered_tokens || 0).toLocaleString("en-IN");
    const completedAt = item.refunded_at || item.paid_at;
    return `<tr><td><strong>${escapeHtml(item.customer_name)}</strong><small>${escapeHtml(item.payment_order_id)}</small></td><td>${escapeHtml(item.package_name)}<small>${escapeHtml(displayEnum(item.revenue_type))}</small></td><td><span class="admin-status admin-status--${escapeHtml(item.payment_status.toLowerCase())}">${escapeHtml(displayEnum(item.payment_status))}</span></td><td><strong>${escapeHtml(paymentMoney(item.amount_minor))}</strong>${item.tax_minor != null ? `<small>Tax ${escapeHtml(paymentMoney(item.tax_minor))}</small>` : ""}</td><td>${escapeHtml(tokenDetail)}</td><td>${reference}</td><td>${escapeHtml(new Date(item.created_at).toLocaleString())}</td><td>${completedAt ? escapeHtml(new Date(completedAt).toLocaleString()) : "—"}</td></tr>`;
  }).join("")}</tbody></table></div>`;
}

async function loadPaymentReport(root) {
  const form = root.querySelector("#admin-payment-report-filter");
  const summary = root.querySelector("#admin-payment-report-summary");
  const list = root.querySelector("#admin-payment-report-list");
  const period = new FormData(form).get("period");
  const range = dashboardDateRange(period, form);
  if (!range.from || !range.to) {
    list.innerHTML = '<div class="admin-error-state admin-error-state--compact"><strong>Choose both custom dates.</strong></div>';
    return;
  }
  const audience = root.querySelector(".admin-payments").dataset.paymentAudience;
  const parameters = new URLSearchParams({ date_from: range.from, date_to: range.to });
  if (form.elements.status.value) parameters.set("status", form.elements.status.value);
  summary.querySelectorAll("article").forEach((card) => card.classList.add("is-loading"));
  list.innerHTML = '<div class="admin-loading-state"><span></span><strong>Loading payments</strong></div>';
  const response = await fetch(`${API_ROOT}/admin/payments/${audience}?${parameters}`, { credentials: "same-origin" });
  if (response.status === 401) return redirect("/admin");
  const data = await response.json();
  if (!response.ok) {
    summary.innerHTML = `<div class="admin-error-state"><strong>Payment summary is unavailable</strong><p>${escapeHtml(data.message || "Try this report again.")}</p></div>`;
    list.innerHTML = '<p class="admin-empty">Transactions could not be loaded.</p>';
    return;
  }
  root.querySelector("#admin-payment-period-label").textContent = `${new Date(`${range.from}T00:00:00`).toLocaleDateString()} – ${new Date(`${range.to}T00:00:00`).toLocaleDateString()}`;
  renderPaymentReport(root, data);
}

function attachPaymentControls(root) {
  const form = root.querySelector("#admin-payment-report-filter");
  if (!form) return;
  const today = isoDate(new Date());
  form.elements.dateFrom.value = today;
  form.elements.dateTo.value = today;
  form.addEventListener("change", (event) => {
    if (event.target.name !== "period") return;
    const custom = event.target.value === "custom";
    root.querySelector("#admin-payment-custom-dates").hidden = !custom;
    form.elements.dateFrom.required = custom;
    form.elements.dateTo.required = custom;
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); loadPaymentReport(root); });
  loadPaymentReport(root);
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
    ["Wearo tokens consumed", values.total_tokens_consumed],
    ["Provider input tokens", Number(values.provider_input_tokens || 0).toLocaleString()],
    ["Provider output tokens", Number(values.provider_output_tokens || 0).toLocaleString()],
    ["Provider total tokens", Number(values.provider_total_tokens || 0).toLocaleString()],
    ["Provider cost", `$${(Number(values.provider_cost_usd_micros || 0) / 1_000_000).toFixed(4)}`],
    ["Average cost / generation", `$${(Number(values.average_cost_per_generation_usd_micros || 0) / 1_000_000).toFixed(4)}`],
    ["Try-ons / second", Number(values.try_ons_per_second || 0).toFixed(6)],
    ["Average try-ons per business", values.average_try_ons_per_organization],
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
  const navigation = ADMIN_SECTIONS.map((section) => {
    if (section.slug !== "payments") return `<a href="/admin/${section.slug}" ${section.slug === active.slug ? 'aria-current="page"' : ""}><span aria-hidden="true">${section.icon}</span><span>${section.label}</span></a>`;
    const audience = paymentAudience(pathname);
    return `<div class="admin-navigation__group ${active.slug === "payments" ? "is-active" : ""}"><a href="/admin/payments/b2c" ${active.slug === "payments" ? 'data-section-active="true"' : ""}><span aria-hidden="true">${section.icon}</span><span>${section.label}</span><span class="admin-navigation__chevron" aria-hidden="true">⌄</span></a><div class="admin-navigation__submenu"><a href="/admin/payments/b2c" ${active.slug === "payments" && audience === "b2c" ? 'aria-current="page"' : ""}>B2C payments</a><a href="/admin/payments/b2b" ${active.slug === "payments" && audience === "b2b" ? 'aria-current="page"' : ""}>B2B payments</a></div></div>`;
  }).join("");
  return `<div class="business-app admin-app">
    <aside class="business-sidebar admin-sidebar">
      <div class="business-sidebar__brand admin-sidebar__brand"><a class="brand-white-bg" href="/admin/dashboard"><img src="/wearo-brand_white_bg.png?v=20261108-white-2" alt="Wearo.ai" /></a><span>Admin</span></div>
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
  list.innerHTML = `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Organization</th><th>Business type</th><th>AI advertisements</th><th>Onboarded</th><th>Subscription</th><th>Operational status</th><th><span class="sr-only">Action</span></th></tr></thead><tbody>${result.organizations.map((organization) => `<tr><td><strong>${escapeHtml(organization.organization_name)}</strong></td><td>${escapeHtml(displayEnum(organization.business_type))}</td><td>${escapeHtml(organization.advertisement_generations)}</td><td>${escapeHtml(new Date(organization.onboarding_date).toLocaleDateString())}</td><td><span class="admin-status">${escapeHtml(displayEnum(organization.subscription_status))}</span></td><td><span class="admin-status admin-status--${escapeHtml(String(organization.operational_status).toLowerCase())}">${escapeHtml(displayEnum(organization.operational_status))}</span></td><td><a href="/admin/organizations/${escapeHtml(organization.tenant_id)}" data-organization-link>View</a></td></tr>`).join("")}</tbody></table></div>`;
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
  const stores = organization.stores.length
    ? organization.stores.map((store) => `<tr><td><strong>${escapeHtml(store.store_name)}</strong><br><small>${escapeHtml(store.code)}</small></td><td><span class="admin-status admin-status--${escapeHtml(String(store.status).toLowerCase())}">${escapeHtml(displayEnum(store.status))}</span></td><td>${escapeHtml(store.advertisement_generations)}</td></tr>`).join("")
    : '<tr><td colspan="3">No stores are configured.</td></tr>';
  panel.innerHTML = `<a class="admin-back-link" href="/admin/organizations">← All businesses</a><h2>${escapeHtml(organization.organization_name)}</h2>
    <div class="admin-stat-grid"><article><span>Available tokens</span><strong id="detail-token-balance">${escapeHtml(organization.available_tokens)}</strong></article><article><span>Tokens consumed</span><strong>${escapeHtml(organization.tokens_consumed)}</strong></article><article><span>Total try-ons</span><strong>${escapeHtml(organization.total_try_ons)}</strong></article><article><span>AI advertisements generated</span><strong>${escapeHtml(organization.advertisement_generations)}</strong></article></div>
    <dl class="admin-detail-grid"><div><dt>Business type</dt><dd>${escapeHtml(displayEnum(organization.business_type))}</dd></div><div><dt>Onboarding date</dt><dd>${escapeHtml(new Date(organization.onboarding_date).toLocaleDateString())}</dd></div><div><dt>Subscription plan</dt><dd>${escapeHtml(organization.plan_code || "Unassigned")}</dd></div><div><dt>Subscription status</dt><dd>${escapeHtml(displayEnum(organization.subscription_status))}</dd></div><div><dt>Operational status</dt><dd id="detail-operational-status">${escapeHtml(displayEnum(organization.operational_status))}</dd></div><div><dt>Billing status</dt><dd>${escapeHtml(displayEnum(organization.billing_status))}</dd></div><div><dt>Legal name</dt><dd>${escapeHtml(organization.legal_name)}</dd></div><div><dt>Jurisdiction</dt><dd>${escapeHtml(organization.jurisdiction)}</dd></div><div><dt>Billing email</dt><dd>${escapeHtml(organization.billing_email)}</dd></div><div><dt>Billing phone</dt><dd>${escapeHtml(organization.billing_phone || "Not provided")}</dd></div><div><dt>Website</dt><dd>${escapeHtml(organization.website_url || "Not provided")}</dd></div></dl>
    ${subscription ? `<section class="admin-subscription-panel"><h3>Subscription lifecycle</h3><dl class="admin-detail-grid"><div><dt>State</dt><dd id="subscription-state">${escapeHtml(displayEnum(subscription.state))}</dd></div><div><dt>Plan</dt><dd id="subscription-plan">${escapeHtml(subscription.plan_code)}</dd></div><div><dt>Start date</dt><dd>${escapeHtml(new Date(subscription.started_at).toLocaleDateString())}</dd></div><div><dt>Next billing date</dt><dd id="subscription-next-billing">${subscription.next_billing_at ? escapeHtml(new Date(subscription.next_billing_at).toLocaleDateString()) : "Not scheduled"}</dd></div><div><dt>Trial ends</dt><dd id="subscription-trial-end">${subscription.trial_ends_at ? escapeHtml(new Date(subscription.trial_ends_at).toLocaleDateString()) : "Not applicable"}</dd></div><div><dt>Admin operational state</dt><dd>${escapeHtml(displayEnum(organization.operational_status))}</dd></div></dl>
    <form id="subscription-transition-form"><label>Reason<input name="reason" required maxlength="500" /></label><div class="admin-action-row"><button name="action" value="START_TRIAL" class="button button--quiet">Start trial</button><button name="action" value="ACTIVATE" class="button button--quiet">Activate / Reactivate</button><button name="action" value="MARK_PAYMENT_DUE" class="button button--quiet">Mark payment due</button><button name="action" value="PAUSE" class="button button--quiet">Customer pause</button><button name="action" value="CANCEL" class="button button--danger">Cancel</button><button name="action" value="EXPIRE" class="button button--quiet">Expire</button></div><p class="form-status" role="status"></p></form>
    <div class="admin-control-grid"><form id="subscription-plan-form"><h3>Assign or change plan</h3><label>Plan code<input name="planCode" value="${escapeHtml(subscription.plan_code)}" required maxlength="40" /></label><label>Next billing date<input name="nextBilling" type="datetime-local" /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Save plan</button><p class="form-status" role="status"></p></form><form id="trial-extension-form"><h3>Extend trial</h3><label>Additional days<input name="days" type="number" min="1" max="365" required /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Extend trial</button><p class="form-status" role="status"></p></form></div></section>` : ""}
    <section class="admin-control-grid"><form id="organization-status-control"><h3>Admin operational controls</h3><p class="field-help">This pause is independent from a customer-paused subscription.</p><label>Reason<input name="reason" required maxlength="500" /></label><div class="admin-action-row"><button name="action" value="ACTIVATE" class="button button--quiet">Activate</button><button name="action" value="PAUSE" class="button button--quiet">Admin pause</button><button name="action" value="RESUME" class="button button--quiet">Resume</button><button name="action" value="DEACTIVATE" class="button button--danger">Deactivate</button></div><p class="form-status" role="status"></p></form>
    <form id="organization-token-control"><h3>Manual token adjustment</h3><label>Token amount<input name="amount" type="number" min="-1000000" max="1000000" required /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Apply adjustment</button><p class="form-status" role="status"></p></form>
    <form id="organization-tryon-limit-control"><h3>B2B2C customer allowance</h3><p class="field-help">Set the free try-ons available to each customer in this business's 24-hour session.</p><label>Try-ons per customer<input name="limit" type="number" min="0" max="100000" value="${escapeHtml(organization.customer_try_on_limit ?? 0)}" required /></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--primary">Update allowance</button><p class="form-status" role="status"></p></form></section>
    <section class="admin-payment-history"><h3>Advertisement generations by store</h3><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Store</th><th>Status</th><th>AI advertisements generated</th></tr></thead><tbody>${stores}</tbody></table></div></section>
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
  const tryOnLimitForm = panel.querySelector("#organization-tryon-limit-control");
  tryOnLimitForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(tryOnLimitForm);
    const status = tryOnLimitForm.querySelector(".form-status");
    const update = await fetch(`${API_ROOT}/admin/organizations/${encodeURIComponent(panel.dataset.tenantId)}/customer-try-on-limit`, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit: Number(data.get("limit")), reason: data.get("reason") }) });
    const result = await update.json();
    if (!update.ok) return void (status.textContent = result.message || "Allowance update failed.");
    tryOnLimitForm.elements.limit.value = result.customer_try_on_limit;
    tryOnLimitForm.elements.reason.value = "";
    status.textContent = "B2B2C customer allowance updated and audited.";
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

function supportPaymentMarkup(payment) {
  if (!payment) return '<section class="admin-support-payment admin-support-payment--empty"><div class="admin-support-section-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M7 3h10v18l-2.5-1.7L12 21l-2.5-1.7L7 21V3Z"/><path d="M10 8h4M10 12h4"/></svg></div><div><strong>No payment history</strong><p>This account has not created a payment order yet.</p></div></section>';
  const amount = new Intl.NumberFormat("en-IN", { style: "currency", currency: payment.currency || "INR" }).format(Number(payment.amount_minor || 0) / 100);
  const date = new Date(payment.paid_at || payment.updated_at || payment.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
  return `<section class="admin-support-payment"><header><div class="admin-support-section-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h10v18l-2.5-1.7L12 21l-2.5-1.7L7 21V3Z"/><path d="M10 8h4M10 12h4"/></svg></div><div><small>Most recent transaction</small><h3>Latest payment</h3></div><span class="admin-status admin-status--${escapeHtml(String(payment.state).toLowerCase())}">${escapeHtml(displayEnum(payment.state))}</span></header><div class="admin-support-payment__amount"><span>${escapeHtml(payment.package_name || "Token purchase")}</span><strong>${escapeHtml(amount)}</strong><small>${escapeHtml(date)}</small></div><dl><div><dt>Tokens purchased</dt><dd>${Number(payment.tokens || 0).toLocaleString("en-IN")}</dd></div><div><dt>Try-ons included</dt><dd>${payment.number_of_try_ons == null ? "—" : Number(payment.number_of_try_ons).toLocaleString("en-IN")}</dd></div><div><dt>Receipt number</dt><dd>${escapeHtml(payment.receipt_number || "Not issued")}</dd></div><div><dt>Gateway reference</dt><dd>${escapeHtml(payment.provider_payment_id || "Not available")}</dd></div></dl></section>`;
}

function renderSupportResults(root, results) {
  const target = root.querySelector("#admin-support-results");
  if (!results.length) {
    target.innerHTML = '<div class="admin-support-empty"><span aria-hidden="true">?</span><strong>No matching account</strong><p>Check the verified email address or phone number and search again.</p></div>';
    return;
  }
  target.innerHTML = results.map((user, index) => `<article class="admin-support-customer" data-support-account="${escapeHtml(user.account_id)}"><header class="admin-support-customer__header"><div class="admin-support-avatar" aria-hidden="true">${escapeHtml((user.business_name || user.normalized_value).charAt(0).toUpperCase())}</div><div><div class="admin-support-customer__badges"><span>${escapeHtml(user.customer_type)}</span><span class="admin-status admin-status--${escapeHtml(String(user.account_status).toLowerCase())}">${escapeHtml(displayEnum(user.account_status))}</span></div><h2>${escapeHtml(user.business_name || user.normalized_value)}</h2><p><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 6h16v12H4z"/><path d="m4 7 8 6 8-6"/></svg>${escapeHtml(user.normalized_value)}${user.business_slug ? `<span>·</span>${escapeHtml(user.business_slug)}` : ""}</p></div><span class="admin-support-result-number">${String(index + 1).padStart(2, "0")}</span></header><div class="admin-support-summary"><article><span class="admin-support-summary__icon"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M8.5 10h7M8.5 14h5"/></svg></span><div><small>Available balance</small><strong data-support-token-balance>${Number(user.token_balance || 0).toLocaleString("en-IN")}</strong><span>Wearo Tokens</span></div></article><article><span class="admin-support-summary__icon"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 3 4 7v5c0 4.5 3.2 7.5 8 9 4.8-1.5 8-4.5 8-9V7l-8-4Z"/><path d="m9 12 2 2 4-4"/></svg></span><div><small>Available capacity</small><strong data-support-tryons>${user.try_ons_remaining == null ? "—" : Number(user.try_ons_remaining).toLocaleString("en-IN")}</strong><span>Estimated try-ons</span></div></article></div><div class="admin-support-details">${supportPaymentMarkup(user.latest_payment)}<form class="admin-support-credit"><header><div class="admin-support-section-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/></svg></div><div><small>Support adjustment</small><h3>Add tokens manually</h3></div></header><p>Issue an append-only, audited credit without changing payment history.</p><div class="admin-support-credit__fields"><label>Tokens to add<input name="amount" type="number" min="1" max="1000000" required placeholder="e.g. 50" /></label><label>Support reason<input name="reason" required maxlength="500" placeholder="Support case or approved correction" /></label></div><button class="button button--primary admin-action-with-icon" type="submit"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/><circle cx="12" cy="12" r="9"/></svg><span>Add tokens</span></button><p class="form-status" role="status" aria-live="polite"></p></form></div></article>`).join("");
  target.querySelectorAll(".admin-support-credit").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const card = form.closest("[data-support-account]");
    const status = form.querySelector(".form-status");
    const values = new FormData(form);
    const button = form.querySelector("button");
    button.disabled = true;
    status.textContent = "Adding audited token credit…";
    try {
      const response = await fetch(`${API_ROOT}/admin/support/customers/${encodeURIComponent(card.dataset.supportAccount)}/token-credits`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount: Number(values.get("amount")), reason: values.get("reason") }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "Token credit failed.");
      card.querySelector("[data-support-token-balance]").textContent = Number(result.token_balance).toLocaleString("en-IN");
      card.querySelector("[data-support-tryons]").textContent = result.try_ons_remaining == null ? "—" : Number(result.try_ons_remaining).toLocaleString("en-IN");
      form.reset();
      status.textContent = `${Number(result.tokens_added).toLocaleString("en-IN")} tokens added successfully.`;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }));
}

function attachSupport(root) {
  const form = root.querySelector("#admin-support-search");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = root.querySelector("#admin-support-status");
    const identity = new FormData(form).get("identity");
    status.textContent = "Searching verified identities…";
    try {
      const response = await fetch(`${API_ROOT}/admin/support/customers?identity=${encodeURIComponent(identity)}`, { credentials: "same-origin" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "User search failed.");
      status.textContent = `${result.results.length} matching account${result.results.length === 1 ? "" : "s"} found.`;
      renderSupportResults(root, result.results);
    } catch (error) {
      status.textContent = error.message;
      root.querySelector("#admin-support-results").innerHTML = "";
    }
  });
}

function renderAuthenticatedSection(root, pathname) {
  root.innerHTML = adminHomeView(pathname);
  root.querySelectorAll(".admin-navigation a, .admin-sidebar__brand a, .admin-route-link").forEach((link) => {
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
  if (adminSection(pathname).slug === "support") attachSupport(root);
  if (adminSection(pathname).slug === "enquiries") attachEnquiries(root);
  if (adminSection(pathname).slug === "dashboard") attachDashboardControls(root);
  if (adminSection(pathname).slug === "realtime") attachRealtimeDashboard(root);
  if (adminSection(pathname).slug === "ai-models-cost") attachAiCostDashboard(root);
  if (adminSection(pathname).slug === "customers-subscriptions") attachCustomerControls(root);
  if (adminSection(pathname).slug === "payments") attachPaymentControls(root);
  if (adminSection(pathname).slug === "billing-pricing") attachPricingControls(root);
  if (adminSection(pathname).slug === "notifications") attachNotificationControls(root);
  if (adminSection(pathname).slug === "platform-operations") attachTryOnOperations(root);
  if (adminSection(pathname).slug === "service-health") attachServiceHealth(root);
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
