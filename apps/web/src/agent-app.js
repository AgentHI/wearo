import { brandMarkup } from "./brand.js";

const API_BASE = "/api/v1";
const AUTH_KEY = "wearo_agent_auth";
let installPrompt = null;

function agentLaunch() {
  const match = window.location.pathname.match(/^\/agent\/([^/]+)\/?$/);
  const key = new URLSearchParams(window.location.search).get("key");
  return match && key ? { business: decodeURIComponent(match[1]), key } : null;
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  document.querySelector("#agent-install")?.removeAttribute("hidden");
});

window.addEventListener("appinstalled", () => {
  installPrompt = null;
  document.querySelector("#agent-install")?.setAttribute("hidden", "");
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function readAuth() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY) || "null"); } catch { return null; }
}

async function agentApi(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const auth = readAuth();
  if (auth?.csrfToken && options.method && !["GET", "HEAD"].includes(options.method)) {
    headers.set("X-CSRF-Token", auth.csrfToken);
  }
  const launch = agentLaunch();
  let requestPath = path;
  if (launch && path.startsWith("/agent/") && path !== "/agent/logout") {
    const separator = path.includes("?") ? "&" : "?";
    requestPath = `${path}${separator}business=${encodeURIComponent(launch.business)}&key=${encodeURIComponent(launch.key)}`;
  }
  const response = await fetch(`${API_BASE}${requestPath}`, { credentials: "same-origin", ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || "The request could not be completed.");
  return body;
}

function signInView() {
  return `<main id="main" class="agent-auth">
    <section class="agent-auth__brand">${brandMarkup("/agent")}<span>Agent</span></section>
    <section class="agent-login-card">
      <p class="eyebrow">Business agent access</p><h1>Welcome back</h1>
      <p>Sign in with the mobile number your business administrator added.</p>
      <form id="agent-login-form">
        <label>Mobile number<input name="mobile" type="tel" inputmode="tel" autocomplete="tel" placeholder="+91 98765 43210" required /></label>
        <button id="agent-send-otp" class="button button--primary button--full" type="button">Send OTP</button>
        <div id="agent-otp-step" hidden>
          <label>6-digit OTP<input name="otp" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" /></label>
          <button class="button button--primary button--full" type="submit">Verify & sign in</button>
          <button id="agent-resend-otp" class="agent-text-button" type="button">Resend OTP</button>
        </div>
        <p id="agent-login-status" class="form-status" role="status" aria-live="polite"></p>
      </form>
      <small>Your session stays active for 30 days on this device.</small>
    </section>
  </main>`;
}

function dashboardView(context) {
  const businessName = escapeHtml(context.display_name);
  const agentName = escapeHtml(context.name);
  const launch = agentLaunch();
  const businessMark = context.logo_asset_id
    ? `<img src="${API_BASE}/public/shops/${encodeURIComponent(launch.business)}/logo?key=${encodeURIComponent(launch.key)}" alt="${businessName} logo" />`
    : `<span aria-hidden="true">${businessName.slice(0, 1).toUpperCase()}</span>`;
  const tryOnsActive = context.try_on_status === "ACTIVE";
  const statusTitle = context.try_on_status === "PAUSED"
    ? "Try-ons are paused"
    : "Subscription is cancelled";
  const statusMessage = `${statusTitle}. Please contact your admin.`;
  const qrContent = tryOnsActive
    ? `<img src="${API_BASE}/agent/shop-qr.png?business=${encodeURIComponent(launch.business)}&key=${encodeURIComponent(launch.key)}" alt="QR code for ${businessName}" />`
    : `<div class="agent-qr-locked" role="img" aria-label="QR scanning unavailable"><span aria-hidden="true">⌑</span><strong>QR unavailable</strong><small>New try-ons are blocked</small></div>`;
  return `<div class="agent-app">
    <header class="agent-header"><div class="agent-header__brand">${brandMarkup("/agent")}<strong class="agent-wordmark-name">Wearo.ai</strong></div><div class="agent-header__actions"><button id="agent-install" class="agent-install-button" type="button" hidden>Install</button><button id="agent-logout" class="agent-avatar" type="button" aria-label="Sign out ${agentName}" title="Sign out"><span>${agentName.slice(0, 1).toUpperCase()}</span></button></div></header>
    <main id="main" class="agent-main agent-main--screens">
      <div id="agent-invite-screen" class="agent-screen">
        <section id="home" class="agent-home-card">
          <div class="agent-business-logo">${businessMark}</div>
          <div class="agent-home-card__copy"><p class="agent-greeting">Welcome back, ${agentName}</p><h1>${businessName}</h1><span>Agent workspace · Powered by Wearo.ai</span></div>
        </section>
        <section class="agent-scan-card"><div><p class="eyebrow">In-store QR</p><h2>Invite a customer</h2><p>Ask the customer to scan and start a private virtual try-on.</p></div><div id="agent-business-status" class="agent-business-status" role="status" aria-live="polite" ${tryOnsActive ? "hidden" : ""}><span class="agent-business-status__icon" aria-hidden="true">!</span><div><strong>${statusTitle}</strong><p>${statusMessage}</p><small>Customer QR scanning is disabled until your administrator changes the business status.</small></div></div><div class="agent-qr${tryOnsActive ? "" : " agent-qr--locked"}">${qrContent}</div></section>
        <button id="agent-open-tryons" class="button button--primary button--full agent-manage-button" type="button"><span aria-hidden="true">＋</span> Manage try-ons</button>
      </div>
      <div id="agent-tryons-screen" class="agent-screen" hidden>
        <button id="agent-back" class="agent-back-button" type="button" aria-label="Back to QR invite"><span aria-hidden="true">←</span> Back</button>
        <section id="customer" class="agent-allowance-card">
        <div class="agent-section-heading"><span class="agent-section-icon" aria-hidden="true">＋</span><div><p class="eyebrow">Customer access</p><h2>Manage try-ons</h2></div></div>
        <p class="agent-section-copy">Enter a customer mobile number to check usage or add more try-ons.</p>
        <form id="agent-customer-form">
          <label>Mobile number<div class="agent-phone-field"><span>+91</span><input name="mobile" type="tel" inputmode="numeric" autocomplete="tel" placeholder="99800 63178" required /></div></label>
          <button class="button button--primary button--full" type="submit">View customer balance</button>
        </form>
        <div id="agent-customer-result" class="agent-customer-result" hidden>
          <div class="agent-balance-grid"><div class="is-primary"><span>Remaining</span><strong id="agent-remaining">0</strong></div><div><span>Allotted</span><strong id="agent-limit">0</strong></div><div><span>Used</span><strong id="agent-used">0</strong></div></div>
          <form id="agent-add-form"><label>Add try-ons<input name="amount" type="number" inputmode="numeric" min="1" max="100" value="1" required /></label><button class="button button--primary" type="submit">Add to customer</button></form>
        </div>
        <p id="agent-customer-status" class="form-status" role="status" aria-live="polite"></p>
        </section>
      </div>
    </main>
  </div>`;
}

function attachLogin(root) {
  const form = root.querySelector("#agent-login-form");
  const status = root.querySelector("#agent-login-status");
  const step = root.querySelector("#agent-otp-step");
  let challengeId = null;
  let resendTimer = null;
  const requestOtp = async () => {
    status.textContent = "Sending OTP…";
    try {
      const result = await agentApi("/auth/email-otp/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ destination: form.elements.mobile.value, purpose: "BUSINESS_SIGN_IN" }) });
      challengeId = result.challenge_id; step.hidden = false; form.elements.otp.focus();
      status.textContent = result.message || "OTP sent.";
      let seconds = 60; const resend = root.querySelector("#agent-resend-otp"); resend.disabled = true;
      clearInterval(resendTimer); resendTimer = setInterval(() => { seconds -= 1; resend.textContent = seconds > 0 ? `Resend in ${seconds}s` : "Resend OTP"; if (seconds <= 0) { clearInterval(resendTimer); resend.disabled = false; } }, 1000);
    } catch (error) { status.textContent = error.message; }
  };
  root.querySelector("#agent-send-otp").addEventListener("click", requestOtp);
  root.querySelector("#agent-resend-otp").addEventListener("click", requestOtp);
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); status.textContent = "Verifying OTP…";
    try {
      const result = await agentApi("/auth/agent-otp/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ challenge_id: challengeId, code: form.elements.otp.value }) });
      localStorage.setItem(AUTH_KEY, JSON.stringify({ csrfToken: result.csrf_token, expiresAt: result.expires_at }));
      const context = await agentApi("/agent/me"); renderDashboard(root, context);
    } catch (error) { localStorage.removeItem(AUTH_KEY); status.textContent = error.message; }
  });
}

function renderAllowance(result, root) {
  const customer = result.customer || (result.user ? {
    mobile: result.user.normalized_mobile,
    allotted: result.user.effective_limit,
    used: result.user.used_count,
    remaining: result.user.remaining,
  } : null);
  if (!customer || customer.remaining == null) {
    throw new Error("Customer allowance data is unavailable. Refresh the app and try again.");
  }
  root.querySelector("#agent-customer-result").hidden = false;
  root.querySelector("#agent-remaining").textContent = customer.remaining;
  root.querySelector("#agent-limit").textContent = customer.allotted;
  root.querySelector("#agent-used").textContent = customer.used;
}

function renderDashboard(root, context) {
  root.innerHTML = dashboardView(context);
  let activeMobile = "";
  const inviteScreen = root.querySelector("#agent-invite-screen");
  const tryonsScreen = root.querySelector("#agent-tryons-screen");
  const tryOnsActive = context.try_on_status === "ACTIVE";
  if (!tryOnsActive) {
    const addForm = root.querySelector("#agent-add-form");
    addForm.setAttribute("aria-disabled", "true");
    for (const control of addForm.elements) control.disabled = true;
    root.querySelector(".agent-section-copy").textContent =
      "Enter a customer mobile number to view existing try-on usage.";
  }
  const status = root.querySelector("#agent-customer-status");
  const installButton = root.querySelector("#agent-install");
  const standalone = window.matchMedia("(display-mode: standalone)").matches
    || window.navigator.standalone === true;
  installButton.hidden = standalone || !installPrompt;
  installButton.addEventListener("click", async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    installButton.hidden = true;
  });
  root.querySelector("#agent-open-tryons").addEventListener("click", () => {
    inviteScreen.hidden = true;
    tryonsScreen.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
    root.querySelector("#agent-customer-form input").focus();
  });
  root.querySelector("#agent-back").addEventListener("click", () => {
    tryonsScreen.hidden = true;
    inviteScreen.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  root.querySelector("#agent-customer-form").addEventListener("submit", async (event) => {
    event.preventDefault(); activeMobile = event.currentTarget.elements.mobile.value; status.textContent = "Checking balance…";
    try { renderAllowance(await agentApi(`/agent/allowances?mobile=${encodeURIComponent(activeMobile)}`), root); status.textContent = "Balance is up to date."; } catch (error) { status.textContent = error.message; }
  });
  root.querySelector("#agent-add-form").addEventListener("submit", async (event) => {
    event.preventDefault(); status.textContent = "Adding try-ons…";
    try { const result = await agentApi("/agent/allowances", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mobile: activeMobile, action: "ADD", amount: Number(event.currentTarget.elements.amount.value) }) }); renderAllowance(result, root); status.textContent = "Try-ons added. The customer app now shows the updated balance."; } catch (error) { status.textContent = error.message; }
  });
  root.querySelector("#agent-logout").addEventListener("click", async () => { try { await agentApi("/agent/logout", { method: "POST" }); } catch {} localStorage.removeItem(AUTH_KEY); renderAgentApp(root); });
}

export async function renderAgentApp(root) {
  document.documentElement.dataset.experience = "agent"; document.title = "Wearo Agent";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", "#3b1746");
  document.querySelector('link[rel="manifest"]')?.remove();
  const launch = agentLaunch();
  if (!launch) {
    root.innerHTML = `<main id="main" class="agent-auth"><section class="agent-login-card"><p class="eyebrow">Invalid agent link</p><h1>Open your business agent URL</h1><p>Ask your business administrator for the Agent app link created for this workspace.</p></section></main>`;
    return;
  }
  const manifest = document.createElement("link");
  manifest.rel = "manifest";
  manifest.href = `${API_BASE}/public/agent-manifest?business=${encodeURIComponent(launch.business)}&key=${encodeURIComponent(launch.key)}`;
  document.head.append(manifest);
  if (readAuth()) {
    try { renderDashboard(root, await agentApi("/agent/me")); return; } catch { localStorage.removeItem(AUTH_KEY); }
  }
  root.innerHTML = signInView(); attachLogin(root);
}
