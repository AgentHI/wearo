import { brandMarkup } from "./brand.js";
import { apiError, networkError, readApiBody } from "./api-messages.js";
import { razorpayCheckoutLogo } from "./razorpay-brand.js";
import { wearoConfirm } from "./wearo-dialog.js";

const API_BASE = "/api/v1";
const BUSINESS_AUTH_KEY = "wearo_business_auth";
let currentAgentAppUrl = "";
let pendingAgentMove = null;
let currentSmartAdSchedules = [];
let smartAdGenerationInProgress = false;
let smartAdGenerationPoll = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

const OPERATING_PROFILE_LABELS = Object.freeze({
  BOUTIQUE: "Boutique",
  CLOTHING_RETAILER: "Clothing retailer",
  JEWELLERY_RETAILER: "Jewellery retailer",
  ENTERPRISE_CHAIN: "Enterprise chain",
  OTHER: "Other",
});

function operatingProfileLabel(profile) {
  return OPERATING_PROFILE_LABELS[profile] || "Operating profile";
}

function personCategoryLabel(category) {
  return { woman: "Woman", girl: "Girl", unknown: "Unclassified" }[category] || "Unclassified";
}

function ageRangeLabel(ageRange) {
  return {
    under_10: "Under 10",
    "10_19": "10–19",
    "20_29": "20–29",
    "30_39": "30–39",
    "40_49": "40–49",
    "50_59": "50–59",
    "60_plus": "60+",
    unknown: "Age unclassified",
  }[ageRange] || "Age unclassified";
}

function estimatedAgeLabel(estimatedAge, ageRange) {
  return Number.isInteger(estimatedAge)
    ? `Approx. ${estimatedAge} years`
    : ageRangeLabel(ageRange);
}

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

function smartAdsMark(className = "") {
  return `<svg class="smart-ads-mark ${className}" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <rect x="6.25" y="7.25" width="19.5" height="18.5" rx="5.25" stroke="currentColor" stroke-width="1.5"/>
    <path d="m16 11.25 3.65 4.2L16 21.2l-3.65-5.75L16 11.25Z" fill="currentColor" fill-opacity=".18" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>
    <path d="M16 11.25v9.95m-3.65-5.75h7.3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
    <path d="M24.5 3.75v3.5M22.75 5.5h3.5M8.5 3.5v2M7.5 4.5h2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
  </svg>`;
}

const sections = [
  ["dashboard", "Overview", "▦"],
  ["customers", "Users", "♙"],
  ["smart-ads", "SmartAds", smartAdsMark("smart-ads-mark--nav")],
  ["stores", "Stores", "⌂"],
  ["agents", "Agent transfers", "♧"],
  ["billing", "Plans & billing", "▤"],
  ["settings", "Settings", "⚙"],
];

function businessFooter() {
  return `<footer class="business-footer">© 2026 All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>`;
}

function sectionFromPath(pathname) {
  if (pathname.startsWith("/business/sign-in")) return "sign-in";
  if (pathname.startsWith("/business/signup")) return "signup";
  if (pathname.startsWith("/business/experience")) return "dashboard";
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
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: "same-origin", ...options, headers,
    });
  } catch {
    throw networkError();
  }
  let body = await readApiBody(response);
  const isMutation = options.method && !["GET", "HEAD"].includes(options.method);
  if (response.status === 403 && body.code === "AUTHENTICATION_REQUIRED" && isMutation) {
    const refresh = await fetch(`${API_BASE}/auth/business/csrf`, { credentials: "same-origin" });
    if (refresh.ok) {
      const refreshed = await refresh.json();
      sessionStorage.setItem(BUSINESS_AUTH_KEY, JSON.stringify({ csrfToken: refreshed.csrf_token }));
      headers.set("X-CSRF-Token", refreshed.csrf_token);
      response = await fetch(`${API_BASE}${path}`, { credentials: "same-origin", ...options, headers });
      body = await readApiBody(response);
    }
  }
  if (!response.ok) throw apiError(response, body);
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
        <div class="business-sidebar__brand">${brandMarkup("/business", "white")}<span>Business</span></div>
        <div class="workspace-switcher"><span class="workspace-switcher__mark">BW</span><span><small>Workspace</small><strong>Business workspace</strong></span><span aria-hidden="true">⌄</span></div>
        <p class="business-sidebar__label">Manage</p>
        <nav class="business-nav" aria-label="Business workspace">${navigation}</nav>
        <div class="business-sidebar__footer"><button id="business-logout" class="business-signout" type="button"><span aria-hidden="true">⇥</span> Sign out</button></div>
      </aside>
      <div class="business-workspace">
        <header class="business-topbar">
          <div class="business-breadcrumb"><strong>Business workspace</strong><span>/</span><span>${sections.find(([id]) => id === section)?.[1] || "Workspace"}</span></div>
          <div class="business-topbar__actions"><span class="environment-badge"><span class="availability-dot" aria-hidden="true"></span>Beta</span><a class="topbar-help" href="/business/settings">Help</a><div class="business-user-menu"><button id="business-user-toggle" class="business-user" type="button" aria-haspopup="menu" aria-expanded="false" aria-controls="business-user-options"><span>MA</span><div><strong>Workspace owner</strong><small>Administrator</small></div><span class="business-user__chevron" aria-hidden="true">⌄</span></button><div id="business-user-options" class="business-user-options" role="menu" hidden><button data-open-owner-email-change role="menuitem" type="button">Change admin email</button></div></div></div>
        </header>
        <main id="main" class="business-main">${content}</main>
        ${businessFooter()}
      </div>
      <dialog id="owner-email-change-dialog" class="owner-email-change-dialog" aria-labelledby="owner-email-change-title">
        <form id="owner-email-change-form">
          <div class="owner-email-change-dialog__heading"><div><p class="eyebrow">Workspace security</p><h2 id="owner-email-change-title">Change admin email</h2></div><button id="owner-email-change-close" type="button" aria-label="Close">×</button></div>
          <p>We will verify both addresses before changing the workspace owner sign-in email.</p>
          <label>Current admin email<input name="currentEmail" type="email" readonly /></label>
          <label>New admin email<input name="newEmail" type="email" autocomplete="email" required /></label>
          <button id="owner-email-change-request" class="button button--quiet" type="button">Send verification codes</button>
          <fieldset id="owner-email-change-codes" hidden><legend>Enter both verification codes</legend><label>Code sent to current email<input name="currentEmailOtp" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" required /></label><label>Code sent to new email<input name="newEmailOtp" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" required /></label></fieldset>
          <p class="field-help">After the email changes, all active admin sessions will be signed out immediately.</p>
          <p id="owner-email-change-status" class="form-status" role="status" aria-live="polite"></p>
          <button id="owner-email-change-submit" class="button button--primary" type="submit" disabled>Verify and change email</button>
        </form>
      </dialog>
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
    <header class="page-heading"><div><p class="eyebrow">Workspace overview</p><h1 id="dashboard-greeting">Welcome.</h1><p>Monitor your virtual try-on operation and remaining capacity.</p></div><form id="overview-period" class="period-filter"><label><span>Reporting period</span><select name="period"><option value="today">Today</option><option value="week">Past week</option><option value="month" selected>Past month</option><option value="custom">Custom duration</option></select></label><div id="overview-custom-dates" class="period-filter__dates" hidden><label><span>From</span><input name="dateFrom" type="date" /></label><label><span>To</span><input name="dateTo" type="date" /></label><button class="button button--quiet" type="submit">Apply</button></div></form></header>
    <section class="dashboard-metric-group dashboard-metric-group--tokens" aria-labelledby="tryon-metrics-heading">
      <div class="dashboard-metric-group__heading"><div><p class="eyebrow">Usage</p><h2 id="tryon-metrics-heading">Try-on overview</h2></div><small>Capacity and consumption</small></div>
      <div class="metric-grid overview-metrics">
        <article class="metric-card--tokens"><div><p>Total try-ons</p><span class="metric-icon">＋</span></div><strong id="overview-total-tryons">—</strong><small>Consumed try-ons plus your estimated remaining capacity</small></article>
        <article class="metric-card--tokens"><div><p>Try-ons consumed</p><span class="metric-icon">−</span></div><strong id="overview-tryons-consumed">—</strong><small>Completed try-ons in the selected period</small></article>
        <article class="metric-card--tokens"><div><p>Average cost per try-on</p><span class="metric-icon">$</span></div><strong id="overview-average-cost">—</strong><small>Based on the models used for completed try-ons</small></article>
        <article class="metric-card--tokens"><div><p>Try-ons remaining</p><span class="metric-icon">≈</span></div><strong id="overview-tryons-remaining">—</strong><small>Estimated from your current available balance</small></article>
      </div>
      <div class="hero-actions"><a class="button button--primary" href="/business/billing#token-topup">Add more try-ons</a></div>
    </section>
    <section class="dashboard-metric-group dashboard-metric-group--activity" aria-labelledby="activity-metrics-heading">
      <div class="dashboard-metric-group__heading"><div><p class="eyebrow">Customer activity</p><h2 id="activity-metrics-heading">Try-on performance</h2></div><small>Completed try-ons only</small></div>
      <div class="metric-grid overview-metrics">
        <article class="metric-card--activity"><div><p>Unique users</p><span class="metric-icon">U</span></div><strong id="overview-unique-users">—</strong><small>Customers who completed a try-on in the selected period</small></article>
        <article class="metric-card--activity"><div><p>Try-ons today</p><span class="metric-icon">D</span></div><strong id="overview-tryons-today">—</strong><small>Completed today · India Standard Time</small></article>
        <article class="metric-card--activity"><div><p id="overview-tryons-selected-label">Try-ons in selected period</p><span class="metric-icon">Σ</span></div><strong id="overview-tryons-selected">—</strong><small>Total completed for the active reporting filter</small></article>
        <article class="metric-card--activity"><div><p>Average try-ons</p><span class="metric-icon">↗</span></div><strong id="overview-average-tryons">—</strong><small id="overview-average-hourly">Per day · per hour</small></article>
      </div>
    </section>
    <section class="dashboard-metric-group dashboard-metric-group--activity" aria-labelledby="customer-category-heading">
      <div class="dashboard-metric-group__heading"><div><p class="eyebrow">Lifetime audience</p><h2 id="customer-category-heading">Customer categories</h2></div><div class="audience-store-filter"><label for="audience-store">Store</label><select id="audience-store"><option value="">All stores</option></select><small id="audience-store-context">All stores · unique customers · all time</small></div></div>
      <div class="metric-grid overview-metrics">
        <article class="metric-card--activity"><div><p>Total unique users</p><span class="metric-icon">U</span></div><strong id="overview-total-unique-users">—</strong><small>All non-anonymized customers seen by your business</small></article>
        <article class="metric-card--activity"><div><p>Basic</p><span class="metric-icon">B</span></div><strong id="overview-category-basic">—</strong><small>Customers currently classified as basic</small></article>
        <article class="metric-card--activity"><div><p>Premium</p><span class="metric-icon">P</span></div><strong id="overview-category-premium">—</strong><small>Customers currently classified as premium</small></article>
        <article class="metric-card--activity"><div><p>Luxury</p><span class="metric-icon">L</span></div><strong id="overview-category-luxury">—</strong><small>Customers currently classified as luxury</small></article>
        <article class="metric-card--activity"><div><p>Ultra luxury</p><span class="metric-icon">UL</span></div><strong id="overview-category-ultra-luxury">—</strong><small>Customers currently classified as ultra_luxury</small></article>
        <article class="metric-card--activity"><div><p>Unclassified</p><span class="metric-icon">?</span></div><strong id="overview-category-unknown">—</strong><small>Customers whose category is still unknown</small></article>
      </div>
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
    total_tryons: document.querySelector("#overview-total-tryons"),
    tryons_consumed: document.querySelector("#overview-tryons-consumed"),
    average_cost: document.querySelector("#overview-average-cost"),
    tryons_remaining: document.querySelector("#overview-tryons-remaining"),
    unique_users: document.querySelector("#overview-unique-users"),
    tryons_today: document.querySelector("#overview-tryons-today"),
    tryons_selected: document.querySelector("#overview-tryons-selected"),
    average_tryons: document.querySelector("#overview-average-tryons"),
    average_hourly: document.querySelector("#overview-average-hourly"),
  };
  const selectedLabel = document.querySelector("#overview-tryons-selected-label");
  if (!fields.total_tryons) return;
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
    const consumedTryons = Number(usage.previews_used || 0);
    const remainingTryons = usage.estimated_previews == null ? null : Number(usage.estimated_previews);
    fields.total_tryons.textContent = remainingTryons == null
      ? "Rate unavailable"
      : String(consumedTryons + remainingTryons);
    fields.tryons_consumed.textContent = String(consumedTryons);
    fields.average_cost.textContent = usage.average_provider_cost_usd_micros == null
      ? "Not available"
      : `$${(Number(usage.average_provider_cost_usd_micros) / 1_000_000).toFixed(4)}`;
    fields.tryons_remaining.textContent = remainingTryons == null
      ? "Rate unavailable"
      : String(remainingTryons);
    fields.unique_users.textContent = String(usage.unique_participants ?? 0);
    fields.tryons_today.textContent = String(usage.previews_today ?? 0);
    fields.tryons_selected.textContent = String(usage.previews_used ?? 0);
    selectedLabel.textContent = dateRange.label
      ? `Try-ons from ${dateRange.label}`
      : "Try-ons in selected period";
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

function audienceFields() {
  return {
    total: document.querySelector("#overview-total-unique-users"),
    basic: document.querySelector("#overview-category-basic"),
    premium: document.querySelector("#overview-category-premium"),
    luxury: document.querySelector("#overview-category-luxury"),
    ultra_luxury: document.querySelector("#overview-category-ultra-luxury"),
    unknown: document.querySelector("#overview-category-unknown"),
  };
}

async function loadAudience(storeId = "", storeName = "All stores") {
  const fields = audienceFields();
  const context = document.querySelector("#audience-store-context");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!tenantId || !fields.total) return;
  try {
    const query = new URLSearchParams();
    if (storeId) query.set("store_id", storeId);
    const suffix = storeId ? `?${query}` : "";
    const audience = await businessApi(`/business/tenants/${tenantId}/audience${suffix}`);
    const categories = audience.users_by_category || {};
    fields.total.textContent = String(audience.total_unique_users ?? 0);
    fields.basic.textContent = String(categories.basic ?? 0);
    fields.premium.textContent = String(categories.premium ?? 0);
    fields.luxury.textContent = String(categories.luxury ?? 0);
    fields.ultra_luxury.textContent = String(categories.ultra_luxury ?? 0);
    fields.unknown.textContent = String(categories.unknown ?? 0);
    if (context) context.textContent = `${storeName} · unique customers · all time`;
  } catch {
    Object.values(fields).forEach((field) => { if (field) field.textContent = "Unavailable"; });
  }
}

async function setupAudienceStoreFilter() {
  const select = document.querySelector("#audience-store");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!select || !tenantId) return;
  try {
    const result = await businessApi(`/business/tenants/${tenantId}/stores`);
    for (const store of result.items) {
      const option = document.createElement("option");
      option.value = store.store_id;
      option.textContent = store.status === "ACTIVE" ? store.name : `${store.name} (${store.status.toLowerCase()})`;
      select.append(option);
    }
    select.addEventListener("change", () => {
      loadAudience(select.value, select.selectedOptions[0]?.textContent || "All stores");
    });
  } catch {
    select.disabled = true;
  }
  await loadAudience();
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
      const demographics = document.createElement("div");
      const activity = document.createElement("small");
      mobile.textContent = customer.mobile;
      demographics.className = "customer-row__people";
      const persons = customer.persons?.length ? customer.persons : [customer];
      persons.forEach((person, index) => {
        const personSummary = document.createElement("span");
        personSummary.className = "customer-row__person";
        const personCategory = document.createElement("span");
        const ageRange = document.createElement("span");
        personCategory.className = "status-chip";
        personCategory.textContent = `${persons.length > 1 ? `Person ${index + 1}: ` : ""}${personCategoryLabel(person.person_category)}`;
        ageRange.className = "status-chip";
        ageRange.textContent = estimatedAgeLabel(person.estimated_age, person.age_range);
        personSummary.append(personCategory, ageRange);
        demographics.append(personSummary);
      });
      activity.textContent = customer.latest_try_on_at
        ? `Latest try-on ${new Date(customer.latest_try_on_at).toLocaleString()}`
        : `Joined ${new Date(customer.first_seen_at).toLocaleString()} · No completed try-ons`;
      identity.append(mobile, demographics, activity);
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

function smartAdsCaption(operatingProfile) {
  const captions = {
    BOUTIQUE: "Create boutique campaigns with AI, then reach the right consented audience at the right moment.",
    CLOTHING_RETAILER: "Create clothing campaigns with AI, then reach the right consented audience at the right moment.",
    JEWELLERY_RETAILER: "Create jewellery campaigns with AI, then reach the right consented audience at the right moment.",
    ENTERPRISE_CHAIN: "Create multi-location retail campaigns with AI, then reach the right consented audience at the right moment.",
    OTHER: "Create tailored business campaigns with AI, then reach the right consented audience at the right moment.",
  };
  return captions[String(operatingProfile || "OTHER").toUpperCase()] || captions.OTHER;
}

function smartAdsView() {
  return `
    <header class="smart-ads-hero">
      <div class="smart-ads-hero__identity">
        <span class="smart-ads-hero__mark">${smartAdsMark("smart-ads-mark--hero")}</span>
        <div><p class="eyebrow">Campaign intelligence</p><h1>Smart<span>Ads</span></h1><p id="smart-ads-caption">${smartAdsCaption()}</p></div>
      </div>
    </header>
    <section class="smart-ads-summary" aria-label="SmartAds summary">
      <article class="smart-ads-stat smart-ads-stat--audience"><div class="smart-ads-stat__top"><span>Unique female users</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3"/><path d="M3.5 18c.4-3.1 2.2-4.7 5.5-4.7s5.1 1.6 5.5 4.7M17 8.5a2.5 2.5 0 1 0 0-5M16 13c2.7 0 4.2 1.3 4.5 4"/></svg></div><strong id="smart-ads-female-users">—</strong><small>Individual women, including multiple people saved in one profile.</small></article>
      <article class="smart-ads-stat"><div class="smart-ads-stat__top"><span>Ready to reach</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 12 5 5L20 6"/></svg></div><strong id="smart-ads-eligible-users">—</strong><small>Female users who have given marketing consent.</small></article>
      <article class="smart-ads-stat smart-ads-stat--tries"><div class="smart-ads-stat__top"><span>AI generations today</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1"/><circle cx="12" cy="12" r="3.5"/></svg></div><strong id="smart-ads-attempts">—</strong><small>Two creative concepts are available each India calendar day.</small></article>
    </section>
    <section class="smart-ads-workspace">
      <form id="smart-ad-create-form" class="panel smart-ad-editor smart-ad-editor--create">
        <div class="smart-ad-editor__heading"><span class="smart-ad-step">01</span><div><p class="eyebrow">Creative studio</p><h2>Create a campaign</h2><p>Start with the jewellery, add an optional model, and guide the look with a prompt. Your company logo and the Wearo.ai logo are applied automatically.</p></div></div>
        <label class="smart-ad-field"><span>Advertisement caption</span><input name="title" maxlength="120" required placeholder="e.g. Diwali heritage collection" /></label>
        <fieldset class="smart-ad-upload-group"><legend>Campaign imagery</legend><div class="smart-ad-upload-grid">
          <label class="smart-ad-upload" data-smart-upload><input name="jewellery" type="file" accept="image/jpeg,image/png,image/webp" required /><span class="smart-ad-upload__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V5m0 0L8 9m4-4 4 4M5 15v3.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V15"/></svg></span><strong>Jewellery set</strong><small data-smart-file-name>Choose the hero product image</small><em>Required</em></label>
          <label class="smart-ad-upload" data-smart-upload><input name="modelPhoto" type="file" accept="image/jpeg,image/png,image/webp" /><span class="smart-ad-upload__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.25"/><path d="M5.5 20c.5-4.5 2.7-6.7 6.5-6.7s6 2.2 6.5 6.7"/></svg></span><strong>Model photo</strong><small data-smart-file-name>Add a preferred model reference</small><em>Optional</em></label>
        </div><p>JPEG, PNG or WebP · Maximum 5 MB per image</p></fieldset>
        <label class="smart-ad-field"><span>Creative direction</span><textarea name="prompt" maxlength="2000" rows="5" required placeholder="Describe the mood, setting, lighting and styling you want…"></textarea><small>Be specific about the occasion and visual mood. You can generate again before accepting.</small></label>
        <div class="smart-ad-tryon-note"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4.5h14v15H5zM8 8h8m-8 4h5m-5 4h3"/><path d="m15 15 4 2-2 1-1 2-1-5Z"/></svg><div><strong>Built-in “Try on” action</strong><span>Every scheduled email invites customers into your B2B2C fitting room with this jewellery already selected. Their sponsored balance is checked before generation.</span></div></div>
        <button class="button button--primary smart-ad-primary-action" type="submit"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1"/><circle cx="12" cy="12" r="3.5"/></svg>Upload and generate concept</button>
        <div id="smart-ad-generation-progress" class="smart-ad-generation-progress" role="status" aria-live="polite" hidden><div><span aria-hidden="true"></span><strong id="smart-ad-generation-message">Generating advertisement concept…</strong></div><div class="smart-ad-generation-progress__bar" aria-hidden="true"><i></i></div><small>Please keep this page open. Generation can take a few minutes.</small></div>
        <p id="smart-ad-create-status" class="form-status" role="status" aria-live="polite"></p>
      </form>
      <form id="smart-ad-schedule-form" class="panel smart-ad-editor smart-ad-editor--schedule">
        <div class="smart-ad-editor__heading"><span class="smart-ad-step">02</span><div><p class="eyebrow">Delivery planner</p><h2>Schedule a campaign</h2><p>Select an accepted creative, define the audience, and choose when it should arrive.</p></div></div>
        <label class="smart-ad-field"><span>Occasion</span><input name="occasion" maxlength="160" required placeholder="e.g. Diwali private preview" /></label>
        <label class="smart-ad-field"><span>Advertisement</span><select name="smartAdId" required><option value="">Select an accepted advertisement</option></select></label>
        <label class="smart-ad-field"><span>Delivery date and time</span><input name="scheduledFor" type="datetime-local" required /></label>
        <fieldset class="smart-ad-audience"><legend><span>Target audience</span><small>Only customers with marketing consent will receive this campaign.</small></legend><div class="smart-ad-target-grid"><label><span>Gender</span><select name="targetGender"><option value="female">Female</option><option value="all">All consented users</option><option value="male">Male</option><option value="non_binary">Non-binary</option></select></label><label><span>Minimum age</span><input name="ageMin" type="number" min="1" max="120" placeholder="Any" /></label><label><span>Maximum age</span><input name="ageMax" type="number" min="1" max="120" placeholder="Any" /></label></div></fieldset>
        <label class="smart-ad-field"><span>Delivery channel</span><select name="channel"><option value="EMAIL">Email</option><option value="WHATSAPP" disabled>WhatsApp · coming soon</option></select></label>
        <div class="smart-ad-channel-note"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6.5h16v11H4zM4.5 7l7.5 6 7.5-6"/></svg><div><strong>Email is ready</strong><span>WhatsApp delivery will be available in a future release.</span></div></div>
        <div class="smart-ad-schedule-actions"><button class="button button--primary smart-ad-primary-action" type="submit"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5h14v14H5zM8 3v5m8-5v5M5 10h14m-10 3h2m2 0h2m-6 3h2"/></svg><span>Schedule email</span></button><button id="smart-ad-schedule-cancel" class="button button--quiet" type="button" hidden>Cancel editing</button></div>
        <p id="smart-ad-schedule-status" class="form-status" role="status" aria-live="polite"></p>
      </form>
    </section>
    <section class="panel smart-ad-library"><div class="panel__heading"><div><p class="eyebrow">Creative library</p><h2>Your advertisements</h2><p>Review drafts, try another concept, or accept a creative to make it available for scheduling.</p></div><span id="smart-ad-count" class="status-chip">Loading</span></div><div id="smart-ad-list" class="smart-ad-grid" aria-live="polite"></div></section>
    <section class="panel smart-ad-schedules"><div class="panel__heading"><div><p class="eyebrow">Campaign calendar</p><h2>Scheduled delivery</h2><p>Email is queued once for every reachable, consented account at the selected time.</p></div></div><div id="smart-ad-schedule-list" class="smart-ad-schedule-list" aria-live="polite">Loading schedules…</div></section>
    <dialog id="smart-ad-edit-dialog" class="cancellation-dialog smart-ad-edit-dialog" aria-labelledby="smart-ad-edit-title" aria-describedby="smart-ad-edit-description"><form id="smart-ad-edit-form" class="cancellation-dialog__panel"><header><div><p class="eyebrow">SmartAds creative</p><h2 id="smart-ad-edit-title">Edit advertisement</h2></div><button id="smart-ad-edit-close" class="camera-dialog__close" type="button" aria-label="Close advertisement editor">×</button></header><div class="cancellation-dialog__details smart-ad-edit-dialog__fields"><p id="smart-ad-edit-description">Update the customer-facing caption and the creative direction used for future generations.</p><label class="smart-ad-field"><span>Advertisement caption</span><input name="title" maxlength="120" required /></label><label class="smart-ad-field"><span>Creative direction</span><textarea name="prompt" maxlength="2000" rows="6" required></textarea><small>Changes to the creative direction apply when you generate another concept.</small></label><p id="smart-ad-edit-status" class="form-status" role="status" aria-live="polite"></p></div><div class="cancellation-dialog__actions"><button id="smart-ad-edit-cancel" class="button button--quiet" type="button">Cancel</button><button class="button button--primary" type="submit">Save changes</button></div></form></dialog>`;
}

function smartAdImageUrl(tenantId, item, role = "creative") {
  return `${API_BASE}/business/tenants/${encodeURIComponent(tenantId)}/smart-ads/${encodeURIComponent(item.smart_ad_id)}/image?role=${role}`;
}

function setSmartAdGenerationUi(active, message = "Generating advertisement concept…") {
  const progress = document.querySelector("#smart-ad-generation-progress");
  const createForm = document.querySelector("#smart-ad-create-form");
  if (!progress || !createForm) return;
  progress.hidden = !active;
  progress.querySelector("#smart-ad-generation-message").textContent = message;
  createForm.toggleAttribute("aria-busy", active);
  createForm.querySelector('button[type="submit"]').disabled = active;
  document.querySelectorAll("[data-smart-generate]").forEach((button) => { button.disabled = active; });
}

function renderSmartAds(result) {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  document.querySelector("#smart-ads-caption").textContent = smartAdsCaption(result.operating_profile);
  document.querySelector("#smart-ads-female-users").textContent = String(result.female_unique_users ?? 0);
  document.querySelector("#smart-ads-eligible-users").textContent = String(result.female_marketing_eligible_users ?? 0);
  document.querySelector("#smart-ads-attempts").textContent = `${result.attempts_remaining_today ?? 0} of ${result.maximum_daily_attempts ?? 2} left`;
  document.querySelector("#smart-ad-count").textContent = `${result.items.length} advertisement${result.items.length === 1 ? "" : "s"}`;
  const generationBusy = smartAdGenerationInProgress || Boolean(result.generation_in_progress);
  const list = document.querySelector("#smart-ad-list");
  list.innerHTML = result.items.length ? result.items.map((item) => {
    const previewRole = item.creative_asset_id ? "creative" : "jewellery";
    const canGenerate = item.status === "DRAFT" && Number(result.attempts_remaining_today) > 0 && !generationBusy;
    return `<article class="smart-ad-card" data-smart-ad="${escapeHtml(item.smart_ad_id)}"><img src="${smartAdImageUrl(tenantId, item, previewRole)}" alt="${escapeHtml(item.title)} advertisement preview" /><div class="smart-ad-card__body"><div><span class="status-chip">${escapeHtml(item.status)}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.prompt)}</p></div><div class="smart-ad-card__actions">${item.status === "DRAFT" ? `<button class="button button--quiet" type="button" data-smart-generate="${escapeHtml(item.smart_ad_id)}" ${canGenerate ? "" : "disabled"}>Generate${item.creative_asset_id ? " again" : " concept"}</button>${item.creative_asset_id ? `<button class="advertisement-icon-button advertisement-icon-button--primary" type="button" data-smart-accept="${escapeHtml(item.smart_ad_id)}" aria-label="Accept advertisement" title="Accept advertisement"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg></button>` : ""}` : ""}<button class="advertisement-icon-button" type="button" data-smart-edit="${escapeHtml(item.smart_ad_id)}" aria-label="Edit advertisement" title="Edit advertisement"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"/></svg></button><button class="advertisement-icon-button advertisement-icon-button--danger" type="button" data-smart-delete="${escapeHtml(item.smart_ad_id)}" aria-label="Delete advertisement" title="Delete advertisement"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></button></div></div></article>`;
  }).join("") : '<p class="admin-empty">No SmartAds created yet.</p>';
  setSmartAdGenerationUi(
    generationBusy,
    smartAdGenerationInProgress
      ? "Generating your advertisement concept…"
      : "Another advertisement concept is generating…",
  );
  window.clearTimeout(smartAdGenerationPoll);
  smartAdGenerationPoll = result.generation_in_progress && !smartAdGenerationInProgress
    ? window.setTimeout(() => loadSmartAds().catch(() => {}), 3000)
    : null;

  const select = document.querySelector("#smart-ad-schedule-form").elements.smartAdId;
  const selected = select.value;
  select.innerHTML = '<option value="">Select an accepted advertisement</option>' + result.items.filter((item) => item.status === "ACTIVE").map((item) => `<option value="${escapeHtml(item.smart_ad_id)}">${escapeHtml(item.title)}</option>`).join("");
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;

  const schedules = document.querySelector("#smart-ad-schedule-list");
  currentSmartAdSchedules = result.schedules;
  schedules.innerHTML = result.schedules.length ? result.schedules.map((item) => {
    const deliveryState = Number(item.delivered) > 0
      ? "Delivered"
      : Number(item.processing) > 0
        ? "Sending"
        : Number(item.failed) > 0 && Number(item.pending) === 0
          ? "Failed"
          : "Scheduled";
    return `<article data-smart-schedule="${escapeHtml(item.schedule_id)}"><div><span class="status-chip">${deliveryState}</span><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.occasion)}</span></div><div><span>${new Date(item.scheduled_for).toLocaleString()}</span><small>${escapeHtml(item.target_gender)} · ages ${item.target_age_min ?? "any"}–${item.target_age_max ?? "any"}</small></div><div><strong>${item.queued_recipient_count}</strong><span>email recipients</span><small>${item.target_user_count} people matched · ${item.delivered} delivered · ${item.failed} failed</small></div><div class="smart-ad-schedule-actions"><button class="advertisement-icon-button" type="button" data-smart-schedule-edit="${escapeHtml(item.schedule_id)}" aria-label="Edit scheduled delivery" title="Edit scheduled delivery" ${item.can_edit ? "" : "disabled"}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"/></svg></button><button class="advertisement-icon-button advertisement-icon-button--danger" type="button" data-smart-schedule-delete="${escapeHtml(item.schedule_id)}" aria-label="Delete scheduled delivery" title="Delete scheduled delivery" ${item.can_delete ? "" : "disabled"}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></button>${item.can_delete ? "" : "<small>Delivery history is locked after sending starts.</small>"}</div></article>`;
  }).join("") : '<p class="admin-empty">No advertisements scheduled.</p>';
}

async function loadSmartAds() {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!tenantId) return null;
  const result = await businessApi(`/business/tenants/${tenantId}/smart-ads`);
  renderSmartAds(result);
  return result;
}

function setupSmartAds() {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  const createForm = document.querySelector("#smart-ad-create-form");
  const createStatus = document.querySelector("#smart-ad-create-status");
  const scheduleForm = document.querySelector("#smart-ad-schedule-form");
  const scheduleStatus = document.querySelector("#smart-ad-schedule-status");
  const scheduleCancel = document.querySelector("#smart-ad-schedule-cancel");
  const editDialog = document.querySelector("#smart-ad-edit-dialog");
  const editForm = document.querySelector("#smart-ad-edit-form");
  const editStatus = document.querySelector("#smart-ad-edit-status");
  if (!tenantId || !createForm || !scheduleForm || !editDialog || !editForm) return;
  const closeEditDialog = () => {
    if (editDialog.open) editDialog.close();
  };
  document.querySelector("#smart-ad-edit-close").addEventListener("click", closeEditDialog);
  document.querySelector("#smart-ad-edit-cancel").addEventListener("click", closeEditDialog);
  editDialog.addEventListener("click", (event) => {
    if (event.target === editDialog) closeEditDialog();
  });
  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = editForm.dataset.smartAdId;
    const button = editForm.querySelector('button[type="submit"]');
    if (!id) return;
    button.disabled = true;
    editStatus.textContent = "Saving advertisement changes…";
    try {
      await businessApi(`/business/tenants/${tenantId}/smart-ads/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: editForm.elements.title.value,
          prompt: editForm.elements.prompt.value,
        }),
      });
      closeEditDialog();
      createStatus.textContent = "Advertisement updated.";
      await loadSmartAds();
    } catch (error) {
      editStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  const resetUploadLabels = () => {
    createForm.querySelectorAll("[data-smart-upload]").forEach((upload) => {
      const input = upload.querySelector('input[type="file"]');
      const fileName = upload.querySelector("[data-smart-file-name]");
      const fallback = input.name === "jewellery" ? "Choose the hero product image" : "Add a preferred model reference";
      fileName.textContent = input.files?.[0]?.name || fallback;
      upload.classList.toggle("has-file", Boolean(input.files?.length));
    });
  };
  createForm.querySelectorAll('[data-smart-upload] input[type="file"]').forEach((input) => {
    input.addEventListener("change", resetUploadLabels);
  });
  const now = new Date(Date.now() + 60_000);
  now.setSeconds(0, 0);
  scheduleForm.elements.scheduledFor.min = new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  const scheduleSubmitLabel = scheduleForm.querySelector('button[type="submit"] span');
  const localDateTimeValue = (value) => {
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  };
  const clearScheduleEditing = () => {
    delete scheduleForm.dataset.editSchedule;
    scheduleForm.reset();
    scheduleSubmitLabel.textContent = "Schedule email";
    scheduleCancel.hidden = true;
  };
  scheduleCancel.addEventListener("click", () => {
    clearScheduleEditing();
    scheduleStatus.textContent = "Schedule editing cancelled.";
  });

  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = createForm.querySelector("button[type=submit]");
    smartAdGenerationInProgress = true;
    setSmartAdGenerationUi(true, "Uploading reference photos…");
    createStatus.textContent = "Uploading reference photos…";
    try {
      const data = new FormData();
      data.set("title", createForm.elements.title.value);
      data.set("prompt", createForm.elements.prompt.value);
      data.set("jewellery", createForm.elements.jewellery.files[0]);
      const model = createForm.elements.modelPhoto.files[0];
      if (model) data.set("model_photo", model);
      const created = await businessApi(`/business/tenants/${tenantId}/smart-ads`, { method: "POST", body: data });
      setSmartAdGenerationUi(true, "AI is creating your advertisement concept…");
      createStatus.textContent = "Generating your advertisement concept…";
      try {
        await businessApi(`/business/tenants/${tenantId}/smart-ads/${created.smart_ad_id}/generate`, { method: "POST" });
        createStatus.textContent = "Concept generated. Review it below and accept it when ready.";
        createForm.reset();
        resetUploadLabels();
      } catch (error) {
        createStatus.textContent = `Draft saved, but generation did not finish: ${error.message}`;
      }
    } catch (error) { createStatus.textContent = error.message; }
    finally {
      smartAdGenerationInProgress = false;
      setSmartAdGenerationUi(false);
      button.disabled = false;
      await loadSmartAds().catch(() => {});
    }
  });

  document.querySelector("#smart-ad-list").addEventListener("click", async (event) => {
    const action = event.target.closest("button");
    if (!action) return;
    const id = action.dataset.smartGenerate || action.dataset.smartAccept || action.dataset.smartEdit || action.dataset.smartDelete;
    if (!id) return;
    const isGeneration = Boolean(action.dataset.smartGenerate);
    if (isGeneration) {
      smartAdGenerationInProgress = true;
      setSmartAdGenerationUi(true, "AI is creating another advertisement concept…");
    } else {
      action.disabled = true;
    }
    createStatus.textContent = "Saving SmartAds changes…";
    try {
      if (action.dataset.smartGenerate) {
        createStatus.textContent = "Generating another concept…";
        await businessApi(`/business/tenants/${tenantId}/smart-ads/${id}/generate`, { method: "POST" });
        createStatus.textContent = "New concept generated. Review it below and accept it when ready.";
      } else if (action.dataset.smartAccept) {
        await businessApi(`/business/tenants/${tenantId}/smart-ads/${id}/accept`, { method: "POST" });
        createStatus.textContent = "Advertisement accepted and added to the active list.";
      } else if (action.dataset.smartEdit) {
        const current = action.closest(".smart-ad-card");
        const currentTitle = current.querySelector("h3").textContent;
        const currentPrompt = current.querySelector("p").textContent;
        editForm.dataset.smartAdId = id;
        editForm.elements.title.value = currentTitle;
        editForm.elements.prompt.value = currentPrompt;
        editStatus.textContent = "";
        editDialog.showModal();
        editForm.elements.title.focus();
        editForm.elements.title.select();
        createStatus.textContent = "";
      } else if (action.dataset.smartDelete) {
        const confirmed = await wearoConfirm({
          eyebrow: "SmartAds",
          title: "Delete this advertisement?",
          message: "Its queued deliveries will be cancelled and its private images scheduled for deletion.",
          confirmLabel: "Delete advertisement",
          cancelLabel: "Keep advertisement",
        });
        if (!confirmed) return;
        await businessApi(`/business/tenants/${tenantId}/smart-ads/${id}`, { method: "DELETE" });
        createStatus.textContent = "Advertisement deleted.";
      }
    } catch (error) { createStatus.textContent = error.message; }
    finally {
      if (isGeneration) {
        smartAdGenerationInProgress = false;
        setSmartAdGenerationUi(false);
      }
      action.disabled = false;
      await loadSmartAds().catch(() => {});
    }
  });

  scheduleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = scheduleForm.querySelector("button[type=submit]");
    button.disabled = true;
    const scheduleId = scheduleForm.dataset.editSchedule;
    scheduleStatus.textContent = scheduleId ? "Updating scheduled delivery…" : "Scheduling delivery…";
    try {
      const result = await businessApi(`/business/tenants/${tenantId}/smart-ad-schedules${scheduleId ? `/${encodeURIComponent(scheduleId)}` : ""}`, {
        method: scheduleId ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          smart_ad_id: scheduleForm.elements.smartAdId.value,
          occasion: scheduleForm.elements.occasion.value,
          scheduled_for: new Date(scheduleForm.elements.scheduledFor.value).toISOString(),
          channel: scheduleForm.elements.channel.value,
          target_gender: scheduleForm.elements.targetGender.value,
          target_age_min: scheduleForm.elements.ageMin.value ? Number(scheduleForm.elements.ageMin.value) : null,
          target_age_max: scheduleForm.elements.ageMax.value ? Number(scheduleForm.elements.ageMax.value) : null,
        }),
      });
      scheduleStatus.textContent = `${scheduleId ? "Schedule updated." : "Schedule created."} ${result.target_user_count} consented people matched; ${result.queued_recipient_count} unique email recipients queued.`;
      clearScheduleEditing();
      await loadSmartAds();
    } catch (error) { scheduleStatus.textContent = error.message; }
    finally { button.disabled = false; }
  });

  document.querySelector("#smart-ad-schedule-list").addEventListener("click", async (event) => {
    const action = event.target.closest("button");
    if (!action) return;
    const editId = action.dataset.smartScheduleEdit;
    const deleteId = action.dataset.smartScheduleDelete;
    const scheduleId = editId || deleteId;
    if (!scheduleId) return;
    const schedule = currentSmartAdSchedules.find((item) => item.schedule_id === scheduleId);
    if (!schedule) return;
    if (editId) {
      scheduleForm.dataset.editSchedule = scheduleId;
      scheduleForm.elements.occasion.value = schedule.occasion;
      scheduleForm.elements.smartAdId.value = schedule.smart_ad_id;
      scheduleForm.elements.scheduledFor.value = localDateTimeValue(schedule.scheduled_for);
      scheduleForm.elements.targetGender.value = schedule.target_gender;
      scheduleForm.elements.ageMin.value = schedule.target_age_min ?? "";
      scheduleForm.elements.ageMax.value = schedule.target_age_max ?? "";
      scheduleForm.elements.channel.value = schedule.channel;
      scheduleSubmitLabel.textContent = "Save schedule changes";
      scheduleCancel.hidden = false;
      scheduleStatus.textContent = `Editing ${schedule.occasion}.`;
      scheduleForm.scrollIntoView({ behavior: "smooth", block: "start" });
      scheduleForm.elements.occasion.focus({ preventScroll: true });
      return;
    }
    const confirmed = await wearoConfirm({
      eyebrow: "Scheduled delivery",
      title: "Delete this schedule?",
      message: "Pending customer emails will be cancelled immediately. The advertisement itself will not be deleted.",
      confirmLabel: "Delete schedule",
      cancelLabel: "Keep schedule",
    });
    if (!confirmed) return;
    action.disabled = true;
    scheduleStatus.textContent = "Deleting scheduled delivery…";
    try {
      await businessApi(`/business/tenants/${tenantId}/smart-ad-schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" });
      if (scheduleForm.dataset.editSchedule === scheduleId) clearScheduleEditing();
      scheduleStatus.textContent = "Scheduled delivery deleted and pending emails cancelled.";
      await loadSmartAds();
    } catch (error) {
      scheduleStatus.textContent = error.message;
      action.disabled = false;
    }
  });

  loadSmartAds().catch((error) => { createStatus.textContent = error.message; });
}

function agentsView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Workspace access</p><h1>Agent transfers</h1><p>Review agents across stores and move them when their store assignment changes.</p></div></header>
    <section class="agent-management">
      <article class="panel agent-link-panel"><div class="panel__heading"><div><h2>Agent app URL</h2><p>Share this business-specific link only with agents assigned to this workspace.</p></div></div><label>Agent URL<input id="agent-app-url" readonly value="Loading…" /></label><button id="agent-copy-link" class="button button--quiet" type="button">Copy link</button><p id="agent-link-status" class="form-status" role="status"></p></article>
      <article class="panel"><div class="panel__heading"><div><h2>Store ownership</h2><p>Store administrators create, update, and delete agents. Only the business administrator can transfer them between stores.</p></div></div><p id="agent-status" class="form-status" role="status" aria-live="polite"></p></article>
      <article class="panel"><div class="panel__heading"><div><h2>Business agents</h2><p>Agents currently configured for this workspace.</p></div></div><div id="agent-list" class="settings-list agent-list" aria-live="polite">Loading agents…</div></article>
    </section>
    <dialog id="agent-move-dialog" class="cancellation-dialog" aria-labelledby="agent-move-title" aria-describedby="agent-move-copy"><div class="cancellation-dialog__panel"><header><div><p class="eyebrow">Agent transfer</p><h2 id="agent-move-title">Move agent</h2></div><button id="agent-move-close" class="camera-dialog__close" type="button" aria-label="Close transfer">×</button></header><div class="cancellation-dialog__details"><p id="agent-move-copy"></p><label>Destination store<select id="agent-move-destination" required></select></label><p id="agent-move-status" class="form-status" role="status" aria-live="polite"></p></div><div class="cancellation-dialog__actions"><button id="agent-move-cancel" class="button button--quiet" type="button">Cancel</button><button id="agent-move-confirm" class="button button--primary" type="button">Move agent</button></div></div></dialog>`;
}

function openAgentMoveDialog(agent, stores) {
  const dialog = document.querySelector("#agent-move-dialog");
  const destination = document.querySelector("#agent-move-destination");
  const currentStore = stores.find((store) => store.store_id === agent.store_id);
  pendingAgentMove = { agent, stores };
  destination.replaceChildren();
  const prompt = document.createElement("option");
  prompt.value = ""; prompt.textContent = "Select destination store"; prompt.disabled = true;
  prompt.selected = true; destination.append(prompt);
  for (const store of stores.filter((item) => item.store_id !== agent.store_id && item.status === "ACTIVE")) {
    const option = document.createElement("option"); option.value = store.store_id;
    option.textContent = store.name; destination.append(option);
  }
  document.querySelector("#agent-move-title").textContent = `Move ${agent.name}`;
  document.querySelector("#agent-move-copy").textContent = `Current store: ${currentStore?.name || "Unknown"}. Select the destination store for this agent.`;
  document.querySelector("#agent-move-status").textContent = destination.options.length === 1
    ? "No other active store is available." : "";
  document.querySelector("#agent-move-confirm").disabled = destination.options.length === 1;
  dialog.showModal();
  if (destination.options.length > 1) destination.focus();
}

function storesView() {
  const match = window.location.pathname.match(/^\/business\/stores\/(new|[0-9a-f-]+\/edit)\/?$/i);
  if (match) {
    const storeId = match[1] === "new" ? "" : match[1].replace(/\/edit$/i, "");
    return `<header class="page-heading store-editor-heading"><div><a class="back-link" href="/business/stores">← Back to stores</a><p class="eyebrow">Business structure</p><h1 id="store-form-title">${storeId ? "Edit store" : "Add store"}</h1><p>${storeId ? "Update store details and administrator access." : "Create a store and assign its administrator."}</p></div></header>
      <section class="panel store-editor"><div class="panel__heading"><div><h2>Store details</h2><p>Store administrators can sign in at <strong>/store</strong> using either their email or mobile.</p></div></div>
      <form id="store-form" data-store-id="${storeId}"><div class="store-form-grid"><label>Store name<input name="name" maxlength="120" autocomplete="organization" required /><small class="field-help">The name shown to agents and the store administrator.</small></label><label>Store code<input name="code" maxlength="40" placeholder="indiranagar" pattern="[a-z0-9-]+" required /><small class="field-help">Lowercase letters, numbers, and hyphens.</small></label><label>Admin email<input name="adminEmail" type="email" autocomplete="email" required /><small class="field-help">Used for email OTP sign-in.</small></label><label>Admin mobile<input name="adminMobile" type="tel" autocomplete="tel" placeholder="+919876543210" required /><small class="field-help">Include the international country code.</small></label></div>
      <div class="form-actions store-form-actions"><button class="button button--primary" type="submit">${storeId ? "Save changes" : "Add store"}</button><a class="button button--quiet" href="/business/stores">Cancel</a></div><p id="store-status" class="form-status" role="status" aria-live="polite"></p></form></section>`;
  }
  return `<header class="page-heading"><div><p class="eyebrow">Business structure</p><h1>Stores</h1><p>Manage your stores and their administrators.</p></div><a class="button button--primary" href="/business/stores/new">Add store</a></header>
    <section class="panel store-directory"><div class="panel__heading"><div><h2>Business stores</h2><p>Each store has one administrator and its own team of agents.</p></div><span id="store-count" class="status-chip">Loading</span></div><div id="store-list" class="store-list" aria-live="polite">Loading stores…</div></section>`;
}

async function loadStores() {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  const list = document.querySelector("#store-list");
  const result = await businessApi(`/business/tenants/${tenantId}/stores`);
  if (!list) return result.items;
  list.replaceChildren();
  const count = document.querySelector("#store-count");
  if (count) count.textContent = `${result.items.length} store${result.items.length === 1 ? "" : "s"}`;
  if (!result.items.length) {
    list.innerHTML = `<div class="table-empty"><span aria-hidden="true">⌂</span><strong>No stores yet</strong><p>Add your first store and assign its administrator.</p><a class="button button--primary" href="/business/stores/new">Add store</a></div>`;
    return result.items;
  }
  for (const store of result.items) {
    const row = document.createElement("article"); row.className = "store-row";
    row.innerHTML = `<div class="store-row__identity"><span class="store-row__mark" aria-hidden="true"></span><div><div class="store-row__title"><strong></strong><span class="status-chip"></span></div><small class="store-row__code"></small></div></div><dl class="store-row__details"><div><dt>Administrator</dt><dd class="store-admin-email"></dd><small class="store-admin-mobile"></small></div><div><dt>Agents</dt><dd class="store-agent-count"></dd></div></dl><a class="button button--quiet store-row__edit">Edit store</a>`;
    row.querySelector(".store-row__mark").textContent = store.name.slice(0, 2).toUpperCase();
    row.querySelector(".store-row__title strong").textContent = store.name;
    row.querySelector(".store-row__title .status-chip").textContent = store.status === "ACTIVE" ? "Active" : store.status;
    row.querySelector(".store-row__code").textContent = `Store code · ${store.code}`;
    row.querySelector(".store-admin-email").textContent = store.admin_email || "Not assigned";
    row.querySelector(".store-admin-mobile").textContent = store.admin_mobile || "Add administrator contacts";
    row.querySelector(".store-agent-count").textContent = `${store.agent_count} agent${Number(store.agent_count) === 1 ? "" : "s"}`;
    row.querySelector(".store-row__edit").href = `/business/stores/${store.store_id}/edit`;
    list.append(row);
  }
  return result.items;
}

function setupStores() {
  const form = document.querySelector("#store-form"), status = document.querySelector("#store-status");
  if (!form) {
    loadStores().catch((error) => { document.querySelector("#store-list").textContent = error.message; });
    return;
  }
  const id = form.dataset.storeId;
  if (id) {
    status.textContent = "Loading store…";
    loadStores().then((stores) => {
      const store = stores.find((item) => item.store_id === id);
      if (!store) throw new Error("Store unavailable.");
      form.elements.name.value = store.name;
      form.elements.code.value = store.code;
      form.elements.adminEmail.value = store.admin_email || "";
      form.elements.adminMobile.value = store.admin_mobile || "";
      document.querySelector("#store-form-title").textContent = `Edit ${store.name}`;
      status.textContent = "";
    }).catch((error) => { status.textContent = error.message; });
  }
  form.addEventListener("submit", async (event) => { event.preventDefault(); status.textContent = id ? "Saving changes…" : "Adding store…"; try { await businessApi(`/business/tenants/${localStorage.getItem("wearo_business_tenant_id")}/stores${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.elements.name.value, code: form.elements.code.value, admin_email: form.elements.adminEmail.value, admin_mobile: form.elements.adminMobile.value }) }); window.history.pushState({}, "", "/business/stores"); renderBusinessApp(document.querySelector("#app"), "/business/stores"); } catch (error) { status.textContent = error.message; } });
}

function billingView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Plans & billing</p><h1>Choose how you want to launch.</h1><p>Select a plan for evaluation. No charge occurs until a payment provider is connected and checkout is confirmed.</p></div></header>
    <section class="business-payment-intro" aria-labelledby="business-payment-title">
      <div><p class="eyebrow">Payment-ready information</p><h2 id="business-payment-title">Platform access and try-on usage stay separate.</h2><p>Future business pricing will combine a monthly or annual platform fee with usage-based Wearo Tokens. Final fees, taxes, renewal dates, and credit validity will be shown before an authorised owner accepts an order.</p></div>
      <div class="business-payment-intro__facts"><span><strong>15%</strong> planned annual platform-fee discount</span><span><strong>7 days</strong> payment grace before try-on suspension</span></div>
    </section>
    <section class="business-policy-grid" aria-label="Business commercial policy summary">
      <article class="panel"><span class="business-policy-card__number">01</span><h2>Platform fee</h2><p>Covers workspace access, stores, team controls, analytics, billing records, and support. Monthly and annual amounts are not yet published.</p></article>
      <article class="panel"><span class="business-policy-card__number">02</span><h2>Usage rate</h2><p id="business-retail-tryon-rate">Loading the published website rate…</p></article>
      <article class="panel"><span class="business-policy-card__number">03</span><h2>Estimated duration</h2><p>When sufficient usage exists, Wearo will show remaining credits, average daily successful try-ons, and an estimated number of days remaining.</p></article>
      <article class="panel"><span class="business-policy-card__number">04</span><h2>Payment due</h2><p>Payment reminders continue during a seven-calendar-day grace period. After that, new try-ons may be suspended while billing, reports, exports, and support remain accessible.</p></article>
      <article class="panel"><span class="business-policy-card__number">05</span><h2>Refunds and recredits</h2><p>Failed, cancelled-before-processing, and non-delivered actions are recredited. Duplicate or incorrect payments and undelivered paid services are reviewed for refund to the original payment method.</p></article>
      <article class="panel"><span class="business-policy-card__number">06</span><h2>Service delivery</h2><p>Activation, integrations, usage rates, support levels, renewal, cancellation, data export, and retention terms will be documented in the accepted business order.</p></article>
    </section>
    <section class="panel business-policy-notice" role="note"><div><h2>No subscription or checkout yet</h2><p>These details explain the intended commercial rules. Selecting an evaluation option does not create a paid subscription, save a payment method, or charge the business.</p></div><span class="status-chip">Information only</span></section>
    <section class="plan-grid">
      <article class="plan-card"><p class="plan-card__name">Pilot</p><h2>₹0 <small>/ beta</small></h2><p>Validate the experience with your internal team.</p><ul><li>1 workspace</li><li>Up to 50 evaluation looks</li><li>Quality report</li></ul><button class="button button--quiet plan-select" data-plan="Pilot" type="button">Select pilot</button></article>
      <article class="plan-card plan-card--featured"><span class="plan-badge">Recommended</span><p class="plan-card__name">Launch</p><h2>Custom</h2><p>Customer-facing rollout with operational support.</p><ul><li>Production usage allowance</li><li>Team access and analytics</li><li>Launch readiness review</li></ul><button class="button button--primary plan-select" data-plan="Launch" type="button">Request checkout</button></article>
      <article class="plan-card"><p class="plan-card__name">Scale</p><h2>Contact us</h2><p>Multiple storefronts and higher-volume workflows.</p><ul><li>Multiple workspaces</li><li>Priority quality evaluation</li><li>Custom retention controls</li></ul><button class="button button--quiet plan-select" data-plan="Scale" type="button">Talk to sales</button></article>
    </section>
    <section class="panel billing-note" aria-labelledby="usage-heading"><div><h2 id="usage-heading">Plan usage</h2><p id="plan-usage-summary">Loading plan, used credits, and remaining preview allowance…</p><p id="plan-action-effect"></p></div><span id="plan-code" class="status-chip">Loading</span></section>
    <section class="panel billing-note" aria-labelledby="try-on-control-heading"><div><h2 id="try-on-control-heading">Try-on availability</h2><p id="try-on-control-copy">Loading current availability…</p><p id="try-on-control-status" class="form-status" role="status" aria-live="polite"></p></div><div class="form-actions"><span id="try-on-status" class="status-chip">Loading</span><button id="pause-try-ons" class="button button--quiet" type="button">Pause Try-ons</button><button id="resume-try-ons" class="button button--primary" type="button" hidden>Resume Try-ons</button><button id="cancel-subscription" class="button button--danger" type="button">Cancel Subscription</button></div></section>
    <dialog id="business-subscription-dialog" class="cancellation-dialog" aria-labelledby="business-subscription-dialog-title" aria-describedby="business-subscription-dialog-description">
      <div class="cancellation-dialog__panel">
        <header><div><p class="eyebrow">Plans &amp; billing</p><h2 id="business-subscription-dialog-title"></h2></div><button id="close-business-subscription-dialog" class="camera-dialog__close" type="button" aria-label="Close confirmation">×</button></header>
        <div id="business-subscription-dialog-description" class="cancellation-dialog__details"><p id="business-subscription-dialog-copy"></p><p>No business, user, profile, or try-on data will be deleted.</p></div>
        <div class="cancellation-dialog__actions">
          <button id="keep-business-subscription" class="button button--quiet" type="button">Keep Subscription</button>
          <button id="confirm-business-subscription-action" class="button button--danger" type="button">Cancel Subscription</button>
        </div>
      </div>
    </dialog>
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

async function loadTryOnStatus() {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  const badge = document.querySelector("#try-on-status");
  const copy = document.querySelector("#try-on-control-copy");
  const pause = document.querySelector("#pause-try-ons");
  const resume = document.querySelector("#resume-try-ons");
  const cancel = document.querySelector("#cancel-subscription");
  if (!tenantId || !badge || !copy || !pause || !resume || !cancel) return;
  const result = await businessApi(`/business/tenants/${tenantId}/try-on-status`);
  badge.textContent = result.status === "CANCELLED" ? "Subscription Cancelled" : result.status;
  pause.hidden = result.status !== "ACTIVE";
  resume.hidden = result.status !== "PAUSED";
  cancel.hidden = result.status === "CANCELLED";
  copy.textContent = result.status === "ACTIVE"
    ? "Customers can start new try-ons."
    : result.status === "PAUSED"
      ? "New try-ons are blocked. Existing profiles, saved data, and results remain available."
      : "This subscription is cancelled. New try-ons are permanently blocked; existing data remains available.";
}

async function updateTryOnStatus(status) {
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  const message = document.querySelector("#try-on-control-status");
  message.textContent = "Updating try-on availability…";
  try {
    await businessApi(`/business/tenants/${tenantId}/try-on-status`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    message.textContent = status === "PAUSED" ? "Try-ons paused."
      : status === "ACTIVE" ? "Try-ons resumed." : "Subscription cancelled.";
    await loadTryOnStatus();
    return true;
  } catch (error) { message.textContent = error.message; return false; }
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

async function loadRetailTryOnRate() {
  const target = document.querySelector("#business-retail-tryon-rate");
  if (!target) return;
  try {
    const rate = await businessApi("/public/try-on-pricing");
    target.textContent = rate.status === "PUBLISHED"
      ? `${Number(rate.tokens_per_tryon).toLocaleString("en-IN")} Wearo Tokens per try-on. Tokens are deducted only for successfully delivered try-ons.`
      : "The website try-on price has not yet been published.";
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
          if (typeof window.Razorpay !== "function") throw new Error("Secure checkout could not be loaded. Check your connection and retry.");
          const checkoutLogo = await razorpayCheckoutLogo();
          const checkout = new window.Razorpay({
            key: order.key_id, amount: order.amount_minor, currency: order.currency,
            name: "Wearo.ai",
            image: checkoutLogo,
            description: `${pack.total_tokens} Wearo Tokens`,
            order_id: order.provider_order_id,
            handler: async (payment) => {
              status.textContent = "Verifying payment…";
              try {
                await businessApi(`/business/tenants/${tenantId}/verify-payment`, {
                  method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(payment),
                });
                status.textContent = "Payment verified. Your Wearo Tokens are ready.";
                await Promise.all([loadTopupPacks(), loadPaymentReconciliation()]);
              } catch (error) { status.textContent = `Payment verification failed: ${error.message}`; }
              finally { button.disabled = false; }
            },
            modal: { ondismiss: () => {
              status.textContent = "Checkout cancelled. No payment was recorded.";
              button.disabled = false;
            } },
            theme: { color: "#5b244f", backdrop_color: "#f4edf6" },
          });
          checkout.on("payment.failed", (response) => {
            status.textContent = response.error?.description || "Payment failed. Please retry.";
            button.disabled = false;
          });
          checkout.open();
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
    <section class="settings-grid"><article class="panel"><h2>Billing and tax profile</h2><form id="business-billing-form"><label>Legal business name<input name="legalName" required /></label><label>Billing email<input name="billingEmail" type="email" required /></label><label>Billing phone <span>(optional)</span><input name="billingPhone" /></label><label class="check"><input name="taxInvoiceRequested" type="checkbox" /> Tax-ready invoices required</label><label>Tax identifier<input name="taxIdentifier" /></label><label>Billing address<input name="line1" /></label><label>City<input name="city" /></label><label>Postal code<input name="postalCode" /></label><label>Reason for change<input name="reason" required maxlength="500" /></label><button class="button button--primary" type="submit">Save for future invoices</button><p id="billing-profile-status" class="form-status" role="status" aria-live="polite"></p></form></article><article class="panel"><h2>Operating profile</h2><p id="operating-profile-summary">Loading profile-specific workspace details…</p><form id="operating-profile-form"><label>Profile type<select name="operatingProfile" required><option value="BOUTIQUE">Boutique</option><option value="CLOTHING_RETAILER">Clothing retailer</option><option value="JEWELLERY_RETAILER">Jewellery retailer</option><option value="ENTERPRISE_CHAIN">Enterprise chain</option><option value="OTHER">Other</option></select></label><label>Reason for change<input name="reason" required maxlength="500" /></label><button class="button button--primary" type="submit">Save operating profile</button><p id="operating-profile-status" class="form-status" role="status" aria-live="polite"></p></form></article><article class="panel"><h2>Owner sign-in contacts</h2><p>Loading secure owner contact controls…</p></article><article class="panel"><h2>Sensitive action audit</h2><p>Owner-only history of billing, access, and wallet changes.</p><div id="sensitive-audit-list" class="settings-list" aria-live="polite">Loading audit history…</div></article><article class="panel"><h2>Customer experience</h2><dl class="settings-list"><div><dt>Jewellery generation</dt><dd><span class="status-chip">Disabled</span></dd></div><div><dt>Image retention</dt><dd>30 days</dd></div><div><dt>Profile deletion</dt><dd>Within 24 hours</dd></div><div><dt>Model training</dt><dd>Not authorised</dd></div></dl></article></section>`;
}

async function loadOperatingProfile() {
  const summary = document.querySelector("#operating-profile-summary");
  const status = document.querySelector("#operating-profile-status");
  const tenantId = localStorage.getItem("wearo_business_tenant_id");
  if (!summary || !status || !tenantId) return;
  try {
    const overview = await businessApi(`/business/tenants/${tenantId}/overview`);
    const recommendation = overview.recommendation;
    summary.textContent = `${operatingProfileLabel(overview.profile.operating_profile)} · Eligible Wearo offerings: ${recommendation.eligible_offerings.join(", ") || "none"}. Your existing app remains the source of truth for business data.`;
    const form = document.querySelector("#operating-profile-form");
    if (form) form.elements.operatingProfile.value = overview.profile.operating_profile;
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
    ownerPanel.innerHTML = `<h2>Owner sign-in contacts</h2><p>Update verified sign-in contacts without changing workspace ownership.</p><div class="owner-contact-list"><section class="owner-contact" data-owner-contact="email"><div><small>Current email</small><strong id="current-owner-email">Loading…</strong></div><button class="button button--quiet" data-open-owner-email-change type="button">Change admin email</button></section><section class="owner-contact" data-owner-contact="mobile"><div><small>Current mobile</small><strong id="current-owner-mobile">Loading…</strong></div><button class="button button--quiet owner-contact-edit" type="button">Update</button><form class="owner-contact-editor" hidden><label>New mobile<input name="value" type="tel" required /></label><button class="button button--quiet owner-contact-send" type="button">Send SMS OTP</button><div class="owner-otp"><label>Mobile OTP<input name="otp" inputmode="numeric" minlength="4" maxlength="8" required /></label><button class="button button--primary" type="submit">Verify and update</button></div><label>Reason for update<input name="reason" required maxlength="500" /></label></form></section></div><p class="field-help">Admin email changes require verification from both the current and new addresses.</p><p id="owner-contact-status" class="form-status" role="status" aria-live="polite"></p>`;
  }
  const experiencePanel = [...grid.querySelectorAll(".panel")]
    .find((panel) => panel.querySelector("h2")?.textContent === "Customer experience");
  if (experiencePanel) {
    experiencePanel.innerHTML = `<h2>Customer experience</h2><p>Manage workspace-wide customer experience settings.</p><section class="settings-section"><h3>Customer data</h3><form id="customer-experience-form"><label>Image retention<select name="imageRetentionDays"><option value="1">1 day</option><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label><p class="field-help">Customer profiles are always deleted within 24 hours.</p><label>Reason for update<input name="reason" required maxlength="500" /></label><button class="button button--primary" type="submit">Update data settings</button><p id="customer-experience-status" class="form-status" role="status" aria-live="polite"></p></form></section><section class="settings-section"><h3>General try-on allowance</h3><p class="field-help">This overall value applies to every customer and resets every 24 hours.</p><form id="allowance-policy-form"><label>Default try-ons<input name="limit" type="number" min="0" max="100000" required /></label><button class="button button--quiet" type="submit">Save default try-ons</button><p id="allowance-admin-status" class="form-status" role="status" aria-live="polite"></p></form></section>`;
  }
  if (document.querySelector("#communications-history")) return;
  grid.insertAdjacentHTML("beforeend", `
    <article class="panel"><h2>Company logo</h2><p>Shown on the QR posters managed by your stores.</p><div id="company-logo-preview" class="company-logo-preview"><span>No logo uploaded</span></div><form id="company-logo-form"><label>Upload logo<input name="image" type="file" accept="image/png,image/jpeg,image/webp" required /></label><button class="button button--primary" type="submit">Save company logo</button><p id="company-logo-status" class="form-status" role="status" aria-live="polite"></p></form></article>
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
    const [result, storesResult] = await Promise.all([
      businessApi(`/business/tenants/${tenantId}/agents`),
      businessApi(`/business/tenants/${tenantId}/stores`),
    ]);
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
      const currentStore = storesResult.items.find((store) => store.store_id === agent.store_id);
      const storeName = document.createElement("span"); storeName.className = "status-chip";
      storeName.textContent = currentStore?.name || "Store unavailable";
      const move = document.createElement("button");
      move.className = "button button--quiet"; move.type = "button"; move.textContent = "Move store";
      const copyLink = document.createElement("button");
      copyLink.className = "button button--quiet"; copyLink.type = "button";
      copyLink.textContent = "Copy app URL";
      copyLink.addEventListener("click", async () => {
        if (!currentAgentAppUrl) { status.textContent = "Agent app URL is unavailable."; return; }
        try { await copyToClipboard(currentAgentAppUrl); status.textContent = `Agent app URL copied for ${agent.name}.`; }
        catch { status.textContent = "Could not copy automatically. Copy the URL from the Agent app URL panel."; }
      });
      move.addEventListener("click", () => openAgentMoveDialog(agent, storesResult.items));
      actions.append(storeName, move, copyLink); row.append(label, actions); list.append(row);
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
  if (!status) return;
  const dialog = document.querySelector("#agent-move-dialog");
  const closeMoveDialog = () => { pendingAgentMove = null; dialog?.close(); };
  document.querySelector("#agent-move-close")?.addEventListener("click", closeMoveDialog);
  document.querySelector("#agent-move-cancel")?.addEventListener("click", closeMoveDialog);
  dialog?.addEventListener("cancel", () => { pendingAgentMove = null; });
  document.querySelector("#agent-move-confirm")?.addEventListener("click", async () => {
    const destination = document.querySelector("#agent-move-destination");
    const moveStatus = document.querySelector("#agent-move-status");
    if (!pendingAgentMove || !destination.value) {
      moveStatus.textContent = "Select a destination store."; destination.focus(); return;
    }
    const button = document.querySelector("#agent-move-confirm"); button.disabled = true;
    moveStatus.textContent = "Moving agent…";
    try {
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      await businessApi(`/business/tenants/${tenantId}/agents/${pendingAgentMove.agent.agent_id}/store`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store_id: destination.value }),
      });
      const agentName = pendingAgentMove.agent.name;
      const storeName = pendingAgentMove.stores.find((store) => store.store_id === destination.value)?.name;
      closeMoveDialog(); status.textContent = `${agentName} moved to ${storeName}.`; await loadAgents();
    } catch (error) { moveStatus.textContent = error.message; button.disabled = false; }
  });
  if (!form) { loadAgentAppLink().then(loadAgents); return; }
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

function setupOwnerEmailChange() {
  const toggle = document.querySelector("#business-user-toggle");
  const menu = document.querySelector("#business-user-options");
  const dialog = document.querySelector("#owner-email-change-dialog");
  const form = document.querySelector("#owner-email-change-form");
  const status = document.querySelector("#owner-email-change-status");
  const codes = document.querySelector("#owner-email-change-codes");
  const submit = document.querySelector("#owner-email-change-submit");
  let challengeId = null;

  toggle?.addEventListener("click", () => {
    const opening = menu.hidden;
    menu.hidden = !opening;
    toggle.setAttribute("aria-expanded", String(opening));
  });
  document.addEventListener("click", (event) => {
    if (!menu || menu.hidden || event.target.closest(".business-user-menu")) return;
    menu.hidden = true;
    toggle?.setAttribute("aria-expanded", "false");
  });

  const openDialog = async () => {
    if (!dialog || !form || !status) return;
    if (menu) menu.hidden = true;
    toggle?.setAttribute("aria-expanded", "false");
    challengeId = null;
    form.reset();
    form.elements.newEmail.readOnly = false;
    codes.hidden = true;
    submit.disabled = true;
    status.textContent = "Loading current admin email…";
    dialog.showModal();
    try {
      const tenantId = localStorage.getItem("wearo_business_tenant_id");
      const contacts = await businessApi(`/business/tenants/${tenantId}/owner-contacts`);
      form.elements.currentEmail.value = contacts.email;
      status.textContent = "";
      form.elements.newEmail.focus();
    } catch (error) { status.textContent = error.message; }
  };
  document.querySelectorAll("[data-open-owner-email-change]").forEach((button) => {
    button.addEventListener("click", openDialog);
  });
  document.querySelector("#owner-email-change-close")?.addEventListener("click", () => {
    dialog.close();
  });
  dialog?.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  document.querySelector("#owner-email-change-request")?.addEventListener("click", async () => {
    if (!form.elements.newEmail.reportValidity()) return;
    const tenantId = localStorage.getItem("wearo_business_tenant_id");
    status.textContent = "Sending verification codes…";
    try {
      const result = await businessApi(
        `/business/tenants/${tenantId}/owner-email-change/request`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_email: form.elements.newEmail.value }),
        },
      );
      challengeId = result.challenge_id;
      form.elements.currentEmail.value = result.current_email;
      form.elements.newEmail.value = result.new_email;
      form.elements.newEmail.readOnly = true;
      codes.hidden = false;
      submit.disabled = false;
      status.textContent = result.message;
      form.elements.currentEmailOtp.focus();
    } catch (error) { status.textContent = error.message; }
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!challengeId || !form.reportValidity()) return;
    const tenantId = localStorage.getItem("wearo_business_tenant_id");
    submit.disabled = true;
    status.textContent = "Verifying both email addresses…";
    try {
      await businessApi(`/business/tenants/${tenantId}/owner-email-change/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          challenge_id: challengeId,
          current_email_otp: form.elements.currentEmailOtp.value,
          new_email_otp: form.elements.newEmailOtp.value,
        }),
      });
      sessionStorage.removeItem(BUSINESS_AUTH_KEY);
      localStorage.removeItem("wearo_business_tenant_id");
      window.location.assign("/business/sign-in?admin-email-updated=1");
    } catch (error) {
      status.textContent = error.message;
      submit.disabled = false;
    }
  });
}

function attachBusinessInteractions(section) {
  setupOwnerEmailChange();
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
    if (new URLSearchParams(window.location.search).has("admin-email-updated")) {
      status.textContent = "Admin email updated. Sign in with the new email address.";
    }
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
    const reportingDate = (daysAgo = 0) => {
      const parts = Object.fromEntries(new Intl.DateTimeFormat("en", {
        timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
      }).formatToParts(new Date()).map(({ type, value }) => [type, value]));
      const value = new Date(Date.UTC(
        Number(parts.year), Number(parts.month) - 1, Number(parts.day) - daysAgo,
      ));
      return [
        value.getUTCFullYear(),
        String(value.getUTCMonth() + 1).padStart(2, "0"),
        String(value.getUTCDate()).padStart(2, "0"),
      ].join("-");
    };
    const formatRangeLabel = (dateFrom, dateTo) => {
      const display = (value) => new Intl.DateTimeFormat("en-IN", {
        day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
      }).format(new Date(`${value}T00:00:00Z`));
      if (!dateFrom || !dateTo) return "";
      return dateFrom === dateTo ? display(dateFrom) : `${display(dateFrom)} to ${display(dateTo)}`;
    };
    const selectedRange = () => {
      const period = periodForm.elements.period.value;
      if (period === "custom") {
        const dateFrom = periodForm.elements.dateFrom.value;
        const dateTo = periodForm.elements.dateTo.value;
        return { dateFrom, dateTo, label: formatRangeLabel(dateFrom, dateTo) };
      }
      const daysAgo = period === "week" ? 6 : period === "month" ? 29 : 0;
      const dateFrom = reportingDate(daysAgo);
      const dateTo = reportingDate();
      return { dateFrom, dateTo, label: formatRangeLabel(dateFrom, dateTo) };
    };
    periodForm.elements.dateTo.max = reportingDate();
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
    setupAudienceStoreFilter();
  }
  if (section === "billing") {
    loadBusinessUsage();
    loadTryOnStatus().catch((error) => {
      document.querySelector("#try-on-control-status").textContent = error.message;
    });
    loadActionRates();
    loadRetailTryOnRate();
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
    const subscriptionDialog = document.querySelector("#business-subscription-dialog");
    const dialogTitle = document.querySelector("#business-subscription-dialog-title");
    const dialogCopy = document.querySelector("#business-subscription-dialog-copy");
    const keepSubscription = document.querySelector("#keep-business-subscription");
    const confirmSubscriptionAction = document.querySelector("#confirm-business-subscription-action");
    let pendingTryOnStatus = null;
    const closeSubscriptionDialog = () => {
      pendingTryOnStatus = null;
      subscriptionDialog.close();
    };
    document.querySelector("#close-business-subscription-dialog")?.addEventListener("click", closeSubscriptionDialog);
    keepSubscription?.addEventListener("click", closeSubscriptionDialog);
    subscriptionDialog?.addEventListener("cancel", () => { pendingTryOnStatus = null; });
    document.querySelector("#pause-try-ons")?.addEventListener("click", () => {
      pendingTryOnStatus = "PAUSED";
      dialogTitle.textContent = "Pause try-ons?";
      dialogCopy.textContent = "New try-ons will be temporarily disabled for your business and its users. Existing data will remain available for viewing.";
      keepSubscription.textContent = "Keep Try-ons Active";
      confirmSubscriptionAction.textContent = "Pause Try-ons";
      confirmSubscriptionAction.className = "button button--quiet";
      subscriptionDialog.showModal();
    });
    document.querySelector("#resume-try-ons")?.addEventListener("click", () => updateTryOnStatus("ACTIVE"));
    document.querySelector("#cancel-subscription")?.addEventListener("click", () => {
      pendingTryOnStatus = "CANCELLED";
      dialogTitle.textContent = "Cancel subscription?";
      dialogCopy.textContent = "New try-ons will be disabled for your business and its users. Existing data will remain available for viewing.";
      keepSubscription.textContent = "Keep Subscription";
      confirmSubscriptionAction.textContent = "Cancel Subscription";
      confirmSubscriptionAction.className = "button button--danger";
      subscriptionDialog.showModal();
    });
    confirmSubscriptionAction?.addEventListener("click", async () => {
      if (!pendingTryOnStatus) return;
      confirmSubscriptionAction.disabled = true;
      const changed = await updateTryOnStatus(pendingTryOnStatus);
      confirmSubscriptionAction.disabled = false;
      if (changed) closeSubscriptionDialog();
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
  if (section === "smart-ads") setupSmartAds();
  if (section === "settings") {
    setupBusinessAdminPanels();
    loadBillingProfile();
    loadOwnerContacts();
    loadCustomerExperienceSettings();
    loadSensitiveAudit();
    loadOperatingProfile();
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
      if (!editor) return;
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
        status.textContent = "Saving…";
        const result = await businessApi(`/business/tenants/${tenantId}/operating-profile`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operating_profile: form.elements.operatingProfile.value,
            reason: form.elements.reason.value }),
        });
        status.textContent = `${operatingProfileLabel(result.operating_profile)} is now active.`;
        form.elements.reason.value = "";
        await loadOperatingProfile();
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
  const resolvedPathname = pathname.startsWith("/business/experience")
    ? "/business/dashboard"
    : pathname;
  if (resolvedPathname !== pathname) window.history.replaceState({}, "", resolvedPathname);
  const section = sectionFromPath(resolvedPathname);
  document.title = "Wearo Business";
  if (resolvedPathname.startsWith("/business/signup")) {
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
    customers: customersView,
    "smart-ads": smartAdsView,
    stores: storesView,
    agents: agentsView,
    billing: billingView,
    settings: settingsView,
  };
  root.innerHTML = businessFrame(section, views[section]());
  attachBusinessInteractions(section);
  if (section === "stores") setupStores();
  if (window.location.hash) {
    const targetId = decodeURIComponent(window.location.hash.slice(1));
    window.requestAnimationFrame(() => document.getElementById(targetId)?.scrollIntoView());
  }
}

export { sectionFromPath };
