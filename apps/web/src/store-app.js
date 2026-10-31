import { brandMarkup } from "./brand.js";

const API = "/api/v1";
const AUTH_KEY = "wearo_store_auth";
const TODAY = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function auth() {
  try { return JSON.parse(sessionStorage.getItem(AUTH_KEY) || "null"); } catch { return null; }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (auth()?.csrfToken && options.method && !["GET", "HEAD"].includes(options.method)) {
    headers.set("X-CSRF-Token", auth().csrfToken);
  }
  const response = await fetch(`${API}${path}`, { credentials: "same-origin", ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || "The request could not be completed.");
  return body;
}

function loginView() {
  return `<main id="main" class="agent-auth"><section class="agent-auth__brand">${brandMarkup("/store")}<span>Store</span></section>
    <section class="agent-login-card"><p class="eyebrow">Store administrator</p><h1>Sign in</h1>
    <p>Use the email address or mobile number assigned by your business administrator.</p>
    <form id="store-login"><label>Email or mobile<input name="destination" autocomplete="username" required /></label>
    <button id="store-send" class="button button--primary button--full" type="button">Send OTP</button>
    <div id="store-code" hidden><label>One-time code<input name="otp" inputmode="numeric" minlength="4" maxlength="8" /></label>
    <button class="button button--primary button--full" type="submit">Verify and sign in</button></div>
    <p id="store-status" class="form-status" role="status"></p></form></section></main>`;
}

function dashboardView(context, pathname) {
  const editMatch = pathname.match(/^\/store\/agents\/([0-9a-f-]+)\/edit\/?$/i);
  const editingId = editMatch?.[1] || "";
  const isEditor = pathname === "/store/agents/new" || Boolean(editingId);
  const isAdvertisements = pathname.startsWith("/store/advertisements");
  const content = isAdvertisements
    ? advertisementView()
    : isEditor
    ? `<header class="page-heading store-editor-heading"><div><a class="back-link" href="/store">← Back to agents</a><p class="eyebrow">Store team</p><h1 id="store-agent-title">${editingId ? "Edit agent" : "Add agent"}</h1><p>${editingId ? "Update this agent's name or sign-in mobile." : `Add an agent to ${context.name}.`}</p></div></header>
      <section class="panel store-editor"><div class="panel__heading"><div><h2>Agent details</h2><p>This agent belongs only to ${context.name}. Store transfers are managed by the business administrator.</p></div></div><form id="store-agent-form" data-agent-id="${editingId}"><div class="store-form-grid"><label>Name<input name="name" maxlength="120" autocomplete="name" required /><small class="field-help">The name shown in the Agent workspace.</small></label><label>Mobile number<input name="mobile" type="tel" autocomplete="tel" placeholder="+919876543210" required /><small class="field-help">Include the international country code.</small></label></div><div class="form-actions store-form-actions"><button class="button button--primary" type="submit">${editingId ? "Save changes" : "Add agent"}</button><a class="button button--quiet" href="/store">Cancel</a></div><p id="store-agent-status" class="form-status" role="status" aria-live="polite"></p></form></section>`
    : `<header class="page-heading"><div><p class="eyebrow">Store dashboard</p><h1>${context.name}</h1><p>Manage this store's team and monitor store operations.</p></div></header>
      <section class="metric-grid overview-metrics"><article class="metric-card--activity"><div><p>Store agents</p><span class="metric-icon">A</span></div><strong>${context.agents}</strong><small>Assigned to this store</small></article><article class="metric-card--activity"><div><p>Active agents</p><span class="metric-icon">✓</span></div><strong>${context.active_agents}</strong><small>Currently able to sign in</small></article><article class="metric-card--activity"><div><p>Business try-ons</p><span class="metric-icon">Σ</span></div><strong>${context.successful_try_ons}</strong><small>${context.total_try_ons} requested through the business-level QR</small></article></section>
      <section class="panel store-shop-link"><div class="panel__heading"><div><h2>Customer QR and URL</h2><p>This QR identifies ${context.name}, so customer sessions are attributed to this store.</p></div></div><p id="store-shop-status" class="form-status" role="status" aria-live="polite">Loading store link…</p><div class="form-actions"><a id="store-shop-url" class="button button--quiet" href="#" target="_blank" rel="noopener">Open customer URL</a><button id="store-copy-url" class="button button--quiet" type="button">Copy URL</button><a id="store-shop-qr" class="button button--primary" href="/api/v1/store/shop-qr.png">Download QR poster</a></div></section>
      <section class="panel store-directory"><div class="panel__heading"><div><h2>Store agents</h2><p>Agents assigned to ${context.name}. Transfers are completed by the business administrator.</p></div><div class="store-list-actions"><span id="store-agent-count" class="status-chip">Loading</span><a class="button button--primary" href="/store/agents/new">Add agent</a></div></div><div id="store-agent-list" class="store-list" aria-live="polite">Loading agents…</div></section>`;
  return `<div class="business-app store-app"><aside class="business-sidebar"><div class="business-sidebar__brand">${brandMarkup("/store")}<span>Store</span></div>
    <div class="workspace-switcher"><span class="workspace-switcher__mark">${context.name.slice(0, 2).toUpperCase()}</span><span><small>${context.business_name}</small><strong>${context.name}</strong></span></div>
    <nav class="business-nav"><a href="/store" ${isAdvertisements ? "" : 'aria-current="page"'}><span class="business-nav__icon">▦</span><span>Dashboard</span></a>${context.advertisements_enabled ? `<a href="/store/advertisements" ${isAdvertisements ? 'aria-current="page"' : ""}><span class="business-nav__icon">▣</span><span>Advertisement</span></a>` : ""}</nav>
    <div class="business-sidebar__footer"><button id="store-logout" class="business-signout" type="button">⇥ Sign out</button></div></aside>
    <div class="business-workspace"><header class="business-topbar"><div class="business-breadcrumb"><strong>${context.business_name}</strong><span>/</span><span>${context.name}</span></div></header>
    <main id="main" class="business-main">${content}</main></div></div>`;
}

function advertisementView() {
  return `<header class="page-heading"><div><p class="eyebrow">Premium Business</p><h1>Advertisements</h1><p>Create cards sized for the customer try-on area and choose one to run today.</p></div></header>
    <section class="advertisement-layout">
      <form id="advertisement-ai-form" class="panel advertisement-editor"><div class="panel__heading"><div><h2>Generate with AI</h2><p>Each card has up to 3 AI generation tries.</p></div><span id="advertisement-tries" class="status-chip">3 tries</span></div><input name="advertisementId" type="hidden" /><label>Card title<input name="title" maxlength="120" required placeholder="Weekend collection" /></label><label>Describe the card<textarea name="prompt" maxlength="1000" rows="5" required placeholder="A premium festive fashion campaign with rich plum and gold styling…"></textarea></label><div class="form-actions"><button class="button button--primary">✦ Generate card</button><button id="advertisement-cancel-edit" class="button button--quiet" type="button" hidden>Cancel edit</button></div><p class="form-status" role="status"></p></form>
      <form id="advertisement-upload-form" class="panel advertisement-editor"><div class="panel__heading"><div><h2>Upload a picture</h2><p>Images are center-cropped to 3:4 and limited to 768 × 1024, below the try-on canvas size.</p></div></div><label>Card title<input name="title" maxlength="120" required /></label><label class="advertisement-upload">Choose JPEG, PNG or WebP<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required /></label><button class="button button--primary">Upload and crop</button><p class="form-status" role="status"></p></form>
    </section>
    <section class="panel advertisement-library"><div class="panel__heading"><div><h2>Advertisement cards</h2><p>Select any card to activate it for today.</p></div><span id="advertisement-count" class="status-chip">Loading</span></div><div id="advertisement-list" class="advertisement-grid" aria-live="polite">Loading advertisements…</div></section>`;
}

async function loadAdvertisements() {
  const list = document.querySelector("#advertisement-list");
  const result = await api("/store/advertisements");
  document.querySelector("#advertisement-count").textContent = `${result.items.length} card${result.items.length === 1 ? "" : "s"}`;
  if (!result.items.length) { list.innerHTML = '<div class="table-empty"><span>▣</span><strong>No advertisements yet</strong><p>Generate a card or upload your own picture.</p></div>'; return; }
  list.innerHTML = result.items.map((item) => `<article class="advertisement-card${item.active_today ? " is-active" : ""}" data-advertisement-id="${item.advertisement_id}"><div class="advertisement-card__image"><img src="${API}/store/advertisements/${item.advertisement_id}/image" alt="${escapeHtml(item.title)}" />${item.active_today ? "<span>Active today</span>" : ""}</div><div class="advertisement-card__body"><div><strong>${escapeHtml(item.title)}</strong><small>${item.source === "AI" ? `AI generated · ${3 - item.ai_attempts} tries left` : "Uploaded and cropped"}</small></div><div class="advertisement-card__actions"><button class="button button--quiet" data-edit type="button">Edit</button><button class="button button--primary" data-activate type="button" ${item.active_today ? "disabled" : ""}>${item.active_today ? "Active" : "Activate today"}</button></div></div></article>`).join("");
  list.querySelectorAll("[data-activate]").forEach((button) => button.addEventListener("click", async () => { await api(`/store/advertisements/${button.closest("article").dataset.advertisementId}/activate`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active_date: TODAY() }) }); await loadAdvertisements(); }));
  list.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => { const item = result.items.find((entry) => entry.advertisement_id === button.closest("article").dataset.advertisementId); const form = document.querySelector("#advertisement-ai-form"); form.elements.advertisementId.value = item.advertisement_id; form.elements.title.value = item.title; form.elements.prompt.value = item.prompt || ""; form.querySelector("button[type=submit]").textContent = item.source === "AI" && item.ai_attempts < 3 ? "✦ Regenerate card" : "Save title"; form.querySelector("#advertisement-tries").textContent = `${3 - item.ai_attempts} tries left`; form.querySelector("#advertisement-cancel-edit").hidden = false; form.scrollIntoView({ behavior: "smooth" }); }));
}

function attachAdvertisements() {
  const aiForm = document.querySelector("#advertisement-ai-form"), uploadForm = document.querySelector("#advertisement-upload-form");
  aiForm.addEventListener("submit", async (event) => { event.preventDefault(); const status = aiForm.querySelector(".form-status"), id = aiForm.elements.advertisementId.value; status.textContent = "Creating your advertisement…"; try { const payload = { title: aiForm.elements.title.value, prompt: aiForm.elements.prompt.value, advertisement_id: id || null }; if (id && !payload.prompt) await api(`/store/advertisements/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: payload.title }) }); else await api("/store/advertisements/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); aiForm.reset(); status.textContent = "Advertisement saved."; await loadAdvertisements(); } catch (error) { status.textContent = error.message; } });
  uploadForm.addEventListener("submit", async (event) => { event.preventDefault(); const status = uploadForm.querySelector(".form-status"), body = new FormData(uploadForm); status.textContent = "Uploading and cropping…"; try { await api("/store/advertisements/upload", { method: "POST", body }); uploadForm.reset(); status.textContent = "Advertisement uploaded."; await loadAdvertisements(); } catch (error) { status.textContent = error.message; } });
  document.querySelector("#advertisement-cancel-edit").addEventListener("click", () => { aiForm.reset(); document.querySelector("#advertisement-cancel-edit").hidden = true; document.querySelector("#advertisement-tries").textContent = "3 tries"; aiForm.querySelector("button[type=submit]").textContent = "✦ Generate card"; });
  loadAdvertisements().catch((error) => { document.querySelector("#advertisement-list").textContent = error.message; });
}

async function loadAgents(context) {
  const list = document.querySelector("#store-agent-list");
  const result = await api("/store/agents");
  if (!list) return result.items;
  list.replaceChildren();
  const count = document.querySelector("#store-agent-count");
  if (count) count.textContent = `${result.items.length} agent${result.items.length === 1 ? "" : "s"}`;
  if (!result.items.length) {
    list.innerHTML = `<div class="table-empty"><span aria-hidden="true">♧</span><strong>No agents yet</strong><p>Add the first agent for ${context.name}.</p><a class="button button--primary" href="/store/agents/new">Add agent</a></div>`;
    return result.items;
  }
  for (const agent of result.items) {
    const row = document.createElement("article"); row.className = "store-row store-agent-row";
    row.innerHTML = `<div class="store-row__identity"><span class="store-row__mark" aria-hidden="true"></span><div><div class="store-row__title"><strong></strong><span class="status-chip"></span></div><small class="agent-mobile"></small></div></div><div class="store-agent-row__access"><small>Access</small><strong>Agent workspace</strong></div><div class="agent-row__actions"><a class="button button--quiet">Edit agent</a><button class="button button--danger" type="button">Delete</button></div>`;
    row.querySelector(".store-row__mark").textContent = agent.name.slice(0, 2).toUpperCase();
    row.querySelector(".store-row__title strong").textContent = agent.name;
    row.querySelector(".store-row__title .status-chip").textContent = agent.status === "ACTIVE" ? "Active" : agent.status;
    row.querySelector(".agent-mobile").textContent = agent.normalized_mobile;
    row.querySelector("a").href = `/store/agents/${agent.agent_id}/edit`;
    const remove = row.querySelector("button");
    remove.addEventListener("click", async () => { if (!window.confirm(`Delete ${agent.name}?`)) return; await api(`/store/agents/${agent.agent_id}`, { method: "DELETE" }); await loadAgents(context); });
    list.append(row);
  }
  return result.items;
}

function attachDashboard(context, pathname) {
  const form = document.querySelector("#store-agent-form");
  document.querySelector("#store-logout").addEventListener("click", async () => { try { await api("/store/logout", { method: "POST" }); } catch {} sessionStorage.removeItem(AUTH_KEY); renderStoreApp(document.querySelector("#app"), "/store"); });
  if (pathname.startsWith("/store/advertisements")) { attachAdvertisements(); return; }
  if (!form) {
    loadStoreShopLink();
    loadAgents(context).catch((error) => { document.querySelector("#store-agent-list").textContent = error.message; });
    return;
  }
  const id = form.dataset.agentId;
  if (id) loadAgents(context).then((agents) => { const agent = agents.find((item) => item.agent_id === id); if (!agent) throw new Error("Agent unavailable."); form.elements.name.value = agent.name; form.elements.mobile.value = agent.normalized_mobile; document.querySelector("#store-agent-title").textContent = `Edit ${agent.name}`; }).catch((error) => { document.querySelector("#store-agent-status").textContent = error.message; });
  form.addEventListener("submit", async (event) => { event.preventDefault(); const status = document.querySelector("#store-agent-status"); status.textContent = id ? "Saving changes…" : "Adding agent…"; try { await api(`/store/agents${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.elements.name.value, mobile: form.elements.mobile.value, store_id: context.store_id }) }); window.history.pushState({}, "", "/store"); renderStoreApp(document.querySelector("#app"), "/store"); } catch (error) { status.textContent = error.message; } });
}

async function loadStoreShopLink() {
  const status = document.querySelector("#store-shop-status");
  const link = document.querySelector("#store-shop-url");
  const copy = document.querySelector("#store-copy-url");
  if (!status || !link || !copy) return;
  try {
    const result = await api("/store/shop-link");
    link.href = result.shop_url;
    status.textContent = `${result.caption} · Store code ${result.store_code}`;
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(result.shop_url);
        status.textContent = "Customer URL copied.";
      } catch {
        status.textContent = "Open the customer URL and copy it from your browser.";
      }
    });
  } catch (error) {
    status.textContent = error.message;
    link.hidden = true; copy.hidden = true;
  }
}

function attachLogin(root) {
  const form = root.querySelector("#store-login"), status = root.querySelector("#store-status"); let challenge;
  root.querySelector("#store-send").addEventListener("click", async () => { try { const result = await api("/auth/email-otp/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ destination: form.elements.destination.value, purpose: "BUSINESS_SIGN_IN" }) }); challenge = result.challenge_id; root.querySelector("#store-code").hidden = false; status.textContent = result.message; } catch (error) { status.textContent = error.message; } });
  form.addEventListener("submit", async (event) => { event.preventDefault(); try { const result = await api("/auth/store-otp/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ challenge_id: challenge, code: form.elements.otp.value }) }); sessionStorage.setItem(AUTH_KEY, JSON.stringify({ csrfToken: result.csrf_token })); renderStoreApp(root); } catch (error) { status.textContent = error.message; } });
}

export async function renderStoreApp(root, pathname = window.location.pathname) {
  document.documentElement.dataset.experience = "business"; document.title = "Wearo Store";
  if (!auth()) { root.innerHTML = loginView(); attachLogin(root); return; }
  try { const context = await api("/store/me"); root.innerHTML = dashboardView(context, pathname); attachDashboard(context, pathname); }
  catch { sessionStorage.removeItem(AUTH_KEY); root.innerHTML = loginView(); attachLogin(root); }
}
