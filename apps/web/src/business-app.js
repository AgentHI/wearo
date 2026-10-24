import { brandMarkup } from "./brand.js";

const API_BASE = "/api/v1";
const BUSINESS_AUTH_KEY = "wearo_business_auth";
let currentAgentAppUrl = "";

async function copyToClipboard(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const field = document.createElement("textarea");
  field.value = value; field.style.position = "fixed"; field.style.opacity = "0";
  document.body.append(field); field.select(); document.execCommand("copy"); field.remove();
}

function agentUrlFromShopLink(result) {
  return typeof result.agent_url === "string" ? result.agent_url.trim() : "";
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result));
    reader.addEventListener("error", () => reject(new Error("The company logo could not be read.")));
    reader.readAsDataURL(file);
  });
}

const sections = [
  ["dashboard", "Overview", "▦"],
  ["experience", "Wearo experience", "◇"],
  ["customers", "Customers", "♙"],
  ["agents", "Agent management", "♧"],
  ["billing", "Plans & billing", "▤"],
  ["settings", "Settings", "⚙"],
];

function businessFooter() {
  return `<footer class="business-footer">© 2026 All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>`;
}

function sectionFromPath(pathname) {
  if (pathname.startsWith("/business/sign-in")) return "sign-in";
  if (pathname.startsWith("/business/signup")) return "signup";
  return sections.find(([id]) => pathname.startsWith(`/business/${id}`))?.[0] || "welcome";
}

function readBusinessAuth() {
  try {
    const value = JSON.parse(sessionStorage.getItem(BUSINESS_AUTH_KEY) || "null");
    return value?.csrfToken ? value : null;
  } catch {
    return null;
  }
}

async function businessApi(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const auth = readBusinessAuth();
  if (auth?.csrfToken && options.method && !["GET", "HEAD"].includes(options.method)) {
    headers.set("X-CSRF-Token", auth.csrfToken);
  }
  let response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin", ...options, headers,
  });
  let body = await response.json().catch(() => ({}));
  const isMutation = options.method && !["GET", "HEAD"].includes(options.method);
  if (response.status === 403 && body.code === "AUTHENTICATION_REQUIRED" && isMutation) {
    const refresh = await fetch(`${API_BASE}/auth/business/csrf`, { credentials: "same-origin" });
    if (refresh.ok) {
      const refreshed = await refresh.json();
      sessionStorage.setItem(BUSINESS_AUTH_KEY, JSON.stringify({ csrfToken: refreshed.csrf_token }));
      headers.set("X-CSRF-Token", refreshed.csrf_token);
      response = await fetch(`${API_BASE}${path}`, { credentials: "same-origin", ...options, headers });
      body = await response.json().catch(() => ({}));
    }
  }
  if (!response.ok) {
    const validationMessage = Array.isArray(body.detail)
      ? body.detail
        .map((issue) => `${issue.loc?.at(-1) || "field"}: ${issue.msg || "invalid value"}`)
        .join(" · ")
      : null;
    throw new Error(body.message || validationMessage || "The request could not be completed.");
  }
  return body;
}

function businessFrame(section, content) {
  const navigation = sections
    .map(
      ([id, label, icon]) => `
        <a href="/business/${id}" ${section === id ? 'aria-current="page"' : ""}>
          <span class="business-nav__icon" aria-hidden="true">${icon}</span><span>${label}</span>
        </a>`,
    )
    .join("");
  return `
    <div class="business-app">
      <aside class="business-sidebar">
        <div class="business-sidebar__brand">${brandMarkup("/business")}<span>Business</span></div>
        <div class="workspace-switcher"><span class="workspace-switcher__mark">BW</span><span><small>Workspace</small><strong>Business workspace</strong></span><span aria-hidden="true">⌄</span></div>
        <p class="business-sidebar__label">Manage</p>
        <nav class="business-nav" aria-label="Business workspace">${navigation}</nav>
        <div class="business-sidebar__footer"><button id="business-logout" class="business-signout" type="button"><span aria-hidden="true">⇥</span> Sign out</button></div>
      </aside>
      <div class="business-workspace">
        <header class="business-topbar">
          <div class="business-breadcrumb"><strong>Business workspace</strong><span>/</span><span>${sections.find(([id]) => id === section)?.[1] || "Workspace"}</span></div>
          <div class="business-topbar__actions"><span class="environment-badge"><span class="availability-dot" aria-hidden="true"></span>Beta</span><a class="topbar-help" href="/business/settings">Help</a><div class="business-user" aria-label="Current user"><span>MA</span><div><strong>Workspace owner</strong><small>Administrator</small></div></div></div>
        </header>
        <main id="main" class="business-main">${content}</main>
        ${businessFooter()}
      </div>
    </div>`;
}

function welcomeView() {
  return `
    <div class="business-public">
      <header class="business-public__header">${brandMarkup("/business")}<nav><a class="button button--quiet" href="/business/sign-in">Sign in</a></nav></header>
      <main id="main">
        <section class="business-hero">
          <div>
            <p class="eyebrow">Virtual try-on for modern retail</p>
            <h1>Give shoppers confidence before they buy.</h1>
            <p class="lede">Add a privacy-first virtual try-on experience to your store, understand adoption, and manage every customer-facing surface from one workspace.</p>
            <div class="hero-actions"><a class="button button--primary" href="/business/signup">Start your workspace</a><a class="button button--quiet" href="/business/dashboard">Explore dashboard</a></div>
            <p class="microcopy">No card charged during beta · Customer photos stay private</p>
          </div>
          <div class="business-hero__visual" aria-label="Business dashboard preview">
            <div class="mini-window"><div class="mini-window__bar"><i></i><i></i><i></i></div><div class="mini-metrics"><span><strong>1,284</strong>try-ons</span><span><strong>38%</strong>engagement</span></div><div class="mini-chart" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div></div>
          </div>
        </section>
        <section class="business-features" aria-label="Product capabilities">
          <article><span>01</span><h2>Launch quickly</h2><p>Create a workspace, choose a plan, and connect Wearo to your existing business app.</p></article>
          <article><span>02</span><h2>Measure adoption</h2><p>See usage, completion, quality, and allowance signals without viewing private photos.</p></article>
          <article><span>03</span><h2>Stay in control</h2><p>Manage team access, consent language, retention policy, and provider availability.</p></article>
        </section>
      </main>
      ${businessFooter()}
    </div>`;
}

function signInView() {
  return `
    <div class="business-auth">
      <div class="business-auth__brand">${brandMarkup("/business")}</div>
      <main id="main" class="business-auth__main">
        <section class="auth-card">
          <p class="eyebrow">Business workspace</p><h1>Sign in securely.</h1>
          <p>Use the verified work email or primary mobile connected to your organisation.</p>
          <form id="business-signin-form">
            <label>Email or mobile<input name="destination" autocomplete="username" required /></label>
            <button id="business-request-code" class="button button--primary" type="button">Send sign-in code</button>
            <div id="business-code-step" class="code-step" hidden>
              <label>Sign-in code<input name="code" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" /></label>
              <button id="business-verify-code" class="button button--primary" type="button">Open workspace</button>
            </div>
            <p id="business-signin-status" class="form-status" role="status" aria-live="polite"></p>
          </form>
          <p class="auth-card__footer">Need a workspace? <a href="/business/signup">Create one</a></p>
        </section>
      </main>
      ${businessFooter()}
    </div>`;
}

function signupView() {
  return `
    <div class="business-auth">
      <div class="business-auth__brand">${brandMarkup("/business")}</div>
      <main id="main" class="business-auth__main">
        <section class="auth-card">
          <p class="eyebrow">Create your business workspace</p>
          <h1>Start with the essentials.</h1>
          <p class="hero__description">Set up your organisation now. Billing activation happens only after you explicitly confirm a payment provider checkout.</p>
          <form id="business-signup-form">
            <label>Business name<input name="businessName" autocomplete="organization" required /></label>
            <div class="signup-verification" data-verification="email"><label>Work email<input name="email" type="email" autocomplete="email" required /></label><button class="button button--quiet signup-send-code" type="button" data-channel="email">Send email OTP</button><div class="signup-code" data-code-for="email" hidden><label>Email OTP<input name="emailOtp" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" required disabled /></label><button class="button button--primary signup-verify-code" type="button" data-channel="email">Verify</button></div></div>
            <div class="signup-verification" data-verification="mobile"><label>Primary mobile<input name="primaryMobile" type="tel" autocomplete="tel" placeholder="+919876543210" required /></label><button class="button button--quiet signup-send-code" type="button" data-channel="mobile">Send mobile OTP</button><div class="signup-code" data-code-for="mobile" hidden><label>Mobile OTP<input name="mobileOtp" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" required disabled /></label><button class="button button--primary signup-verify-code" type="button" data-channel="mobile">Verify</button></div></div>
            <p id="signup-otp-status" class="notice" role="status" aria-live="polite">For local testing, use OTP 9876 for both email and mobile.</p>
            <label>Business type<select name="operatingProfile" required><option value="">Select type</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label>
            <div id="operating-profile-guidance" class="notice" role="status" aria-live="polite">Choose a type to see the matching Wearo experience guidance.</div>
            <label>Country code<input name="jurisdiction" value="IN" minlength="2" maxlength="2" required /></label>
            <label>Website <span>(optional)</span><input name="website" type="url" placeholder="https://" /></label>
            <label>Company logo <span>(optional)</span><input name="companyLogo" type="file" accept="image/png,image/jpeg,image/webp" /><small class="field-help">PNG, JPEG, or WebP up to 2 MB. Used on your QR poster.</small></label>
            <label class="check"><input name="taxInvoiceRequested" type="checkbox" /> I need tax-ready business invoices.</label>
            <fieldset id="invoice-details" hidden><legend>Invoice details</legend>
              <label>Legal business name<input name="legalName" autocomplete="organization" /></label>
              <label>Tax identifier <span>(required where applicable)</span><input name="taxIdentifier" /></label>
              <label>Billing address<input name="addressLine1" autocomplete="address-line1" /></label>
              <label>City<input name="city" autocomplete="address-level2" /></label>
              <label>Postal code<input name="postalCode" autocomplete="postal-code" /></label>
            </fieldset>
            <label class="check"><input name="terms" type="checkbox" required /> I agree to the beta terms and privacy commitments.</label>
            <button class="button button--primary" type="submit">Create workspace</button>
            <p id="business-signup-status" class="form-status" role="status" aria-live="polite"></p>
          </form>
          <p class="auth-card__footer">Already evaluating Wearo? <a href="/business/dashboard">Open the demo workspace</a></p>
        </section>
        <aside class="auth-proof"><blockquote>“The right experience is not just a model call. It is consent, quality, operations, and a clear customer promise.”</blockquote><p>Built into every Wearo workflow.</p></aside>
      </main>
      ${businessFooter()}
    </div>`;
}

function dashboardView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Workspace overview</p><h1 id="dashboard-greeting">Welcome.</h1><p>Monitor your virtual try-on operation and token consumption.</p></div><form id="overview-period" class="period-filter"><label><span>Reporting period</span><select name="period"><option value="today">Today</option><option value="week">Past week</option><option value="month" selected>Past month</option><option value="custom">Custom duration</option></select></label><div id="overview-custom-dates" class="period-filter__dates" hidden><label><span>From</span><input name="dateFrom" type="date" /></label><label><span>To</span><input name="dateTo" type="date" /></label><button class="button button--quiet" type="submit">Apply</button></div></form></header>
    <section class="metric-grid overview-metrics" aria-label="Workspace token and try-on summary">
      <article><div><p>Total tokens</p><span class="metric-icon">＋</span></div><strong id="overview-total-tokens">—</strong><small>Tokens purchased or credited</small></article>
      <article><div><p>Tokens consumed</p><span class="metric-icon">−</span></div><strong id="overview-tokens-used">—</strong><small>Used in the selected period</small></article>
      <article><div><p>Average tokens per try-on</p><span class="metric-icon">÷</span></div><strong id="overview-average-tokens">—</strong><small>Consumed tokens ÷ completed try-ons</small></article>
      <article><div><p>Tokens remaining</p><span class="metric-icon">T</span></div><strong id="overview-token-balance">—</strong><small>Current available token balance</small></article>
      <article><div><p>Estimated try-ons remaining</p><span class="metric-icon">≈</span></div><strong id="overview-estimated-tryons">—</strong><small>Based on average tokens per try-on</small></article>
      <article><div><p>Average try-ons</p><span class="metric-icon">↗</span></div><strong id="overview-average-tryons">—</strong><small id="overview-average-hourly">Per day · per hour</small></article>
      <article class="metric-topup"><div><p>Need more Wearo Tokens?</p><small>Choose a token pack and continue through secure payment.</small></div><a class="button button--primary" href="/business/billing#token-topup">Top up tokens</a></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel__heading"><div><h2>Launch readiness</h2><p>Complete these before customer traffic.</p></div></div><ul class="readiness-list"><li class="done"><span>✓</span>Workspace created</li><li><span>2</span>Connect billing</li><li><span>3</span>Connect your business app</li><li><span>4</span>Pass quality evaluation</li></ul></article>
      <article class="panel panel--wide"><div class="panel__heading"><div><h2>Recent activity</h2><p>Operational events, never private customer photos.</p></div></div><div class="table-empty"><span aria-hidden="true">◎</span><strong>Your activity feed is ready</strong><p>Events will appear when your team starts configuring the workspace.</p></div></article>
    </section>`;
}

function dashboardGreeting(date = new Date()) {
  const hour = date.getHours();
  if (hour < 12) return "Good morning.";
  if (hour < 17) return "Good afternoon.";
  return "Good evening.";
}

async function loadOverviewUsage(dateRange = {}) {
  const fields = {
    tokens_purchased: document.querySelector("#overview-total-tokens"),
    tokens_used: document.querySelector("#overview-tokens-used"),
    average_tokens: document.querySelector("#overview-average-tokens"),
    token_balance: document.querySelector("#overview-token-balance"),
    estimated_previews: document.querySelector("#overview-estimated-tryons"),
    average_tryons: document.querySelector("#overview-average-tryons"),
    average_hourly: document.querySelector("#overview-average-hourly"),
  };
  if (!fields.tokens_purchased) return;
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!tenantId) {
    Object.values(fields).forEach((field) => { field.textContent = "Sign in"; });
    return;
  }
  try {
    const query = new URLSearchParams({ action_code: "TRY_ON" });
    if (dateRange.dateFrom) query.set("date_from", dateRange.dateFrom);
    if (dateRange.dateTo) query.set("date_to", dateRange.dateTo);
    const usage = await businessApi(`/business/tenants/${tenantId}/usage?${query}`);
    const formatAverage = (value) => value == null ? "Not available" : Number(value).toFixed(1);
    fields.tokens_purchased.textContent = String(usage.tokens_purchased);
    fields.tokens_used.textContent = String(usage.tokens_used);
    fields.average_tokens.textContent = formatAverage(usage.average_tokens_per_preview);
    fields.token_balance.textContent = String(usage.token_balance);
    fields.estimated_previews.textContent = usage.estimated_previews == null
      ? "Rate unavailable"
      : String(usage.estimated_previews);
    fields.average_tryons.textContent = usage.average_previews_per_day == null
      ? "Not available"
      : `${Number(usage.average_previews_per_day).toFixed(1)} / day`;
    fields.average_hourly.textContent = usage.average_previews_per_hour == null
      ? "No completed try-ons in this period"
      : `${Number(usage.average_previews_per_hour).toFixed(2)} try-ons per hour`;
  } catch {
    Object.values(fields).forEach((field) => { field.textContent = "Unavailable"; });
  }
}

function experienceView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Wearo experience</p><h1>Connect your customer experience</h1><p>Your existing app owns its inventory and commerce flow. This workspace only manages the Wearo try-on service.</p></div></header>
    <section class="settings-grid"><article class="panel"><div class="panel__heading"><div><h2>App connection</h2><p>Connect Wearo from your own website, mobile app, or in-store application.</p></div></div><dl class="settings-list"><div><dt>Connection status</dt><dd><span class="status-chip">Not connected</span></dd></div><div><dt>Environment</dt><dd>Beta</dd></div><div><dt>Customer data</dt><dd>Private by default</dd></div></dl></article><article class="panel"><div class="panel__heading"><div><h2>Experience controls</h2><p>Manage availability without duplicating your business data in Wearo.</p></div></div><dl class="settings-list"><div><dt>Virtual try-on</dt><dd>Enabled</dd></div><div><dt>Quality gate</dt><dd>Required</dd></div><div><dt>Image retention</dt><dd>30 days</dd></div></dl></article></section>`;
}

function customersView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Customers</p><h1>Customer activity</h1><p>Customers are ordered by their latest successful try-on.</p></div></header>
    <section class="panel customer-directory">
      <form id="customer-search-form" role="search"><label>Search by mobile number<input name="search" type="search" inputmode="tel" autocomplete="off" placeholder="Enter a mobile number" /></label><button class="button button--primary" type="submit">Search</button><button id="customer-search-clear" class="button button--quiet" type="button">Clear</button></form>
      <p id="customer-search-status" class="form-status" role="status" aria-live="polite">Loading customers…</p>
      <div id="customer-list" class="customer-list" aria-live="polite"></div>
      <nav class="customer-pagination" aria-label="Customer pages"><button id="customer-previous" class="button button--quiet" type="button">Previous</button><span id="customer-page">Page 1</span><button id="customer-next" class="button button--quiet" type="button">Next</button></nav>
    </section>`;
}

async function loadCustomers({ page = 1, search = "" } = {}) {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  const list = document.querySelector("#customer-list");
  const status = document.querySelector("#customer-search-status");
  const previous = document.querySelector("#customer-previous");
  const next = document.querySelector("#customer-next");
  const pageLabel = document.querySelector("#customer-page");
  if (!tenantId || !list || !status || !previous || !next || !pageLabel) return;
  status.textContent = "Loading customers…";
  const query = new URLSearchParams({ page: String(page), page_size: "20" });
  if (search.trim()) query.set("search", search.trim());
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/customers?${query}`);
    list.replaceChildren();
    if (!result.items.length) {
      list.textContent = search.trim()
        ? "No customers match this mobile number."
        : "No customers have used this business try-on yet.";
    }
    for (const customer of result.items) {
      const row = document.createElement("article");
      row.className = "customer-row";
      const identity = document.createElement("div");
      const mobile = document.createElement("strong");
      const activity = document.createElement("small");
      mobile.textContent = customer.mobile;
      activity.textContent = customer.latest_try_on_at
        ? `Latest try-on ${new Date(customer.latest_try_on_at).toLocaleString()}`
        : `Joined ${new Date(customer.first_seen_at).toLocaleString()} · No completed try-ons`;
      identity.append(mobile, activity);
      const count = document.createElement("div");
      count.className = "customer-row__count";
      count.innerHTML = `<strong>${customer.try_on_count}</strong><span>successful try-on${customer.try_on_count === 1 ? "" : "s"}</span>`;
      row.append(identity, count);
      list.append(row);
    }
    status.textContent = `${result.total} customer${result.total === 1 ? "" : "s"}`;
    previous.disabled = !result.has_previous;
    next.disabled = !result.has_next;
    pageLabel.textContent = `Page ${result.page}`;
    return result;
  } catch (error) {
    list.replaceChildren();
    status.textContent = error.message;
    previous.disabled = true;
    next.disabled = true;
    return null;
  }
}

function agentsView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Workspace access</p><h1>Agent management</h1><p>Add and manage the agents who operate Wearo for this business.</p></div></header>
    <section class="agent-management">
      <article class="panel agent-link-panel"><div class="panel__heading"><div><h2>Agent app URL</h2><p>Share this business-specific link only with agents assigned to this workspace.</p></div></div><label>Agent URL<input id="agent-app-url" readonly value="Loading…" /></label><button id="agent-copy-link" class="button button--quiet" type="button">Copy link</button><p id="agent-link-status" class="form-status" role="status"></p></article>
      <article class="panel"><div class="panel__heading"><div><h2 id="agent-form-title">Add agent</h2><p>Create an agent using their name and mobile number.</p></div></div><form id="agent-form"><label>Name<input name="name" required maxlength="120" /></label><label>Mobile number<input name="mobile" type="tel" required placeholder="+919876543210" /></label><div class="form-actions"><button id="agent-submit" class="button button--primary" type="submit">Add agent</button><button id="agent-cancel" class="button button--quiet" type="button" hidden>Cancel update</button></div><p id="agent-status" class="form-status" role="status" aria-live="polite"></p></form></article>
      <article class="panel"><div class="panel__heading"><div><h2>Business agents</h2><p>Agents currently configured for this workspace.</p></div></div><div id="agent-list" class="settings-list agent-list" aria-live="polite">Loading agents…</div></article>
    </section>`;
}

function billingView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Plans & billing</p><h1>Choose how you want to launch.</h1><p>Select a plan for evaluation. No charge occurs until a payment provider is connected and checkout is confirmed.</p></div></header>
    <section class="plan-grid">
      <article class="plan-card"><p class="plan-card__name">Pilot</p><h2>₹0 <small>/ beta</small></h2><p>Validate the experience with your internal team.</p><ul><li>1 workspace</li><li>Up to 50 evaluation looks</li><li>Quality report</li></ul><button class="button button--quiet plan-select" data-plan="Pilot" type="button">Select pilot</button></article>
      <article class="plan-card plan-card--featured"><span class="plan-badge">Recommended</span><p class="plan-card__name">Launch</p><h2>Custom</h2><p>Customer-facing rollout with operational support.</p><ul><li>Production usage allowance</li><li>Team access and analytics</li><li>Launch readiness review</li></ul><button class="button button--primary plan-select" data-plan="Launch" type="button">Request checkout</button></article>
      <article class="plan-card"><p class="plan-card__name">Scale</p><h2>Contact us</h2><p>Multiple storefronts and higher-volume workflows.</p><ul><li>Multiple workspaces</li><li>Priority quality evaluation</li><li>Custom retention controls</li></ul><button class="button button--quiet plan-select" data-plan="Scale" type="button">Talk to sales</button></article>
    </section>
    <section class="panel billing-note" aria-labelledby="usage-heading"><div><h2 id="usage-heading">Plan usage</h2><p id="plan-usage-summary">Loading plan, used credits, and remaining preview allowance…</p><p id="plan-action-effect"></p></div><span id="plan-code" class="status-chip">Loading</span></section>
    <section class="panel"><div class="panel__heading"><div><h2>Wearo Token action rates</h2><p>Wearo Tokens price product actions; they are not model text tokens.</p></div></div><div id="action-rate-list" class="settings-list" aria-live="polite">Loading published rates…</div></section>
    <section class="panel"><div class="panel__heading"><div><h2>Refund and recredit policy</h2><p>Eligible reversals restore Wearo Tokens and appear in transaction history.</p></div></div><div id="recredit-policy" class="settings-list" aria-live="polite">Loading policy…</div></section>
    <section class="panel panel--wide"><div class="panel__heading"><div><h2>Token transaction history</h2><p>Reconcile purchases, promotional credits, consumption, refunds, and expiry.</p></div><a id="transaction-download" class="button button--quiet" href="#">Download CSV</a></div><form id="transaction-filters" class="filter-row"><label>Type<select name="category"><option value="">All transactions</option><option value="PURCHASE">Purchases</option><option value="PROMOTIONAL_CREDIT">Promotional credits</option><option value="CONSUMPTION">Consumption</option><option value="REFUND">Refunds</option><option value="EXPIRY">Expiry</option></select></label><label>From<input name="dateFrom" type="date" /></label><label>To<input name="dateTo" type="date" /></label><button class="button button--quiet" type="submit">Apply filters</button></form><p id="transaction-reconciliation" class="form-status" aria-live="polite"></p><div id="transaction-history" class="settings-list" aria-live="polite">Loading transactions…</div></section>
    <section id="token-topup" class="panel"><div class="panel__heading"><div><h2>Secure token top-up</h2><p>Tokens are credited only after the payment gateway confirms payment. Estimates use published rates; actual token costs vary by action.</p></div></div><p id="topup-estimate-summary">Loading current try-on estimate…</p><div id="topup-packs" class="settings-list" aria-live="polite">Loading available packs…</div><p id="topup-status" class="form-status" role="status"></p></section>
    <section class="panel"><div class="panel__heading"><div><h2>Payment reconciliation</h2><p>Track failed payments, refunds, invoice state, and discrepancies.</p></div></div><div id="payment-reconciliation" class="settings-list" aria-live="polite">Loading payment status…</div></section>
    <section class="panel billing-note"><div><h2>Payment method</h2><p>No payment method connected. Wearo will never mark a plan paid from this screen until server-verified checkout is available.</p></div><span class="status-chip">Not connected</span><p id="billing-status" class="form-status" role="status" aria-live="polite"></p></section>`;
}

async function loadBusinessUsage() {
  const summary = document.querySelector("#plan-usage-summary");
  const effect = document.querySelector("#plan-action-effect");
  const plan = document.querySelector("#plan-code");
  if (!summary || !effect || !plan) return;
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!tenantId) {
    plan.textContent = "Sign in required";
    summary.textContent = "Open an authenticated workspace to view its current usage.";
    effect.textContent = "No payment or token debit has been attempted.";
    return;
  }
  try {
    const response = await fetch(`/api/v1/business/tenants/${tenantId}/usage?action_code=TRY_ON`);
    if (!response.ok) throw new Error("Usage is temporarily unavailable.");
    const usage = await response.json();
    plan.textContent = usage.plan_code;
    const remaining = usage.previews_remaining ?? "Unlimited or token-based";
    summary.textContent = `${usage.previews_used} previews used · ${remaining} remaining · ${usage.token_balance} Wearo Tokens available.`;
    effect.textContent = usage.action_cost
      ? `A try-on currently costs ${usage.action_cost} tokens. After one try-on, approximately ${usage.balance_after_action} tokens would remain.`
      : "No active try-on rate is published. A billable preview cannot be started.";
  } catch (error) {
    plan.textContent = "Unavailable";
    summary.textContent = error.message;
    effect.textContent = "Refresh to try again; no usage was consumed.";
  }
}

async function loadActionRates() {
  const target = document.querySelector("#action-rate-list");
  if (!target) return;
  try {
    const schedule = await businessApi("/platform/pricing");
    target.replaceChildren();
    for (const rate of schedule.rates) {
      const row = document.createElement("div");
      const description = document.createElement("span");
      description.textContent = rate.description;
      const cost = document.createElement("strong");
      cost.textContent = rate.status === "PUBLISHED" ? `${rate.token_cost} tokens` : "Not published";
      row.append(description, cost);
      target.append(row);
    }
  } catch (error) { target.textContent = error.message; }
}

async function loadRecreditPolicy() {
  const target = document.querySelector("#recredit-policy");
  if (!target) return;
  try {
    const policy = await businessApi("/platform/recredit-policy");
    target.replaceChildren();
    for (const item of policy.automatic_recredit) {
      const row = document.createElement("div");
      row.textContent = item.description;
      target.append(row);
    }
    const review = document.createElement("div");
    review.textContent = policy.not_automatic;
    target.append(review);
  } catch (error) { target.textContent = error.message; }
}

async function loadTokenTransactions() {
  const target = document.querySelector("#transaction-history");
  const summary = document.querySelector("#transaction-reconciliation");
  const form = document.querySelector("#transaction-filters");
  const download = document.querySelector("#transaction-download");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!target || !summary || !form || !download) return;
  if (!tenantId) {
    target.textContent = "Sign in to view account-scoped transactions.";
    download.hidden = true;
    return;
  }
  const query = new URLSearchParams();
  if (form.elements.category.value) query.set("category", form.elements.category.value);
  if (form.elements.dateFrom.value) query.set("date_from", form.elements.dateFrom.value);
  if (form.elements.dateTo.value) query.set("date_to", form.elements.dateTo.value);
  const suffix = query.toString() ? `?${query}` : "";
  download.href = `/api/v1/business/tenants/${tenantId}/token-transactions.csv${suffix}`;
  download.hidden = false;
  target.textContent = "Loading transactions…";
  try {
    const history = await businessApi(`/business/tenants/${tenantId}/token-transactions${suffix}`);
    summary.textContent = `Opening ${history.opening_balance} · Net change ${history.net_change} · Closing ${history.closing_balance} ${history.unit}`;
    target.replaceChildren();
    if (!history.items.length) {
      target.textContent = "No transactions match these filters.";
      return;
    }
    for (const item of history.items) {
      const row = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = `${item.category.replaceAll("_", " ")} · ${new Date(item.occurred_at).toLocaleString()}`;
      const amount = document.createElement("strong");
      amount.textContent = `${item.amount > 0 ? "+" : ""}${item.amount} · balance ${item.balance_after}`;
      row.append(label, amount);
      target.append(row);
    }
  } catch (error) { target.textContent = error.message; }
}

async function loadTopupPacks() {
  const target = document.querySelector("#topup-packs");
  const status = document.querySelector("#topup-status");
  const summary = document.querySelector("#topup-estimate-summary");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!target || !status || !summary) return;
  if (!tenantId) { target.textContent = "Sign in to purchase tokens."; return; }
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/topup-packs`);
    target.replaceChildren();
    const current = result.current_estimated_try_ons.map((item) =>
      `${item.offering}: ${item.estimated_try_ons ?? "rate unavailable"}`).join(" · ");
    summary.textContent = `${result.current_token_balance} tokens currently available · ${current || "No eligible offering"}. ${result.explanation}`;
    if (!result.eligible) {
      target.textContent = "Your operating profile is not currently eligible for prepaid top-ups.";
      return;
    }
    if (!result.items.length) { target.textContent = "No token packs are currently available."; return; }
    for (const pack of result.items) {
      const row = document.createElement("div");
      const label = document.createElement("span");
      const estimates = pack.estimated_try_ons.map((item) =>
        `${item.offering}: about ${item.estimated_try_ons ?? "—"} try-ons`).join(" · ");
      label.textContent = `${pack.purchased_tokens} tokens${pack.promo_tokens ? ` + ${pack.promo_tokens} promotional` : ""} · ${estimates}`;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button--quiet";
      button.textContent = `${pack.currency} ${(pack.amount_minor / 100).toFixed(2)}`;
      button.addEventListener("click", async () => {
        button.disabled = true;
        status.textContent = "Creating secure checkout…";
        try {
          const order = await businessApi(`/business/tenants/${tenantId}/topup-orders`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pack_id: pack.pack_id, idempotency_key: crypto.randomUUID() }),
          });
          window.location.assign(order.checkout_url);
        } catch (error) { status.textContent = error.message; button.disabled = false; }
      });
      row.append(label, button);
      target.append(row);
    }
  } catch (error) { target.textContent = error.message; }
}

async function loadPaymentReconciliation() {
  const target = document.querySelector("#payment-reconciliation");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!target) return;
  if (!tenantId) { target.textContent = "Sign in to review payment status."; return; }
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/payment-reconciliation`);
    target.replaceChildren();
    if (!result.items.length) { target.textContent = "No payment activity yet."; return; }
    for (const item of result.items) {
      const row = document.createElement("div");
      const state = item.discrepancy_status === "OPEN"
        ? `Needs review: ${item.discrepancy_kind}`
        : `Payment ${item.payment_status} · Invoice ${item.invoice_status || "not issued"}`;
      row.textContent = state;
      target.append(row);
    }
  } catch (error) { target.textContent = error.message; }
}

function settingsView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Settings</p><h1>Workspace controls</h1><p>Keep product identity, team access, and privacy expectations clear.</p></div></header>
    <section class="settings-grid"><article class="panel"><h2>Billing and tax profile</h2><form id="business-billing-form"><label>Legal business name<input name="legalName" required /></label><label>Billing email<input name="billingEmail" type="email" required /></label><label>Billing phone <span>(optional)</span><input name="billingPhone" /></label><label class="check"><input name="taxInvoiceRequested" type="checkbox" /> Tax-ready invoices required</label><label>Tax identifier<input name="taxIdentifier" /></label><label>Billing address<input name="line1" /></label><label>City<input name="city" /></label><label>Postal code<input name="postalCode" /></label><label>Reason for change<input name="reason" required maxlength="500" /></label><button class="button button--primary" type="submit">Save for future invoices</button><p id="billing-profile-status" class="form-status" role="status" aria-live="polite"></p></form></article><article class="panel"><h2>Operating profile</h2><p id="operating-profile-summary">Loading profile-specific workspace details…</p><form id="operating-profile-form"><label>Request a different profile<select name="requestedProfile" required><option value="">Select type</option><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label><label>Reason<input name="reason" required maxlength="500" /></label><button class="button button--quiet" type="submit">Request profile change</button><p id="operating-profile-status" class="form-status" role="status"></p></form></article><article class="panel"><h2>Owner sign-in contacts</h2><p>Update the main administrator email and mobile without changing workspace ownership. Both contacts must be OTP verified.</p><form id="owner-contact-form"><label>Owner email<input name="email" type="email" required /></label><div class="owner-otp"><label>Email OTP<input name="emailOtp" inputmode="numeric" minlength="4" maxlength="8" required /></label><button class="button button--quiet owner-verify" data-channel="email" type="button">Verify email</button></div><label>Owner mobile<input name="mobile" type="tel" required /></label><div class="owner-otp"><label>Mobile OTP<input name="mobileOtp" inputmode="numeric" minlength="4" maxlength="8" required /></label><button class="button button--quiet owner-verify" data-channel="mobile" type="button">Verify mobile</button></div><p class="field-help">Use test OTP 9876. Verified contacts will sign in to this same workspace.</p><label>Reason for update<input name="reason" required maxlength="500" /></label><button class="button button--primary" type="submit">Update sign-in contacts</button><p id="owner-contact-status" class="form-status" role="status" aria-live="polite"></p></form></article><article class="panel"><h2>Sensitive action audit</h2><p>Owner-only history of billing, access, and wallet changes.</p><div id="sensitive-audit-list" class="settings-list" aria-live="polite">Loading audit history…</div></article><article class="panel"><h2>Customer experience</h2><dl class="settings-list"><div><dt>Jewellery generation</dt><dd><span class="status-chip">Disabled</span></dd></div><div><dt>Image retention</dt><dd>30 days</dd></div><div><dt>Profile deletion</dt><dd>Within 24 hours</dd></div><div><dt>Model training</dt><dd>Not authorised</dd></div></dl></article></section>`;
}

async function loadOperatingProfile() {
  const summary = document.querySelector("#operating-profile-summary");
  const status = document.querySelector("#operating-profile-status");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!summary || !status || !tenantId) return;
  try {
    const overview = await businessApi(`/business/tenants/${tenantId}/overview`);
    const recommendation = overview.recommendation;
    summary.textContent = `${overview.profile.operating_profile.replaceAll("_", " ")} · Eligible Wearo offerings: ${recommendation.eligible_offerings.join(", ") || "none"}. Your existing app remains the source of truth for business data.`;
    if (overview.profile_change_request) {
      status.textContent = `Change to ${overview.profile_change_request.requested_profile.replaceAll("_", " ")} is pending review.`;
    }
  } catch (error) { summary.textContent = error.message; }
}

async function loadSensitiveAudit() {
  const target = document.querySelector("#sensitive-audit-list");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!target) return;
  if (!tenantId) { target.textContent = "Sign in as an owner to review audit history."; return; }
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/audit-events?limit=50`);
    target.replaceChildren();
    if (!result.items.length) { target.textContent = "No sensitive actions recorded."; return; }
    for (const item of result.items) {
      const row = document.createElement("div");
      row.textContent = `${item.action} · ${item.reason || "No reason"} · ${new Date(item.occurred_at).toLocaleString()}`;
      target.append(row);
    }
  } catch (error) { target.textContent = error.message; }
}

function setupBusinessAdminPanels() {
  const grid = document.querySelector(".settings-grid");
  if (!grid) return;
  const ownerPanel = [...grid.querySelectorAll(".panel")]
    .find((panel) => panel.querySelector("h2")?.textContent === "Owner sign-in contacts");
  if (ownerPanel) {
    ownerPanel.innerHTML = `<h2>Owner sign-in contacts</h2><p>Update either verified contact without changing workspace ownership.</p><div class="owner-contact-list"><section class="owner-contact" data-owner-contact="email"><div><small>Current email</small><strong id="current-owner-email">Loading…</strong></div><button class="button button--quiet owner-contact-edit" type="button">Update</button><form class="owner-contact-editor" hidden><label>New email<input name="value" type="email" required /></label><button class="button button--quiet owner-contact-send" type="button">Send email OTP</button><div class="owner-otp"><label>Email OTP<input name="otp" inputmode="numeric" minlength="4" maxlength="8" required /></label><button class="button button--primary" type="submit">Verify and update</button></div><label>Reason for update<input name="reason" required maxlength="500" /></label></form></section><section class="owner-contact" data-owner-contact="mobile"><div><small>Current mobile</small><strong id="current-owner-mobile">Loading…</strong></div><button class="button button--quiet owner-contact-edit" type="button">Update</button><form class="owner-contact-editor" hidden><label>New mobile<input name="value" type="tel" required /></label><button class="button button--quiet owner-contact-send" type="button">Send SMS OTP</button><div class="owner-otp"><label>Mobile OTP<input name="otp" inputmode="numeric" minlength="4" maxlength="8" required /></label><button class="button button--primary" type="submit">Verify and update</button></div><label>Reason for update<input name="reason" required maxlength="500" /></label></form></section></div><p class="field-help">Use test OTP 9876. The updated contact will sign in to this same workspace.</p><p id="owner-contact-status" class="form-status" role="status" aria-live="polite"></p>`;
  }
  const experiencePanel = [...grid.querySelectorAll(".panel")]
    .find((panel) => panel.querySelector("h2")?.textContent === "Customer experience");
  if (experiencePanel) {
    experiencePanel.innerHTML = `<h2>Customer experience</h2><p>Manage workspace-wide customer experience settings.</p><section class="settings-section"><h3>Customer data</h3><form id="customer-experience-form"><label>Image retention<select name="imageRetentionDays"><option value="1">1 day</option><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label><p class="field-help">Customer profiles are always deleted within 24 hours.</p><label>Reason for update<input name="reason" required maxlength="500" /></label><button class="button button--primary" type="submit">Update data settings</button><p id="customer-experience-status" class="form-status" role="status" aria-live="polite"></p></form></section><section class="settings-section"><h3>General try-on allowance</h3><p class="field-help">This overall value applies to every customer and resets every 24 hours.</p><form id="allowance-policy-form"><label>Default try-ons<input name="limit" type="number" min="0" max="100000" required /></label><button class="button button--quiet" type="submit">Save default try-ons</button><p id="allowance-admin-status" class="form-status" role="status" aria-live="polite"></p></form></section>`;
  }
  if (document.querySelector("#shop-link-status")) return;
  grid.insertAdjacentHTML("beforeend", `
    <article class="panel"><h2>Company logo</h2><p>Shown on your downloadable business QR poster.</p><div id="company-logo-preview" class="company-logo-preview"><span>No logo uploaded</span></div><form id="company-logo-form"><label>Upload logo<input name="image" type="file" accept="image/png,image/jpeg,image/webp" required /></label><button class="button button--primary" type="submit">Save company logo</button><p id="company-logo-status" class="form-status" role="status" aria-live="polite"></p></form></article>
    <article class="panel"><h2>Shop QR and URL</h2><p id="shop-link-status">Loading shop link…</p><a id="shop-url" class="button button--quiet" href="#" target="_blank" rel="noopener">Open shop URL</a> <a id="shop-qr-download" class="button button--quiet" href="#">Download QR poster</a></article>
    <article class="panel"><h2>Communications and legal history</h2><p>Manage email and SMS topics and review versioned notice acceptances.</p><div id="communications-history" class="settings-list">Loading notices…</div></article>
    <article class="panel"><h2>Financial reconciliation</h2><p id="reconciliation-summary">Loading top-ups, usage, and invoices…</p><a id="reconciliation-download" class="button button--quiet" href="#">Download reconciliation CSV</a></article>
    <article class="panel"><h2>Support and billing issues</h2><form id="support-case-form"><label>Issue type<select name="caseType"><option value="SUPPORT">Support</option><option value="PAYMENT">Billing dispute</option><option value="QUALITY">Render quality</option></select></label><label>Details<textarea name="reason" required maxlength="2000"></textarea></label><button class="button button--quiet" type="submit">Submit issue</button></form><p id="support-case-status" class="form-status"></p><div id="support-case-list" class="settings-list">Loading cases…</div></article>
    <article class="panel"><h2>Support data access</h2><p>Only case-bound, time-limited, role-scoped access is allowed. Private media content is excluded from minimum-data views.</p><div id="support-access-list" class="settings-list">Loading access grants…</div></article>`);
}

async function loadSupportAccess() {
  const list = document.querySelector("#support-access-list");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!list || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/support-access-grants`);
    list.replaceChildren();
    if (!result.items.length) { list.textContent = "No support access grants."; return; }
    for (const item of result.items) {
      const row = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = `${item.scope} · expires ${new Date(item.expires_at).toLocaleString()}${item.revoked_at ? " · revoked" : ""}`;
      row.append(label);
      if (!item.revoked_at) {
        const revoke = document.createElement("button"); revoke.type = "button";
        revoke.className = "button button--quiet"; revoke.textContent = "Revoke";
        revoke.addEventListener("click", async () => {
          await businessApi(`/business/tenants/${tenantId}/support-access-grants/${item.grant_id}`, { method: "DELETE" });
          await loadSupportAccess();
        }); row.append(revoke);
      }
      list.append(row);
    }
  } catch (error) { list.textContent = error.message; }
}

async function loadReconciliationReport() {
  const summary = document.querySelector("#reconciliation-summary");
  const download = document.querySelector("#reconciliation-download");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!summary || !download || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/reconciliation-report`);
    summary.textContent = `${result.outlet} · ${result.totals.tokens_purchased} tokens purchased · ${result.totals.tokens_used} used · ${result.topups.length} top-ups with invoice records.`;
    download.href = `/api/v1/business/tenants/${tenantId}/reconciliation-report.csv`;
  } catch (error) { summary.textContent = error.message; }
}

async function loadSupportCases() {
  const list = document.querySelector("#support-case-list");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!list || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/support-cases`);
    list.replaceChildren();
    if (!result.items.length) { list.textContent = "No support cases."; return; }
    for (const item of result.items) {
      const row = document.createElement("div");
      row.textContent = `${item.case_type} · ${item.state} · ${item.disposition || "Awaiting resolution"}`;
      list.append(row);
    }
  } catch (error) { list.textContent = error.message; }
}

async function loadAllowanceAdmin() {
  const status = document.querySelector("#allowance-admin-status");
  const form = document.querySelector("#allowance-policy-form");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!status || !form || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/allowances`);
    form.elements.limit.value = result.policy.default_try_on_limit;
    status.textContent = "Applies to all customers for each 24-hour period.";
  } catch (error) { status.textContent = error.message; }
}

async function loadCommunications() {
  const target = document.querySelector("#communications-history");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!target || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/communications`);
    target.replaceChildren();
    const summary = document.createElement("div");
    summary.textContent = `${result.active_notices.length} active notices · ${result.acceptance_history.length} recorded acceptances · ${result.communication_preferences.length} communication preferences.`;
    target.append(summary);
  } catch (error) { target.textContent = error.message; }
}

async function loadAgents() {
  const list = document.querySelector("#agent-list");
  const status = document.querySelector("#agent-status");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!list || !status || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/agents`);
    list.replaceChildren();
    if (!result.items.length) { list.textContent = "No agents configured."; return; }
    for (const agent of result.items) {
      const row = document.createElement("div");
      row.className = "agent-row";
      const label = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = agent.name;
      const mobile = document.createElement("small");
      mobile.textContent = agent.normalized_mobile;
      label.append(name, mobile);
      const actions = document.createElement("span");
      actions.className = "agent-row__actions";
      const remove = document.createElement("button");
      remove.className = "button button--quiet"; remove.type = "button"; remove.textContent = "Delete";
      const edit = document.createElement("button");
      edit.className = "button button--quiet"; edit.type = "button"; edit.textContent = "Edit";
      const copyLink = document.createElement("button");
      copyLink.className = "button button--quiet"; copyLink.type = "button";
      copyLink.textContent = "Copy app URL";
      copyLink.addEventListener("click", async () => {
        if (!currentAgentAppUrl) { status.textContent = "Agent app URL is unavailable."; return; }
        try { await copyToClipboard(currentAgentAppUrl); status.textContent = `Agent app URL copied for ${agent.name}.`; }
        catch { status.textContent = "Could not copy automatically. Copy the URL from the Agent app URL panel."; }
      });
      edit.addEventListener("click", () => {
        const form = document.querySelector("#agent-form");
        form.dataset.agentId = agent.agent_id;
        form.elements.name.value = agent.name;
        form.elements.mobile.value = agent.normalized_mobile;
        document.querySelector("#agent-form-title").textContent = `Update ${agent.name}`;
        document.querySelector("#agent-submit").textContent = "Update agent";
        document.querySelector("#agent-cancel").hidden = false;
        status.textContent = `Editing ${agent.name}.`;
        form.elements.name.focus();
      });
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Delete ${agent.name} from this workspace?`)) return;
        try {
          await businessApi(`/business/tenants/${tenantId}/agents/${agent.agent_id}`, { method: "DELETE" });
          status.textContent = `${agent.name} deleted.`; await loadAgents();
        } catch (error) { status.textContent = error.message; }
      });
      actions.append(copyLink, edit, remove); row.append(label, actions); list.append(row);
    }
  } catch (error) { list.textContent = error.message; }
}

function resetAgentForm() {
  const form = document.querySelector("#agent-form");
  if (!form) return;
  form.reset();
  delete form.dataset.agentId;
  document.querySelector("#agent-form-title").textContent = "Add agent";
  document.querySelector("#agent-submit").textContent = "Add agent";
  document.querySelector("#agent-cancel").hidden = true;
}

function setupAgentManagement() {
  const form = document.querySelector("#agent-form");
  const status = document.querySelector("#agent-status");
  if (!form || !status) return;
  document.querySelector("#agent-cancel").addEventListener("click", () => {
    resetAgentForm();
    status.textContent = "Update cancelled.";
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const tenantId = localStorage.getItem("wearo_business_tenant_id");
    const agentId = form.dataset.agentId;
    status.textContent = agentId ? "Updating agent…" : "Adding agent…";
    try {
      await businessApi(`/business/tenants/${tenantId}/agents${agentId ? `/${agentId}` : ""}`, {
        method: agentId ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: form.elements.name.value, mobile: form.elements.mobile.value }),
      });
      resetAgentForm();
      status.textContent = agentId ? "Agent updated." : "Agent added.";
      await loadAgents();
    } catch (error) { status.textContent = error.message; }
  });
  loadAgentAppLink().then(loadAgents);
}

async function loadAgentAppLink() {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  const input = document.querySelector("#agent-app-url");
  const status = document.querySelector("#agent-link-status");
  const copy = document.querySelector("#agent-copy-link");
  if (!tenantId || !input || !status || !copy) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/shop-link`);
    currentAgentAppUrl = agentUrlFromShopLink(result);
    if (!currentAgentAppUrl) throw new Error("Agent app URL is unavailable.");
    input.value = currentAgentAppUrl;
    copy.addEventListener("click", async () => {
      try { await copyToClipboard(currentAgentAppUrl); status.textContent = "Agent app URL copied."; }
      catch { status.textContent = "Select the URL above and copy it manually."; }
    });
  } catch (error) { currentAgentAppUrl = ""; input.value = ""; status.textContent = error.message; }
}

async function loadShopLink() {
  const status = document.querySelector("#shop-link-status");
  const link = document.querySelector("#shop-url");
  const qr = document.querySelector("#shop-qr-download");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!status || !link || !qr || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/shop-link`);
    status.textContent = `${result.caption} · Business ID ${result.business_id}`;
    link.href = result.shop_url; qr.href = `/api/v1/business/tenants/${tenantId}/shop-qr.png`;
  } catch (error) { status.textContent = error.message; }
}

async function loadCompanyLogo() {
  const preview = document.querySelector("#company-logo-preview");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!preview || !tenantId) return;
  try {
    const details = await businessApi(`/business/tenants/${tenantId}/shop-link`);
    if (!details.logo_asset_id) { preview.innerHTML = "<span>No logo uploaded</span>"; return; }
    preview.innerHTML = `<img src="/api/v1/business/tenants/${tenantId}/company-logo?v=${encodeURIComponent(details.logo_asset_id)}" alt="Current company logo" />`;
  } catch (error) { preview.textContent = error.message; }
}

async function loadOwnerContacts() {
  const email = document.querySelector("#current-owner-email");
  const mobile = document.querySelector("#current-owner-mobile");
  const status = document.querySelector("#owner-contact-status");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!email || !mobile || !tenantId) return;
  try {
    let result;
    try {
      result = await businessApi(`/business/tenants/${tenantId}/owner-contacts`);
    } catch {
      const [memberships, billing] = await Promise.all([
        businessApi(`/business/tenants/${tenantId}/memberships`),
        businessApi(`/business/tenants/${tenantId}/billing-profile`),
      ]);
      const owner = memberships.items.find((item) => item.role === "OWNER" && !item.revoked_at);
      result = {
        email: owner?.email || billing.current.billing_email,
        mobile: billing.current.billing_phone || "",
      };
    }
    email.textContent = result.email || "Not added";
    mobile.textContent = result.mobile || "Not added";
  } catch (error) {
    email.textContent = "Unavailable";
    mobile.textContent = "Unavailable";
    status.textContent = error.message;
  }
}

async function loadCustomerExperienceSettings() {
  const form = document.querySelector("#customer-experience-form");
  const status = document.querySelector("#customer-experience-status");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!form || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/customer-experience-settings`);
    form.elements.imageRetentionDays.value = String(result.image_retention_days);
  } catch (error) { status.textContent = error.message; }
}

async function loadBillingProfile() {
  const form = document.querySelector("#business-billing-form");
  const status = document.querySelector("#billing-profile-status");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!form || !status || !tenantId) return;
  status.textContent = "Loading billing profile…";
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/billing-profile`);
    const profile = result.current;
    form.elements.legalName.value = profile.legal_name;
    form.elements.billingEmail.value = profile.billing_email;
    form.elements.billingPhone.value = profile.billing_phone || "";
    form.elements.taxInvoiceRequested.checked = profile.tax_invoice_requested;
    form.elements.taxIdentifier.value = profile.tax_identifier || "";
    form.elements.line1.value = profile.billing_address?.line1 || "";
    form.elements.city.value = profile.billing_address?.city || "";
    form.elements.postalCode.value = profile.billing_address?.postal_code || "";
    status.textContent = `${result.issued_invoices.length} issued invoices retain their original details.`;
  } catch (error) { status.textContent = error.message; }
}

function attachBusinessInteractions(section) {
  document.querySelector("#business-logout")?.addEventListener("click", async () => {
    try { await businessApi("/auth/logout", { method: "POST" }); } catch { /* Clear stale local state regardless. */ }
    sessionStorage.removeItem(BUSINESS_AUTH_KEY);
    localStorage.removeItem("wearo_business_tenant_id");
    window.location.assign("/business/sign-in");
  });
  if (section === "sign-in") {
    const form = document.querySelector("#business-signin-form");
    const status = document.querySelector("#business-signin-status");
    const codeStep = document.querySelector("#business-code-step");
    let challengeId = null;
    document.querySelector("#business-request-code")?.addEventListener("click", async () => {
      if (!form.reportValidity()) return;
      status.textContent = "Sending code…";
      try {
        const result = await businessApi("/auth/email-otp/request", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ destination: form.elements.destination.value, purpose: "BUSINESS_SIGN_IN" }),
        });
        challengeId = result.challenge_id;
        codeStep.hidden = false;
        status.textContent = result.message;
      } catch (error) { status.textContent = error.message; }
    });
    document.querySelector("#business-verify-code")?.addEventListener("click", async () => {
      if (!challengeId || !form.elements.code.value) return;
      status.textContent = "Verifying…";
      try {
        const result = await businessApi("/auth/email-otp/verify", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ challenge_id: challengeId, code: form.elements.code.value }),
        });
        sessionStorage.setItem(BUSINESS_AUTH_KEY, JSON.stringify({ csrfToken: result.csrf_token }));
        const workspaces = await businessApi("/business/workspaces");
        if (!workspaces.items.length) throw new Error("No active business workspace is assigned.");
        localStorage.setItem("wearo_business_tenant_id", workspaces.items[0].tenant_id);
        window.location.assign("/business/dashboard");
      } catch (error) { status.textContent = error.message; }
    });
  }
  if (section === "signup") {
    const signupForm = document.querySelector("#business-signup-form");
    const signupVerified = { email: false, mobile: false };
    const resendTimers = { email: null, mobile: null };
    let failedSignupOtpAttempts = 0;
    const signupLockKey = "wearo_business_signup_locked_until";
    const lockRemaining = () => Math.max(0, Number(localStorage.getItem(signupLockKey) || 0) - Date.now());
    const showSignupLock = () => {
      const remaining = lockRemaining();
      if (!remaining) return false;
      const minutes = Math.ceil(remaining / 60000);
      document.querySelector("#signup-otp-status").textContent = `Too many incorrect codes. Try signup again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
      signupForm.querySelectorAll("button").forEach((button) => { button.disabled = true; });
      return true;
    };
    const profileGuidance = {
      BOUTIQUE: "Recommended: Wearo Studio for your existing boutique app.",
      CLOTHING_RETAILER: "Recommended: Wearo Studio and Wearo Shop for your existing retail app.",
      JEWELLERY_RETAILER: "No generation offering until jewellery quality approval.",
      ENTERPRISE_CHAIN: "Recommended: Wearo Studio and Wearo Mirror for your existing enterprise apps.",
      OTHER: "Recommended: Wearo Studio connected to your existing app.",
    };
    signupForm?.elements.operatingProfile.addEventListener("change", (event) => {
      const guidance = profileGuidance[event.currentTarget.value];
      document.querySelector("#operating-profile-guidance").textContent = guidance
        ? guidance
        : "Choose a type to see the matching Wearo experience guidance.";
    });
    signupForm?.elements.taxInvoiceRequested.addEventListener("change", (event) => {
      const requested = event.currentTarget.checked;
      document.querySelector("#invoice-details").hidden = !requested;
      for (const name of ["legalName", "addressLine1", "city", "postalCode"]) {
        signupForm.elements[name].required = requested;
      }
      signupForm.elements.taxIdentifier.required = requested && signupForm.elements.jurisdiction.value.toUpperCase() === "IN";
    });
    document.querySelectorAll(".signup-send-code").forEach((button) => {
      button.addEventListener("click", () => {
        if (showSignupLock()) return;
        const channel = button.dataset.channel;
        const destination = channel === "email"
          ? signupForm.elements.email
          : signupForm.elements.primaryMobile;
        const status = document.querySelector("#signup-otp-status");
        if (!destination.reportValidity()) return;
        const codeField = document.querySelector(`[data-code-for="${channel}"]`);
        codeField.hidden = false;
        codeField.querySelector("input").disabled = false;
        codeField.querySelector("input").focus();
        let remaining = 60;
        button.disabled = true;
        button.textContent = `Resend in ${remaining}s`;
        resendTimers[channel] = window.setInterval(() => {
          remaining -= 1;
          button.textContent = remaining > 0 ? `Resend in ${remaining}s` : "Resend OTP";
          if (remaining <= 0) {
            window.clearInterval(resendTimers[channel]);
            resendTimers[channel] = null;
            button.disabled = false;
          }
        }, 1000);
        status.textContent = `Test ${channel} OTP sent. Use 9876.`;
      });
    });
    document.querySelectorAll(".signup-verify-code").forEach((button) => {
      button.addEventListener("click", () => {
        if (showSignupLock()) return;
        const channel = button.dataset.channel;
        const input = signupForm.elements[channel === "email" ? "emailOtp" : "mobileOtp"];
        const status = document.querySelector("#signup-otp-status");
        if (input.value !== "9876") {
          failedSignupOtpAttempts += 1;
          const attemptsLeft = 3 - failedSignupOtpAttempts;
          if (attemptsLeft <= 0) {
            localStorage.setItem(signupLockKey, String(Date.now() + 2 * 60 * 60 * 1000));
            showSignupLock();
          } else {
            status.textContent = `Incorrect ${channel} OTP. ${attemptsLeft} attempt${attemptsLeft === 1 ? "" : "s"} remaining.`;
          }
          return;
        }
        signupVerified[channel] = true;
        input.readOnly = true;
        button.disabled = true;
        button.textContent = "Verified ✓";
        const verification = button.closest("[data-verification]");
        verification.classList.add("is-verified");
        window.clearInterval(resendTimers[channel]);
        resendTimers[channel] = null;
        verification.querySelector(".signup-send-code").hidden = true;
        status.textContent = `${channel === "email" ? "Email" : "Mobile"} verified successfully.`;
      });
    });
    for (const [channel, fieldName] of [["email", "email"], ["mobile", "primaryMobile"]]) {
      signupForm.elements[fieldName].addEventListener("input", () => {
        if (!signupVerified[channel]) return;
        signupVerified[channel] = false;
        const verification = document.querySelector(`[data-verification="${channel}"]`);
        const otpInput = signupForm.elements[channel === "email" ? "emailOtp" : "mobileOtp"];
        const verifyButton = verification.querySelector(".signup-verify-code");
        const sendButton = verification.querySelector(".signup-send-code");
        verification.classList.remove("is-verified");
        otpInput.value = "";
        otpInput.readOnly = false;
        verifyButton.disabled = false;
        verifyButton.textContent = "Verify";
        sendButton.hidden = false;
        sendButton.disabled = false;
        sendButton.textContent = `Send ${channel} OTP`;
        document.querySelector("#signup-otp-status").textContent = `The ${channel} changed. Send and verify a new OTP.`;
      });
    }
    showSignupLock();
    signupForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const status = document.querySelector("#business-signup-status");
      if (showSignupLock()) return;
      if (!signupVerified.email || !signupVerified.mobile) {
        status.textContent = "Verify both your work email and primary mobile before continuing.";
        return;
      }
      const idempotencyKey = sessionStorage.getItem("wearo_business_registration_key") || crypto.randomUUID();
      sessionStorage.setItem("wearo_business_registration_key", idempotencyKey);
      status.textContent = "Creating workspace…";
      try {
        const logoFile = form.elements.companyLogo.files[0];
        if (logoFile && logoFile.size > 2 * 1024 * 1024) {
          throw new Error("Upload a company logo under 2 MB.");
        }
        const companyLogoDataUrl = logoFile ? await fileToDataUrl(logoFile) : null;
        const result = await businessApi("/business/register", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
          body: JSON.stringify({
            business_name: form.elements.businessName.value,
            email: form.elements.email.value,
            primary_mobile: form.elements.primaryMobile.value,
            email_otp: form.elements.emailOtp.value,
            mobile_otp: form.elements.mobileOtp.value,
            operating_profile: form.elements.operatingProfile.value,
            jurisdiction: form.elements.jurisdiction.value,
            website_url: form.elements.website.value || null,
            tax_invoice_requested: form.elements.taxInvoiceRequested.checked,
            legal_name: form.elements.legalName.value || null,
            tax_identifier: form.elements.taxIdentifier.value || null,
            billing_address: form.elements.taxInvoiceRequested.checked ? {
              line1: form.elements.addressLine1.value,
              city: form.elements.city.value,
              postal_code: form.elements.postalCode.value,
            } : null,
            company_logo_data_url: companyLogoDataUrl,
          }),
        });
        localStorage.setItem("wearo_business_tenant_id", result.tenant_id);
        sessionStorage.removeItem("wearo_business_registration_key");
        status.innerHTML = 'Workspace created. <a href="/business/sign-in">Verify your email to sign in</a>.';
      } catch (error) {
        status.textContent = error.message;
      }
    });
  }
  if (section === "dashboard") {
    document.querySelector("#dashboard-greeting").textContent = dashboardGreeting();
    const periodForm = document.querySelector("#overview-period");
    const customDates = document.querySelector("#overview-custom-dates");
    const isoDate = (value) => [
      value.getFullYear(),
      String(value.getMonth() + 1).padStart(2, "0"),
      String(value.getDate()).padStart(2, "0"),
    ].join("-");
    const selectedRange = () => {
      const today = new Date();
      const period = periodForm.elements.period.value;
      if (period === "custom") {
        return { dateFrom: periodForm.elements.dateFrom.value, dateTo: periodForm.elements.dateTo.value };
      }
      const start = new Date(today);
      if (period === "week") start.setDate(start.getDate() - 6);
      if (period === "month") start.setDate(start.getDate() - 29);
      return { dateFrom: isoDate(start), dateTo: isoDate(today) };
    };
    periodForm.elements.dateTo.max = isoDate(new Date());
    periodForm.elements.period.addEventListener("change", () => {
      const custom = periodForm.elements.period.value === "custom";
      customDates.hidden = !custom;
      periodForm.elements.dateFrom.required = custom;
      periodForm.elements.dateTo.required = custom;
      if (!custom) loadOverviewUsage(selectedRange());
    });
    periodForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (periodForm.reportValidity()) loadOverviewUsage(selectedRange());
    });
    loadOverviewUsage(selectedRange());
  }
  if (section === "billing") {
    loadBusinessUsage();
    loadActionRates();
    loadRecreditPolicy();
    loadTokenTransactions();
    loadTopupPacks();
    loadPaymentReconciliation();
    document.querySelector("#transaction-filters")?.addEventListener("submit", (event) => {
      event.preventDefault();
      loadTokenTransactions();
    });
    document.querySelectorAll(".plan-select").forEach((button) => {
      button.addEventListener("click", () => {
        localStorage.setItem("wearo_business_plan", button.dataset.plan);
        document.querySelector("#billing-status").textContent =
          `${button.dataset.plan} selected. Checkout is not connected, so no charge was made.`;
      });
    });
  }
  if (section === "agents") setupAgentManagement();
  if (section === "customers") {
    const form = document.querySelector("#customer-search-form");
    const searchInput = form?.elements.search;
    let currentPage = 1;
    let searchTimer = null;
    const refresh = async () => {
      const result = await loadCustomers({ page: currentPage, search: searchInput?.value || "" });
      if (result) currentPage = result.page;
    };
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      currentPage = 1;
      await refresh();
    });
    searchInput?.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => { currentPage = 1; refresh(); }, 300);
    });
    document.querySelector("#customer-search-clear")?.addEventListener("click", () => {
      searchInput.value = "";
      currentPage = 1;
      refresh();
      searchInput.focus();
    });
    document.querySelector("#customer-previous")?.addEventListener("click", () => {
      if (currentPage > 1) { currentPage -= 1; refresh(); }
    });
    document.querySelector("#customer-next")?.addEventListener("click", () => {
      currentPage += 1;
      refresh();
    });
    refresh();
  }
  if (section === "settings") {
    setupBusinessAdminPanels();
    loadBillingProfile();
    loadOwnerContacts();
    loadCustomerExperienceSettings();
    loadSensitiveAudit();
    loadOperatingProfile();
    loadShopLink();
    loadCompanyLogo();
    loadAllowanceAdmin();
    loadCommunications();
    loadReconciliationReport();
    loadSupportCases();
    loadSupportAccess();
    document.querySelectorAll(".owner-contact").forEach((contact) => {
      const channel = contact.dataset.ownerContact;
      const editor = contact.querySelector(".owner-contact-editor");
      const status = document.querySelector("#owner-contact-status");
      contact.querySelector(".owner-contact-edit").addEventListener("click", () => {
        editor.hidden = false;
        editor.elements.value.focus();
      });
      contact.querySelector(".owner-contact-send").addEventListener("click", () => {
        if (!editor.elements.value.reportValidity()) return;
        status.textContent = channel === "mobile"
          ? "SMS sent. Enter the OTP to verify the new mobile number."
          : "Email sent. Enter the OTP to verify the new email address.";
        editor.elements.otp.focus();
      });
      editor.addEventListener("submit", async (event) => {
        event.preventDefault();
        const tenantId = localStorage.getItem("wearo_business_tenant_id");
        status.textContent = `Verifying ${channel}…`;
        try {
          await businessApi(`/business/tenants/${tenantId}/owner-contacts`, {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              channel,
              value: editor.elements.value.value,
              otp: editor.elements.otp.value,
              reason: editor.elements.reason.value,
            }),
          });
          editor.reset(); editor.hidden = true;
          status.textContent = `${channel === "email" ? "Email" : "Mobile"} verified and updated. Use it for your next sign-in.`;
          await loadOwnerContacts();
        } catch (error) { status.textContent = error.message; }
      });
    });
    document.querySelector("#customer-experience-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      const status = document.querySelector("#customer-experience-status");
      try {
        await businessApi(`/business/tenants/${tenantId}/customer-experience-settings`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_retention_days: Number(form.elements.imageRetentionDays.value),
            profile_deletion_hours: 24,
            reason: form.elements.reason.value,
          }),
        });
        status.textContent = "Customer experience settings updated.";
        form.elements.reason.value = "";
      } catch (error) { status.textContent = error.message; }
    });
    document.querySelector("#company-logo-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const status = document.querySelector("#company-logo-status");
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      const file = form.elements.image.files[0];
      if (file.size > 2 * 1024 * 1024) {
        status.textContent = "Upload a company logo under 2 MB.";
        return;
      }
      status.textContent = "Uploading logo…";
      try {
        const body = new FormData();
        body.append("image", file);
        await businessApi(`/business/tenants/${tenantId}/company-logo`, { method: "PUT", body });
        form.reset();
        status.textContent = "Company logo updated. New QR posters will use this logo.";
        await loadCompanyLogo();
      } catch (error) { status.textContent = error.message; }
    });
    document.querySelector("#support-case-form")?.addEventListener("submit", async (event) => {
      event.preventDefault(); const form = event.currentTarget;
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      const status = document.querySelector("#support-case-status");
      try { const result = await businessApi(`/business/tenants/${tenantId}/support-cases`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_type: form.elements.caseType.value, reason: form.elements.reason.value }),
      }); form.reset(); status.textContent = `Case ${result.case_id} submitted.`; await loadSupportCases();
      } catch (error) { status.textContent = error.message; }
    });
    document.querySelector("#allowance-policy-form")?.addEventListener("submit", async (event) => {
      event.preventDefault(); const form = event.currentTarget;
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      const status = document.querySelector("#allowance-admin-status");
      try { await businessApi(`/business/tenants/${tenantId}/allowances/policy`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ default_try_on_limit: Number(form.elements.limit.value) }),
      }); status.textContent = "Default try-ons updated for all customers. The allowance resets every 24 hours."; } catch (error) { status.textContent = error.message; }
    });
    document.querySelector("#operating-profile-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const status = document.querySelector("#operating-profile-status");
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      try {
        const result = await businessApi(`/business/tenants/${tenantId}/operating-profile-change`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ requested_profile: form.elements.requestedProfile.value,
            reason: form.elements.reason.value }),
        });
        status.textContent = `Change to ${result.requested_profile.replaceAll("_", " ")} is pending review.`;
      } catch (error) { status.textContent = error.message; }
    });
    document.querySelector("#business-billing-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const status = document.querySelector("#billing-profile-status");
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      status.textContent = "Saving…";
      try {
        await businessApi(`/business/tenants/${tenantId}/billing-profile`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            legal_name: form.elements.legalName.value,
            billing_email: form.elements.billingEmail.value,
            billing_phone: form.elements.billingPhone.value || null,
            tax_invoice_requested: form.elements.taxInvoiceRequested.checked,
            tax_identifier: form.elements.taxIdentifier.value || null,
            billing_address: { line1: form.elements.line1.value, city: form.elements.city.value, postal_code: form.elements.postalCode.value },
            reason: form.elements.reason.value,
          }),
        });
        form.elements.reason.value = "";
        status.textContent = "Saved for future invoices. Issued invoices were not changed.";
      } catch (error) { status.textContent = error.message; }
    });
  }
}

export function renderBusinessApp(root, pathname) {
  document.documentElement.dataset.experience = "business";
  const section = sectionFromPath(pathname);
  document.title = "Wearo Business";
  if (pathname.startsWith("/business/signup")) {
    root.innerHTML = signupView();
    attachBusinessInteractions("signup");
    return;
  }
  if (section === "sign-in") {
    root.innerHTML = signInView();
    attachBusinessInteractions("sign-in");
    return;
  }
  if (section === "welcome") {
    root.innerHTML = welcomeView();
    return;
  }
  if (!readBusinessAuth()) {
    window.history.replaceState({}, "", "/business/sign-in");
    root.innerHTML = signInView();
    attachBusinessInteractions("sign-in");
    return;
  }
  const views = {
    dashboard: dashboardView,
        experience: experienceView,
        customers: customersView,
        agents: agentsView,
        billing: billingView,
    settings: settingsView,
  };
  root.innerHTML = businessFrame(section, views[section]());
  attachBusinessInteractions(section);
  if (window.location.hash) {
    const targetId = decodeURIComponent(window.location.hash.slice(1));
    window.requestAnimationFrame(() => document.getElementById(targetId)?.scrollIntoView());
  }
}

export { sectionFromPath };
