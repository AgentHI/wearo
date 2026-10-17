import { brandMarkup } from "./brand.js";

const sections = [
  ["dashboard", "Overview"],
  ["catalog", "Catalogue"],
  ["customers", "Customers"],
  ["billing", "Plans & billing"],
  ["settings", "Settings"],
];

function sectionFromPath(pathname) {
  return sections.find(([id]) => pathname.startsWith(`/business/${id}`))?.[0] || "welcome";
}

function businessFrame(section, content) {
  const navigation = sections
    .map(
      ([id, label]) => `
        <a href="/business/${id}" ${section === id ? 'aria-current="page"' : ""}>
          <span class="business-nav__dot" aria-hidden="true"></span>${label}
        </a>`,
    )
    .join("");
  return `
    <div class="business-app">
      <aside class="business-sidebar">
        ${brandMarkup("/business")}
        <p class="business-sidebar__label">Business workspace</p>
        <nav class="business-nav" aria-label="Business workspace">${navigation}</nav>
        <a class="consumer-link" href="/app/">Open consumer app <span aria-hidden="true">↗</span></a>
      </aside>
      <div class="business-workspace">
        <header class="business-topbar">
          <div><span class="availability-dot" aria-hidden="true"></span> Beta workspace</div>
          <div class="business-user" aria-label="Current workspace"><span>WA</span><div><strong>Wearo Atelier</strong><small>Owner workspace</small></div></div>
        </header>
        <main id="main" class="business-main">${content}</main>
      </div>
    </div>`;
}

function welcomeView() {
  return `
    <div class="business-public">
      <header class="business-public__header">${brandMarkup("/business")}<nav><a href="/app/">Consumer app</a><a class="button button--quiet" href="/business/dashboard">Sign in</a></nav></header>
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
          <article><span>01</span><h2>Launch quickly</h2><p>Create a workspace, choose a plan, and prepare your catalogue for try-on.</p></article>
          <article><span>02</span><h2>Measure adoption</h2><p>See usage, completion, quality, and allowance signals without viewing private photos.</p></article>
          <article><span>03</span><h2>Stay in control</h2><p>Manage team access, consent language, retention policy, and provider availability.</p></article>
        </section>
      </main>
    </div>`;
}

function signupView() {
  return `
    <div class="business-auth">
      <div class="business-auth__brand">${brandMarkup("/business")}<a href="/app/">Consumer app ↗</a></div>
      <main id="main" class="business-auth__main">
        <section class="auth-card">
          <p class="eyebrow">Create your business workspace</p>
          <h1>Start with the essentials.</h1>
          <p class="hero__description">Set up your organisation now. Billing activation happens only after you explicitly confirm a payment provider checkout.</p>
          <form id="business-signup-form">
            <label>Business name<input name="businessName" autocomplete="organization" required /></label>
            <label>Work email<input name="email" type="email" autocomplete="email" required /></label>
            <label>Website <span>(optional)</span><input name="website" type="url" placeholder="https://" /></label>
            <label class="check"><input name="terms" type="checkbox" required /> I agree to the beta terms and privacy commitments.</label>
            <button class="button button--primary" type="submit">Create workspace</button>
            <p id="business-signup-status" class="form-status" role="status" aria-live="polite"></p>
          </form>
          <p class="auth-card__footer">Already evaluating Wearo? <a href="/business/dashboard">Open the demo workspace</a></p>
        </section>
        <aside class="auth-proof"><blockquote>“The right experience is not just a model call. It is consent, quality, operations, and a clear customer promise.”</blockquote><p>Built into every Wearo workflow.</p></aside>
      </main>
    </div>`;
}

function dashboardView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Overview</p><h1>Good morning, Wearo Atelier.</h1><p>Here is what is happening across your virtual try-on experience.</p></div><a class="button button--primary" href="/business/catalog">Add product</a></header>
    <section class="metric-grid" aria-label="Workspace metrics">
      <article><p>Try-ons this month</p><strong>0</strong><small>Waiting for launch traffic</small></article>
      <article><p>Completion rate</p><strong>—</strong><small>Available after first result</small></article>
      <article><p>Active products</p><strong>0</strong><small>Add the first catalogue item</small></article>
      <article><p>Quality acceptance</p><strong>—</strong><small>50-case gate required</small></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel panel--wide"><div class="panel__heading"><div><h2>Try-on activity</h2><p>Successful customer previews over the selected period.</p></div><select aria-label="Activity period"><option>Last 30 days</option><option>Last 7 days</option></select></div><div class="empty-chart"><div aria-hidden="true"></div><strong>No usage yet</strong><p>Activity appears here after your first customer generation.</p></div></article>
      <article class="panel"><div class="panel__heading"><div><h2>Launch readiness</h2><p>Complete these before customer traffic.</p></div></div><ul class="readiness-list"><li class="done"><span>✓</span>Workspace created</li><li><span>2</span>Connect billing</li><li><span>3</span>Add catalogue items</li><li><span>4</span>Pass quality evaluation</li></ul></article>
      <article class="panel panel--wide"><div class="panel__heading"><div><h2>Recent activity</h2><p>Operational events, never private customer photos.</p></div></div><div class="table-empty"><span aria-hidden="true">◎</span><strong>Your activity feed is ready</strong><p>Events will appear when your team starts configuring the workspace.</p></div></article>
    </section>`;
}

function catalogView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Catalogue</p><h1>Products</h1><p>Manage which apparel items can be used in customer try-ons.</p></div><button id="catalog-add" class="button button--primary" type="button">Add product</button></header>
    <section class="panel"><div class="toolbar"><label class="search-field"><span class="sr-only">Search products</span><input type="search" placeholder="Search products" /></label><select aria-label="Product status"><option>All statuses</option><option>Ready</option><option>Draft</option></select></div><div class="table-empty"><span aria-hidden="true">◇</span><strong>No products yet</strong><p>Add a clear product image and Wearo will prepare it for the supported try-on route.</p><button class="button button--quiet" type="button" data-catalog-add>Add first product</button></div><p id="catalog-status" class="form-status" role="status"></p></section>`;
}

function customersView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Customers</p><h1>Privacy-safe insights</h1><p>Understand aggregate adoption without browsing customer source photos.</p></div></header>
    <section class="metric-grid metric-grid--three"><article><p>Unique participants</p><strong>0</strong><small>Aggregate count only</small></article><article><p>Returning participants</p><strong>—</strong><small>Available after launch</small></article><article><p>Consent completion</p><strong>—</strong><small>Five attestations required</small></article></section>
    <section class="panel"><div class="table-empty"><span aria-hidden="true">◌</span><strong>No customer activity</strong><p>Customer identities and private photos are not exposed in this workspace.</p></div></section>`;
}

function billingView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Plans & billing</p><h1>Choose how you want to launch.</h1><p>Select a plan for evaluation. No charge occurs until a payment provider is connected and checkout is confirmed.</p></div></header>
    <section class="plan-grid">
      <article class="plan-card"><p class="plan-card__name">Pilot</p><h2>₹0 <small>/ beta</small></h2><p>Validate the experience with your internal team.</p><ul><li>1 workspace</li><li>Up to 50 evaluation looks</li><li>Quality report</li></ul><button class="button button--quiet plan-select" data-plan="Pilot" type="button">Select pilot</button></article>
      <article class="plan-card plan-card--featured"><span class="plan-badge">Recommended</span><p class="plan-card__name">Launch</p><h2>Custom</h2><p>Customer-facing rollout with operational support.</p><ul><li>Production usage allowance</li><li>Team access and analytics</li><li>Launch readiness review</li></ul><button class="button button--primary plan-select" data-plan="Launch" type="button">Request checkout</button></article>
      <article class="plan-card"><p class="plan-card__name">Scale</p><h2>Contact us</h2><p>Multiple storefronts and higher-volume workflows.</p><ul><li>Multiple workspaces</li><li>Priority quality evaluation</li><li>Custom retention controls</li></ul><button class="button button--quiet plan-select" data-plan="Scale" type="button">Talk to sales</button></article>
    </section>
    <section class="panel billing-note"><div><h2>Payment method</h2><p>No payment method connected. Wearo will never mark a plan paid from this screen until server-verified checkout is available.</p></div><span class="status-chip">Not connected</span><p id="billing-status" class="form-status" role="status" aria-live="polite"></p></section>`;
}

function settingsView() {
  return `
    <header class="page-heading"><div><p class="eyebrow">Settings</p><h1>Workspace controls</h1><p>Keep product identity, team access, and privacy expectations clear.</p></div></header>
    <section class="settings-grid"><article class="panel"><h2>Organisation</h2><form id="business-settings-form"><label>Workspace name<input name="name" value="Wearo Atelier" /></label><label>Support email<input name="support" type="email" placeholder="support@example.com" /></label><button class="button button--primary" type="submit">Save changes</button><p id="settings-status" class="form-status" role="status"></p></form></article><article class="panel"><h2>Customer experience</h2><dl class="settings-list"><div><dt>Jewellery generation</dt><dd><span class="status-chip">Disabled</span></dd></div><div><dt>Image retention</dt><dd>30 days</dd></div><div><dt>Profile deletion</dt><dd>Within 24 hours</dd></div><div><dt>Model training</dt><dd>Not authorised</dd></div></dl></article></section>`;
}

function attachBusinessInteractions(section) {
  if (section === "signup") {
    document.querySelector("#business-signup-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      sessionStorage.setItem(
        "wearo_business_draft",
        JSON.stringify({ name: form.elements.businessName.value }),
      );
      document.querySelector("#business-signup-status").innerHTML =
        'Workspace draft saved for this tab. <a href="/business/billing">Choose a plan</a>.';
    });
  }
  if (section === "billing") {
    document.querySelectorAll(".plan-select").forEach((button) => {
      button.addEventListener("click", () => {
        localStorage.setItem("wearo_business_plan", button.dataset.plan);
        document.querySelector("#billing-status").textContent =
          `${button.dataset.plan} selected. Checkout is not connected, so no charge was made.`;
      });
    });
  }
  if (section === "catalog") {
    document.querySelectorAll("#catalog-add, [data-catalog-add]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelector("#catalog-status").textContent =
          "Catalogue upload will activate with the business API. No product was submitted.";
      });
    });
  }
  if (section === "settings") {
    document.querySelector("#business-settings-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      document.querySelector("#settings-status").textContent = "Settings saved in this preview.";
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
  if (section === "welcome") {
    root.innerHTML = welcomeView();
    return;
  }
  const views = {
    dashboard: dashboardView,
    catalog: catalogView,
    customers: customersView,
    billing: billingView,
    settings: settingsView,
  };
  root.innerHTML = businessFrame(section, views[section]());
  attachBusinessInteractions(section);
}

export { sectionFromPath };
