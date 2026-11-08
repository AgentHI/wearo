import { wearoConfirm } from "../../../apps/web/src/wearo-dialog.js";

const API = "/api/cost-lab";
const NAV = [
  ["", "Overview"], ["providers", "Providers"], ["models", "Models & pricing"],
  ["datasets", "Dataset"], ["benchmarks", "Run benchmark"], ["results", "Results"], ["compare", "Compare"], ["final-checks", "Final checks"], ["promoted-models", "Promoted models"], ["knowledge", "Knowledge"],
];

const escapeHtml = (value) => {
  const node = document.createElement("span"); node.textContent = String(value ?? ""); return node.innerHTML;
};
const money = (value, currency = "USD") => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: currency === "USD" ? 6 : 2 }).format(Number(value || 0));
const VIEW_ICON = `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>`;
const DELETE_ICON = `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg>`;
function iconifyActions(root, selector, icon, label) {
  root.querySelectorAll(selector).forEach(action => {
    if (action.classList.contains("cost-icon-action")) return;
    action.classList.add("cost-icon-action");
    action.innerHTML = icon;
    action.setAttribute("aria-label", label);
    action.title = label;
  });
}
function syncActionIcons(root) {
  iconifyActions(root, "[data-source-url], [data-final-id], [data-view-benchmark], [data-view-comparison], .cost-row-actions a[href*='/knowledge/']", VIEW_ICON, "View");
  iconifyActions(root, "[data-delete-final-id], [data-delete-asset], [data-delete-benchmark], [data-delete-result], [data-delete-knowledge]", DELETE_ICON, "Delete");
}
let actionIconObserver;
async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, { credentials: "same-origin", ...options, headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...(options.headers || {}) } });
  if (response.status === 401 && path !== "/auth/session") throw Object.assign(new Error("SESSION_EXPIRED"), { status: 401 });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "object" && detail ? [detail.message, detail.upstream_status ? `HTTP ${detail.upstream_status}` : "", detail.request_id ? `request ${detail.request_id}` : "", detail.generation_id ? `generation ${detail.generation_id}` : ""].filter(Boolean).join(" · ") : detail;
    throw new Error(message || data.message || "Request failed");
  }
  return data;
}
function route(pathname) { return pathname.replace(/^\/admin\/cost-lab\/?/, "").split("/")[0]; }
function go(path) { history.pushState({}, "", `/admin/cost-lab${path ? `/${path}` : ""}`); window.dispatchEvent(new PopStateEvent("popstate")); }

function loginView() {
  return `<main class="admin-auth cost-lab-auth"><section class="admin-login-card"><img class="admin-brand" src="/wearo-brand.png" alt="Wearo.ai"><p class="eyebrow">Model Cost Lab</p><h1>Cost Lab sign in</h1><p>This workspace uses a dedicated session, separate from Wearo Super Admin.</p><form id="cost-login"><label>Username<input name="username" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button class="button button--primary">Sign in</button><p class="form-status form-status--error" role="alert"></p></form></section></main>`;
}
function shell(active, content) {
  return `<div class="cost-lab admin-shell"><aside class="admin-sidebar"><div class="admin-sidebar__brand"><a class="brand-white-bg" href="/admin/cost-lab"><img src="/wearo-brand_white_bg.png" alt="Wearo.ai"></a><span>Model Cost Lab</span></div><p class="admin-sidebar__label">Benchmark workspace</p><nav class="admin-navigation">${NAV.map(([slug,label]) => `<a href="/admin/cost-lab${slug ? `/${slug}` : ""}" class="${active===slug?"is-active":""}"><span>${slug === "" ? "◈" : "◇"}</span>${label}</a>`).join("")}</nav><div class="admin-identity"><button id="cost-logout" class="button button--quiet">Sign out</button></div></aside><main class="admin-main"><header class="admin-topbar"><div><p class="eyebrow">Wearo Cost Admin module</p><h1>${escapeHtml(NAV.find(([slug]) => slug === active)?.[1] || "Cost Lab")}</h1></div><span class="cost-lab-badge">USD canonical</span></header><div class="admin-content">${content}</div></main></div>`;
}
const overview = () => `<section class="cost-hero"><div><p class="eyebrow">Controlled model evaluation</p><h2>Benchmark image models with cost you can audit.</h2><p>Fixed datasets, reproducible internal pairings, pricing snapshots and provider-reported usage across Low, Medium and High quality.</p><button class="button button--primary" data-go="benchmarks">Run a benchmark</button></div><div class="cost-guardrails"><strong>Consistent evaluation</strong><span>10 try-ons per quality</span><span>Finite retries only</span><span>Independent credentials and schema</span></div></section><div id="cost-overview-totals" class="admin-platform-metrics"><article class="admin-metric-card"><div><span>Providers</span><span class="metric-icon">◇</span></div><strong>—</strong><small>Configured model providers</small></article><article class="admin-metric-card"><div><span>Models</span><span class="metric-icon">✦</span></div><strong>—</strong><small>Models available for testing</small></article><article class="admin-metric-card"><div><span>Quality profiles</span><span class="metric-icon">◈</span></div><strong>3</strong><small>Low, Medium and High</small></article><article class="admin-metric-card"><div><span>Try-ons per benchmark</span><span class="metric-icon">◎</span></div><strong>30</strong><small>Ten per quality profile</small></article></div><section class="admin-data-panel cost-overview-list"><h2>Providers, models and average cost</h2><div id="cost-overview-models">Loading…</div></section><section class="admin-data-panel cost-overview-list cost-overview-list--qualities"><h2>Benchmark runs by model and quality</h2><div id="cost-overview-qualities">Loading…</div></section>`;

function providersView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Connected services</p><h2>AI Model Providers</h2><p>Review connection type, credential storage, pricing references and availability.</p></div><button id="open-provider-dialog" class="button button--primary" type="button">+ Add provider</button></div><div id="provider-list">Loading…</div></section><dialog id="provider-dialog" class="cost-dialog"><form id="provider-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Provider connection</p><h2>Add provider</h2></div><button id="close-provider-dialog" class="cost-dialog__close" type="button" aria-label="Close add provider dialog">×</button></div><p class="field-help">Connect an image-generation provider. Credentials remain encrypted or referenced from the server environment.</p><label>Provider name<input name="name" required placeholder="Example: OpenAI"></label><label>Adapter type<select name="provider_type"><option value="OPENAI_COMPATIBLE">OpenAI Images compatible</option><option value="BYTEPLUS">BytePlus ModelArk</option><option value="BFL">Black Forest Labs (BFL)</option><option value="SECRET_REFERENCE">Future/custom configuration</option></select></label><label>API base URL<input name="api_base_url" type="url" value="https://api.openai.com/v1"></label><label>API key<input name="api_key" type="password" autocomplete="off" placeholder="Stored encrypted"><small>Encrypted server-side and never returned to the browser.</small></label><label>Environment secret reference<input name="secret_reference" placeholder="env:WEARO_OPENAI_API_KEY"><small>Use this instead of entering a key when it already exists in the server environment.</small></label><div class="cost-dialog__section"><strong>Provider pricing reference</strong><small>Record where the model prices configured under this provider came from.</small></div><label>Pricing reference URL<input name="pricing_reference_url" type="url" placeholder="https://provider.example/pricing"></label><label>Pricing reference notes<textarea name="pricing_reference_text" rows="4" maxlength="10000" placeholder="Pricing tier, effective date, units, or copied provider text"></textarea></label><div class="cost-dialog__actions"><button id="cancel-provider-dialog" class="button button--quiet" type="button">Cancel</button><button class="button button--primary" type="submit">Save provider</button></div><p class="form-status"></p></form></dialog>`; }
function modelsView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Cost modelling catalogue</p><h2>AI Models and Pricing</h2><p>Configure pricing, then verify each model with a sample generation or mark it tested manually.</p></div><button id="open-model-dialog" class="button button--primary" type="button">+ Add model and pricing</button></div><div id="model-list">Loading…</div></section><dialog id="model-dialog" class="cost-dialog"><form id="model-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Cost modelling</p><h2>Add model and pricing</h2></div><button class="cost-dialog__close" data-close-dialog="model-dialog" type="button" aria-label="Close add model dialog">×</button></div><label>Provider<select name="provider_id" required></select></label><label>Display name<input name="name" required></label><label>API model identifier<input name="api_identifier" required></label><label>Version<input name="version" placeholder="Optional"></label><div class="cost-dialog__section"><strong>Token pricing</strong><small>Optional USD prices per 1 million tokens.</small></div><label>Image input — USD / 1M tokens<input name="image_input_price_usd_per_million" type="number" min="0" step="0.000001"></label><label>Image output — USD / 1M tokens<input name="image_output_price_usd_per_million" type="number" min="0" step="0.000001"></label><div class="cost-dialog__section"><strong>Output image pricing by quality</strong><small>Optional USD price for each generated image. At least one price on this form is required.</small></div><label>Low quality — USD / image<input name="output_image_price_usd_low" type="number" min="0" step="0.000001"></label><label>Medium quality — USD / image<input name="output_image_price_usd_medium" type="number" min="0" step="0.000001"></label><label>High quality — USD / image<input name="output_image_price_usd_high" type="number" min="0" step="0.000001"></label><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="model-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Save model and pricing</button></div><p class="form-status"></p></form></dialog><dialog id="model-test-dialog" class="cost-dialog"><form id="model-test-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Connection test</p><h2>Test sample generation</h2></div><button class="cost-dialog__close" data-close-dialog="model-test-dialog" type="button" aria-label="Close model test dialog">×</button></div><p class="field-help" id="model-test-name"></p><label>Prompt<textarea name="prompt" rows="5" maxlength="4000" required placeholder="Describe the sample image to generate"></textarea></label><label>Output quality<select name="quality"><option value="LOW">Low</option><option value="MEDIUM" selected>Medium</option><option value="HIGH">High</option></select></label><label>Optional input images (maximum 2)<input name="images" type="file" accept="image/png,image/jpeg,image/webp" multiple></label><div class="cost-notice">This sends a real generation request and may incur provider charges.</div><div id="model-test-preview"></div><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="model-test-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Generate test image</button></div><p class="form-status"></p></form></dialog>`; }
function datasetsView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary cost-dataset-list"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Reusable benchmark assets</p><h2>Benchmark Dataset</h2><p>Review, generate, and remove the person and product images used across model comparisons. Every asset has Low, Medium and High quality variants.</p></div><div class="cost-list-toolbar__actions"><button id="open-upload-dialog" class="button button--quiet" type="button">+ Upload image</button><button id="open-generation-dialog" class="button button--primary" type="button">Generate images</button></div></div><div id="asset-summary">Loading…</div><label class="cost-dataset-quality-filter">View dataset quality<select id="dataset-quality-filter"><option value="LOW">Low</option><option value="MEDIUM" selected>Medium</option><option value="HIGH">High</option></select></label><div id="asset-gallery" class="cost-gallery"></div></section><section class="admin-data-panel cost-management-list cost-dataset-history"><div class="cost-panel-heading"><p class="eyebrow">Generation activity</p><h2>Dataset Generation History</h2><p>Track category, prompt, quality, progress and cost for each generation.</p></div><div id="dataset-generation-status">Loading…</div></section><dialog id="dataset-generation-dialog" class="cost-dialog"><form id="dataset-generation-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Controlled generation</p><h2>Generate dataset images</h2></div><button class="cost-dialog__close" data-close-dialog="dataset-generation-dialog" type="button" aria-label="Close generate dataset dialog">×</button></div><p class="field-help">Select one image category, enter the exact number of images, and optionally provide a custom prompt. Each output contains one standalone product for benchmark use.</p><label>Generation model<select name="model_id" required></select></label><label>Category<select name="category" required><option value="PERSON">Person</option><option value="JEWELLERY">Jewellery</option><option value="SAREE">Sarees</option><option value="DRESS">Dresses</option></select></label><label id="dataset-count-field">Number of images<input name="count" type="number" min="1" max="100" value="1" required><small>The generation creates exactly this many separate images, with one product per image. Maximum 100.</small></label><label>Generation quality<select name="generation_quality" required><option value="LOW">Low</option><option value="MEDIUM" selected>Medium</option><option value="HIGH">High</option></select><small>The model's configured quality mapping is used for generation.</small></label><label>Custom prompt<textarea name="prompt" rows="4" maxlength="4000" placeholder="Example: Create 2 jeans and 3 men's T-shirts as separate product images."></textarea><small>Optional. Quantities apply across the batch; each generated image contains only one product.</small></label><label>Additional direction<textarea name="direction" rows="3" maxlength="4000" placeholder="Example: Use warm studio lighting and no text or logos."></textarea><small>Optional. Appended to every image prompt in this generation.</small></label><div id="dataset-generation-notice" class="cost-notice"><strong>1 person</strong><br>Low, Medium and High local variants are retained.</div><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="dataset-generation-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Generate images now</button></div><p class="form-status"></p></form></dialog><dialog id="asset-upload-dialog" class="cost-dialog"><form id="asset-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Dataset asset</p><h2>Upload an additional image</h2></div><button class="cost-dialog__close" data-close-dialog="asset-upload-dialog" type="button" aria-label="Close upload image dialog">×</button></div><label>Category<select name="kind"><option>PERSON</option><option>JEWELLERY</option><option>BLOUSE</option><option>SAREE</option><option>DRESS</option></select></label><label>Name<input name="name" required></label><label>Image<input name="file" type="file" accept="image/png,image/jpeg,image/webp" required></label><label class="admin-confirm"><input name="authorized" type="checkbox" value="true" required> I confirm this image is authorized for model testing.</label><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="asset-upload-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Upload and create variants</button></div><p class="form-status"></p></form></dialog>`; }
function benchmarksView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary cost-benchmark-list"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Model cost evaluation</p><h2>Benchmark Runs</h2><p>Review benchmark progress with separately controlled product category and input/output quality.</p></div><button id="open-benchmark-dialog" class="button button--primary" type="button">+ Run benchmark</button></div><div id="run-list">Loading…</div></section><dialog id="benchmark-dialog" class="cost-dialog"><form id="benchmark-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Automated evaluation</p><h2>Run benchmark</h2></div><button class="cost-dialog__close" data-close-dialog="benchmark-dialog" type="button" aria-label="Close run benchmark dialog">×</button></div><p class="field-help">Select the product category, person, source/output quality, and how many sample images to generate.</p><label>Model<select name="model_id" required></select></label><label>Person image<select name="person_asset_id"><option value="">Automatic (default)</option></select><small>Select a specific person for every try-on, or leave automatic to use the dataset default selection.</small></label><div id="benchmark-person-preview"></div><label>Benchmark product<select name="category" required><option value="SAREE">Saree</option><option value="JEWELLERY">Jewellery</option><option value="DRESS">Dress</option></select><small>Every selected product is paired with the selected or default person image.</small></label><label>Number of images<input name="image_count" type="number" min="1" max="100" step="1" value="10" required><small>Choose between 1 and 100 generated try-on images.</small></label><label>Input image quality<select name="input_quality" required><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH" selected>High</option></select><small>Controls the person and product dataset variants sent to the model.</small></label><label>Output image quality<select name="output_quality" required><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH" selected>High</option></select><small>Controls the model/provider generation quality mapping.</small></label><div class="cost-notice"><strong><span id="benchmark-image-count">10</span> total try-ons</strong><br>Each try-on uses one person image and one product from the selected category.</div><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="benchmark-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Run benchmark now</button></div><p class="form-status"></p></form></dialog>`; }
function resultsView(compare = false) { return `<section class="admin-data-panel cost-management-list cost-management-list--primary cost-results-panel"><div class="cost-panel-heading"><p class="eyebrow">${compare ? "Side-by-side analysis" : "Benchmark reporting"}</p><h2>${compare ? "Model Cost Comparison" : "Benchmark Results"}</h2><p>${compare ? "Compare model cost and performance using the same reusable dataset and quality profiles." : "Review successful try-ons, provider-reported token usage, cost and latency by model and quality."}</p></div><form id="result-filter" class="cost-result-filters"><label>Model<select name="model_id"><option value="">All models</option></select></label><label>Quality<select name="quality"><option value="">All qualities</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select></label><label>Currency<select name="currency"><option>USD</option><option>INR</option></select></label><button class="button button--primary">Apply filters</button><button id="refresh-fx" class="button button--quiet" type="button">Refresh USD/INR</button></form><p id="fx-note" class="field-help cost-fx-note"></p><div id="result-summary" class="admin-platform-metrics cost-result-summary"><article class="admin-metric-card"><div><span>Result groups</span><span class="metric-icon">◇</span></div><strong>—</strong><small>Model and quality combinations</small></article><article class="admin-metric-card"><div><span>Successful try-ons</span><span class="metric-icon">✓</span></div><strong>—</strong><small>Completed generations</small></article><article class="admin-metric-card"><div><span>Success rate</span><span class="metric-icon">◎</span></div><strong>—</strong><small>Across filtered try-ons</small></article><article class="admin-metric-card"><div><span>Total cost</span><span class="metric-icon">$</span></div><strong>—</strong><small>Filtered generation spend</small></article></div><div id="results-list">Loading…</div>${compare ? '<div class="cost-notice cost-comparison-note">Comparisons use the stored dataset fingerprint, prompt version and quality snapshot. Lowest cost does not indicate output quality.</div>' : ""}</section>`; }
function compareView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary cost-results-panel cost-compare-panel"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Model-level cost analysis</p><h2>Model Cost Comparison</h2><p>Compare try-on volume, provider-reported image tokens and average generation cost across configured models.</p></div><form id="compare-currency" class="cost-compare-controls"><label>Currency<select name="currency"><option>USD</option><option>INR</option></select></label><button id="refresh-fx" class="button button--quiet" type="button">Refresh rate</button></form></div><p id="fx-note" class="field-help cost-fx-note"></p><div id="compare-list">Loading…</div><div class="cost-notice cost-comparison-note">Values combine Low, Medium and High benchmark results. Cost comparison does not measure visual output quality.</div></section>`; }
function finalChecksView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Production readiness review</p><h2>Final model checks</h2><p>Generate the fixed 12-image suite, score every output, review the quality summaries and let an administrator decide whether to promote.</p></div><button id="open-final-dialog" class="button button--primary">+ Start final check</button></div><div id="final-check-list">Loading…</div><p id="final-check-status" class="form-status"></p></section><dialog id="final-check-dialog" class="cost-dialog"><form id="final-check-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Final evaluation</p><h2>Start final check</h2></div><button class="cost-dialog__close" type="button" data-final-close>×</button></div><label>Candidate model<select name="model_id" required></select></label><label>Person image<select name="person_asset_id" required></select></label><div class="cost-notice">12 outputs: jewellery ×2, saree ×1 and dress ×1 at each Low, Medium and High quality.</div><div class="cost-dialog__actions"><button class="button button--quiet" type="button" data-final-close>Cancel</button><button class="button button--primary">Generate final suite</button></div><p class="form-status"></p></form></dialog><dialog id="final-source-dialog" class="cost-dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Source product</p><h2 id="final-source-title">Reference image</h2></div><button class="cost-dialog__close" type="button" data-source-close>×</button></div><img id="final-source-image" class="cost-detail-preview" alt="Source product reference"><button class="button button--quiet" type="button" data-source-close>Close</button></dialog><section id="final-check-detail"></section>`; }
function promotedModelsView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary"><div class="cost-panel-heading"><p class="eyebrow">Production registry</p><h2>Promoted models</h2><p>Review production providers, approved qualities, promotion-time pricing and routing priority. Priority 1 is first and priority 20 is last.</p></div><p id="production-model-status" class="form-status form-status--error" role="alert"></p><div id="production-model-list">Loading…</div></section>`; }

async function attachFinalChecks(root) {
  const [models, assets] = await Promise.all([api("/models"), api("/assets")]);
  const dialog = root.querySelector("#final-check-dialog"), form = root.querySelector("#final-check-form");
  const modelSelect = form.querySelector('select[name="model_id"]');
  const personSelect = form.querySelector('select[name="person_asset_id"]');
  modelSelect.innerHTML = models.models.filter(m => m.enabled).map(m => `<option value="${m.model_id}">${escapeHtml(m.provider_name)} · ${escapeHtml(m.name)}</option>`).join("");
  personSelect.innerHTML = assets.assets.filter(a => a.kind === "PERSON").map(a => `<option value="${a.asset_id}">${escapeHtml(a.name)}</option>`).join("");
  const complexityOptions = kind => {
    const levels = ["SIMPLE", "MEDIUM", "COMPLEX"];
    const counts = Object.fromEntries(levels.map(level => [level, assets.assets.filter(asset => asset.kind === kind && asset.complexity === level).length]));
    const selected = counts.MEDIUM ? "MEDIUM" : levels.find(level => counts[level]) || "MEDIUM";
    return levels.map(level => `<option value="${level}" ${level === selected ? "selected" : ""} ${counts[level] ? "" : "disabled"}>${level[0]}${level.slice(1).toLowerCase()} (${counts[level]} available)</option>`).join("");
  };
  const complexitySection = document.createElement("fieldset");
  complexitySection.className = "cost-final-complexities";
  complexitySection.innerHTML = `<legend>Choose item complexity</legend><p>Select the dataset complexity to use for each item worn by the person. Unavailable choices are disabled.</p>${[["jewellery_complexity","Jewellery","JEWELLERY"],["saree_complexity","Saree","SAREE"],["dress_complexity","Dress","DRESS"]].map(([name,label,kind]) => `<label>${label}<select name="${name}" required>${complexityOptions(kind)}</select></label>`).join("")}`;
  personSelect.closest("label").insertAdjacentElement("afterend", complexitySection);
  root.querySelector("#open-final-dialog").onclick = () => dialog.showModal();
  root.querySelectorAll("[data-final-close]").forEach(b => b.onclick = () => dialog.close());
  const sourceDialog = root.querySelector("#final-source-dialog");
  root.querySelectorAll("[data-source-close]").forEach(b => b.onclick = () => sourceDialog.close());
  const showDetail = async id => {
    const data = await api(`/final-checks/${id}`), complete = data.outputs.length === 12 && data.outputs.every(o => o.score);
    const score = data.outputs.filter(o => o.score).reduce((sum,o) => sum + Number(o.score), 0) / Math.max(1, data.outputs.filter(o => o.score).length) * 10;
    const qualitySummary = ["LOW","MEDIUM","HIGH"].map(q => { const qualityScore = Number(data.quality_scores[q] || 0), price = data.quality_prices_usd[q]; return `<article class="admin-metric-card"><div><span>${q}</span><span class="metric-icon">◇</span></div><strong>${qualityScore.toFixed(1)}%</strong><small>${price == null ? "Price not configured" : `${money(price)} per image`}</small></article>`; }).join("");
    const reviewFilters = `<div class="cost-review-filters"><div><strong>Filter review results</strong><span id="cost-review-filter-count">${data.outputs.length} of ${data.outputs.length} shown</span></div><fieldset><legend>Quality</legend>${["LOW","MEDIUM","HIGH"].map(q => `<label><input type="checkbox" data-review-filter="quality" value="${q}" checked><span>${q}</span></label>`).join("")}</fieldset><fieldset><legend>Try-on category</legend>${["JEWELLERY","SAREE","DRESS"].map(category => `<label><input type="checkbox" data-review-filter="category" value="${category}" checked><span>${category === "JEWELLERY" ? "Jewellery" : category === "SAREE" ? "Saree" : "Dress"}</span></label>`).join("")}</fieldset></div>`;
    root.querySelector("#final-check-detail").innerHTML = `<section class="admin-data-panel"><div class="cost-panel-heading"><p class="eyebrow">${escapeHtml(data.check.status)}</p><h2>${escapeHtml(data.check.provider_name)} · ${escapeHtml(data.check.model_name)}</h2></div><div class="cost-notice"><strong>Generation ${data.progress.completed}/12</strong><br><progress value="${data.progress.completed}" max="12"></progress><br><strong>Scores ${data.progress.reviewed}/12</strong><br><progress value="${data.progress.reviewed}" max="12"></progress>${data.progress.reviewed ? `<br>Overall score: ${score.toFixed(1)}/100` : ""}</div>${complete ? `<div class="admin-platform-metrics cost-result-summary">${qualitySummary}</div>` : ""}${reviewFilters}<form id="final-review-form"><div class="cost-result-gallery">${data.outputs.map(o => `<article class="cost-result-card" data-review-quality="${o.quality}" data-review-category="${o.category}"><div class="cost-result-card__image">${o.image_url ? `<img src="${o.image_url}" alt="${escapeHtml(o.category)} ${escapeHtml(o.quality)} output">` : "Generation pending"}</div><strong>${escapeHtml(o.category)} · ${escapeHtml(o.quality)}</strong><button class="button button--quiet" type="button" data-source-url="${o.source_image_url}" data-source-title="${escapeHtml(o.product_asset_name)}">View source ${escapeHtml(o.category.toLowerCase())}</button><label>Score (1–10)<input type="number" min="1" max="10" name="score-${o.tryon_id}" value="${o.score || ""}" ${o.status !== "SUCCEEDED" ? "disabled" : ""}></label></article>`).join("")}</div><button class="button button--primary" ${data.outputs.some(o => o.status !== "SUCCEEDED") ? "disabled" : ""}>Save all scores</button><p class="form-status"></p></form>${complete && data.check.status === "SCORED" ? `<form id="promote-final-form" class="cost-promotion-panel"><div class="cost-promotion-panel__heading"><div><p class="eyebrow">Production decision</p><h3>Choose approved qualities</h3></div><span>Admin controlled</span></div><p class="cost-promotion-panel__intro">Select one or more quality levels to make available in production.</p><div class="cost-promotion-options">${["LOW","MEDIUM","HIGH"].map(q => { const price = data.quality_prices_usd[q]; return `<label class="cost-promotion-option"><input type="checkbox" name="quality_levels" value="${q}" checked><span class="cost-promotion-option__control" aria-hidden="true"></span><span class="cost-promotion-option__content"><strong>${q}</strong><span>${Number(data.quality_scores[q] || 0).toFixed(1)}% score</span><small>${price == null ? "Price not configured" : `${money(price)} per image`}</small></span></label>`; }).join("")}</div><div class="cost-promotion-panel__footer"><p><strong>Advisory scores only.</strong><br>No automatic pass or fail threshold is applied.</p><button class="button button--primary">Promote selected qualities</button></div><p class="form-status"></p></form>` : ""}</section>`;
    root.querySelectorAll("[data-source-url]").forEach(button => button.onclick = () => { root.querySelector("#final-source-image").src = button.dataset.sourceUrl; root.querySelector("#final-source-title").textContent = button.dataset.sourceTitle; sourceDialog.showModal(); });
    const applyReviewFilters = () => { const selected = type => new Set([...root.querySelectorAll(`[data-review-filter="${type}"]:checked`)].map(input => input.value)); const qualities = selected("quality"), categories = selected("category"); let visible = 0; root.querySelectorAll("[data-review-quality]").forEach(card => { const show = qualities.has(card.dataset.reviewQuality) && categories.has(card.dataset.reviewCategory); card.hidden = !show; if (show) visible += 1; }); root.querySelector("#cost-review-filter-count").textContent = `${visible} of ${data.outputs.length} shown`; };
    root.querySelectorAll("[data-review-filter]").forEach(input => input.onchange = applyReviewFilters);
    const reviewForm = root.querySelector("#final-review-form");
    reviewForm.onsubmit = async event => { event.preventDefault(); const reviews = data.outputs.map(o => ({tryon_id:o.tryon_id, score:Number(reviewForm.elements[`score-${o.tryon_id}`].value)})); if (reviews.some(review => review.score < 1 || review.score > 10)) { reviewForm.querySelector(".form-status").textContent="Score all 12 results from 1 to 10 before saving."; return; } try { await api(`/final-checks/${id}/reviews`, {method:"PUT", body:JSON.stringify({reviews})}); await showDetail(id); await load(); } catch (e) { reviewForm.querySelector(".form-status").textContent=e.message; } };
    const promoteForm = root.querySelector("#promote-final-form"); if (promoteForm) promoteForm.onsubmit = async event => { event.preventDefault(); const quality_levels = new FormData(promoteForm).getAll("quality_levels"); try { await api(`/final-checks/${id}/promote`, {method:"POST", body:JSON.stringify({quality_levels})}); await showDetail(id); await load(); } catch(e) { promoteForm.querySelector(".form-status").textContent=e.message; } };
  };
  const load = async () => { const data = await api("/final-checks"); root.querySelector("#final-check-list").innerHTML = data.checks.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Status</th><th>Generation</th><th>Scores</th><th>Created</th><th>Actions</th></tr></thead><tbody>${data.checks.map(c => `<tr><td>${escapeHtml(c.provider_name)} · ${escapeHtml(c.model_name)}</td><td><span class="admin-status">${escapeHtml(c.status)}</span></td><td><progress value="${c.completed_outputs}" max="12"></progress><br>${c.completed_outputs}/12</td><td><progress value="${c.review_count}" max="12"></progress><br>${c.review_count}/12</td><td>${new Date(c.created_at).toLocaleString()}</td><td><div class="cost-row-actions"><button class="admin-history-button" data-final-id="${c.check_id}">View scores</button><button class="admin-history-button cost-delete-button cost-delete-icon" type="button" data-delete-final-id="${c.check_id}" data-delete-final-status="${escapeHtml(c.status)}" aria-label="Delete final check" title="Delete final check"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></button></div></td></tr>`).join("")}</tbody></table></div>` : '<div class="cost-empty-state"><strong>No final checks yet</strong></div>'; root.querySelectorAll("[data-final-id]").forEach(b => b.onclick=()=>showDetail(b.dataset.finalId)); root.querySelectorAll("[data-delete-final-id]").forEach(button => button.onclick=async()=>{ if (!await wearoConfirm({eyebrow:"Final model check",title:`Delete this ${button.dataset.deleteFinalStatus.toLowerCase()} check?`,message:"The final check, its generated suite and all saved scores will be permanently removed.",note:"Promoted checks are protected because they are part of production history. This action cannot be undone.",confirmLabel:"Delete final check",cancelLabel:"Keep check",tone:"danger"})) return; button.disabled=true; try { await api(`/final-checks/${button.dataset.deleteFinalId}`,{method:"DELETE"}); root.querySelector("#final-check-detail").innerHTML=""; await load(); } catch(e) { button.disabled=false; root.querySelector("#final-check-status").textContent=e.message; } }); };
  form.onsubmit = async event => { event.preventDefault(); const values=Object.fromEntries(new FormData(form)); try { const result=await api("/final-checks", {method:"POST", body:JSON.stringify(values)}); dialog.close(); await load(); await showDetail(result.check_id); } catch(e) { form.querySelector(".form-status").textContent=e.message; } };
  await load();
  setInterval(() => route(location.pathname) === "final-checks" && load(), 5000);
}
async function attachPromotedModels(root) {
  const pricingDetails = release => { const items = release.pricing_snapshot || []; return items.length ? items.map(item => { const unit = item.unit === "output_images" ? `${item.quality || "Any"} image` : `${String(item.unit).replaceAll("_", " ")} / 1M`; return `${escapeHtml(unit)}: ${money(item.price_usd)}`; }).join("<br>") : "No pricing snapshot"; };
  const load = async () => {
    const production = await api("/production-models"), active = production.active_models || [];
    root.querySelector("#production-model-list").innerHTML = production.history.length ? `<form id="production-priority-form"><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Priority</th><th>Status</th><th>Provider</th><th>Model</th><th>Approved qualities</th><th>Price details</th><th>Promoted</th><th>Actions</th></tr></thead><tbody>${production.history.map(r => `<tr><td>${r.retired_at ? "—" : `<select name="priority-${r.release_id}" aria-label="Priority for ${escapeHtml(r.model_name)}">${Array.from({length:20}, (_, index) => `<option value="${index + 1}" ${r.priority === index + 1 ? "selected" : ""}>${index + 1}</option>`).join("")}</select>`}</td><td><span class="admin-status">${r.retired_at ? "RETIRED" : "ACTIVE PROD"}</span></td><td><strong>${escapeHtml(r.provider_name)}</strong><br><small>${escapeHtml(r.provider_type)}</small></td><td><strong>${escapeHtml(r.model_name)}</strong><br><code>${escapeHtml(r.api_identifier)}</code>${r.model_version ? `<br><small>Version ${escapeHtml(r.model_version)}</small>` : ""}</td><td>${(r.approved_quality_levels || []).map(q => `<span class="admin-status cost-quality-badge">${escapeHtml(q)}</span>`).join(" ")}</td><td>${pricingDetails(r)}${r.pricing_effective_at ? `<br><small>Effective ${new Date(r.pricing_effective_at).toLocaleString()}</small>` : ""}</td><td>${new Date(r.promoted_at).toLocaleString()}<br><small>by ${escapeHtml(r.promoted_by)}</small>${r.retired_at ? `<br><small>Retired ${new Date(r.retired_at).toLocaleString()}</small>` : ""}</td><td><button class="admin-history-button cost-delete-button cost-icon-action" type="button" data-delete-production-model="${r.release_id}" data-production-model-name="${escapeHtml(r.model_name)}" aria-label="Delete promoted model" title="Delete promoted model">${DELETE_ICON}</button></td></tr>`).join("")}</tbody></table></div>${active.length ? '<div class="cost-priority-actions"><p>Assign each active model a unique priority from 1 (first) to 20 (last).</p><button class="button button--primary">Save priorities</button><span class="form-status"></span></div>' : ""}</form>` : '<div class="cost-empty-state"><strong>No promoted models yet</strong><p>Models appear here after a final check is scored and promoted.</p></div>';
    root.querySelectorAll("[data-delete-production-model]").forEach(button => button.onclick = async () => {
      if (!await wearoConfirm({eyebrow:"Promoted model",title:`Delete ${button.dataset.productionModelName} from production?`,message:"This production release and its priority will be removed.",note:"The completed final check and its scores will be retained, so the model can be promoted again later.",confirmLabel:"Delete promoted model",cancelLabel:"Keep model",tone:"danger"})) return;
      button.disabled = true;
      try { await api(`/production-models/${button.dataset.deleteProductionModel}`, {method:"DELETE"}); await load(); }
      catch(e) { button.disabled = false; root.querySelector("#production-model-status").textContent = e.message; }
    });
    const form = root.querySelector("#production-priority-form"); if (!form || !active.length) return;
    form.onsubmit = async event => { event.preventDefault(); const priorities = active.map(r => ({release_id:r.release_id, priority:Number(form.elements[`priority-${r.release_id}`].value)})); const values = priorities.map(item => item.priority); if (new Set(values).size !== values.length) { form.querySelector(".form-status").textContent = "Each active model needs a unique priority."; return; } try { await api("/production-models/priorities", {method:"PUT", body:JSON.stringify({priorities})}); await load(); } catch(e) { form.querySelector(".form-status").textContent=e.message; } };
  };
  await load();
}
function modelComparisonsView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Same-input model test</p><h2>Compare Models</h2><p>Run one person and product pair through every enabled model.</p></div><button id="open-comparison" class="button button--primary" type="button">+ New comparison</button></div><div id="comparison-list">Loading…</div><div id="comparison-detail"></div></section><dialog id="comparison-dialog" class="cost-dialog"><form id="comparison-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><h2>Compare all models</h2><button class="cost-dialog__close" type="button">×</button></div><label>Product category<select name="category"><option value="JEWELLERY">Jewellery</option><option value="SAREE">Saree</option><option value="DRESS">Dress</option></select></label><label>Output quality<select name="output_quality"><option>LOW</option><option selected>MEDIUM</option><option>HIGH</option></select></label><input name="person_result_tryon_id" type="hidden" required><button id="choose-comparison-person" class="button button--quiet" type="button">Choose person from Results</button><div id="comparison-person"></div><input name="product_asset_id" type="hidden" required><button id="choose-comparison-product" class="button button--quiet" type="button">Choose product image</button><div id="comparison-product"></div><div class="cost-dialog__actions"><button class="button button--primary" type="submit">Run on all models</button></div><p class="form-status"></p></form></dialog>`; }

function knowledgeView() { return `<section class="admin-data-panel cost-management-list cost-management-list--primary cost-knowledge-list"><div class="cost-list-toolbar"><div class="cost-panel-heading"><p class="eyebrow">Reference library</p><h2>Knowledge</h2><p>Add learnings, pricing notes, provider guidance and other reference material for Cost Lab.</p></div><div class="cost-list-toolbar__actions"><button id="open-knowledge-text" class="button button--quiet" type="button">+ Paste text</button><button id="open-knowledge-pdf" class="button button--primary" type="button">Upload PDF</button></div></div><div id="knowledge-list">Loading…</div></section><dialog id="knowledge-text-dialog" class="cost-dialog"><form id="knowledge-text-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">Text knowledge</p><h2>Add pasted text</h2></div><button class="cost-dialog__close" data-close-dialog="knowledge-text-dialog" type="button" aria-label="Close text knowledge dialog">×</button></div><label>Title<input name="title" required maxlength="240" placeholder="Example: OpenAI image pricing notes"></label><label>Knowledge or learning<textarea name="content" rows="12" required maxlength="1000000" placeholder="Paste the reference text here…"></textarea></label><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="knowledge-text-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Save knowledge</button></div><p class="form-status"></p></form></dialog><dialog id="knowledge-pdf-dialog" class="cost-dialog"><form id="knowledge-pdf-form" class="cost-management-form" method="dialog"><div class="cost-dialog__header"><div><p class="eyebrow">PDF knowledge</p><h2>Upload PDF</h2></div><button class="cost-dialog__close" data-close-dialog="knowledge-pdf-dialog" type="button" aria-label="Close PDF knowledge dialog">×</button></div><label>Title<input name="title" required maxlength="240" placeholder="Example: Provider pricing guide"></label><label>PDF file<input name="file" type="file" accept="application/pdf,.pdf" required><small>PDF only, up to 25 MB.</small></label><div class="cost-dialog__actions"><button class="button button--quiet" data-close-dialog="knowledge-pdf-dialog" type="button">Cancel</button><button class="button button--primary" type="submit">Upload PDF</button></div><p class="form-status"></p></form></dialog>`; }

async function attachOverview(root) {
  const data = await api("/overview");
  root.querySelector("#cost-overview-totals").innerHTML = `<article class="admin-metric-card"><div><span>Providers</span><span class="metric-icon">◇</span></div><strong>${data.provider_count}</strong><small>Configured model providers</small></article><article class="admin-metric-card"><div><span>Models</span><span class="metric-icon">✦</span></div><strong>${data.model_count}</strong><small>Models available for testing</small></article><article class="admin-metric-card"><div><span>Quality profiles</span><span class="metric-icon">◈</span></div><strong>3</strong><small>Low, Medium and High</small></article><article class="admin-metric-card"><div><span>Try-ons per benchmark</span><span class="metric-icon">◎</span></div><strong>30</strong><small>Ten per quality profile</small></article>`;
  root.querySelector("#cost-overview-models").innerHTML = data.providers.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Provider</th><th>Provider status</th><th>Models</th><th>Model</th><th>Benchmarks</th><th>Average successful try-on</th></tr></thead><tbody>${data.providers.map(provider => { const models = data.models.filter(model => model.provider_name === provider.name); return models.length ? models.map((model, index) => `<tr><td>${index === 0 ? escapeHtml(provider.name) : ""}</td><td>${index === 0 ? `<span class="admin-status">${provider.enabled ? "Enabled" : "Disabled"}</span>` : ""}</td><td>${index === 0 ? provider.model_count : ""}</td><td>${escapeHtml(model.model_name)}</td><td>${model.benchmark_runs}</td><td>${model.average_tryon_cost_usd == null ? "No benchmark data" : money(model.average_tryon_cost_usd)}</td></tr>`).join("") : `<tr><td>${escapeHtml(provider.name)}</td><td><span class="admin-status">${provider.enabled ? "Enabled" : "Disabled"}</span></td><td>0</td><td>No models</td><td>0</td><td>No benchmark data</td></tr>`; }).join("")}</tbody></table></div>` : "No providers configured.";
  const qualityFor = (modelId, quality) => data.qualities.find(item => item.model_id === modelId && item.quality === quality);
  root.querySelector("#cost-overview-qualities").innerHTML = data.models.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Low</th><th>Medium</th><th>High</th></tr></thead><tbody>${data.models.map(model => `<tr><td>${escapeHtml(model.provider_name)} · ${escapeHtml(model.model_name)}</td>${["LOW","MEDIUM","HIGH"].map(quality => { const metric = qualityFor(model.model_id, quality); return `<td><strong>${metric?.benchmark_runs || 0}</strong> runs<br><small>${metric?.successful_tryons || 0}/${metric?.total_tryons || 0} successful</small></td>`; }).join("")}</tr>`).join("")}</tbody></table></div>` : "No models configured.";
}

async function attachProviders(root) {
  const dialog = root.querySelector("#provider-dialog");
  const form = root.querySelector("#provider-form");
  const openAdd = () => {
    form.reset();
    delete form.dataset.editId;
    form.querySelector("h2").textContent = "Add provider";
    form.querySelector("button[type=submit]").textContent = "Save provider";
    form.querySelector("input[name=api_base_url]").value = "https://api.openai.com/v1";
    form.querySelector(".form-status").textContent = "";
    dialog.showModal();
  };
  root.querySelector("#open-provider-dialog").onclick = openAdd;
  root.querySelector("#close-provider-dialog").onclick = () => dialog.close();
  root.querySelector("#cancel-provider-dialog").onclick = () => dialog.close();
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
  const load = async () => {
    const data = await api("/providers");
    root.querySelector("#provider-list").innerHTML = data.providers.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Name</th><th>Adapter</th><th>Secret</th><th>Pricing reference</th><th>Status</th><th>Actions</th></tr></thead><tbody>${data.providers.map(p => `<tr><td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.provider_type)}</td><td>${p.has_stored_secret ? "Encrypted" : escapeHtml(p.secret_reference)}</td><td>${p.pricing_reference_url ? `<a href="${escapeHtml(p.pricing_reference_url)}" target="_blank" rel="noreferrer">View pricing</a>` : "—"}${p.pricing_reference_text ? `<br><small>${escapeHtml(p.pricing_reference_text)}</small>` : ""}</td><td>${p.enabled ? "Enabled" : "Disabled"}</td><td><div class="cost-row-actions"><button class="admin-history-button" data-edit-provider="${p.provider_id}">Edit</button><button class="admin-history-button" data-validate="${p.provider_id}">Validate</button></div></td></tr>`).join("")}</tbody></table></div>` : "No providers configured.";
    root.querySelectorAll("[data-edit-provider]").forEach(button => button.onclick = () => {
      const provider = data.providers.find(item => item.provider_id === button.dataset.editProvider);
      if (!provider) return;
      form.reset();
      form.dataset.editId = provider.provider_id;
      form.querySelector("h2").textContent = "Edit provider";
      form.querySelector("button[type=submit]").textContent = "Update provider";
      form.elements.name.value = provider.name;
      form.elements.provider_type.value = provider.provider_type;
      form.elements.api_base_url.value = provider.api_base_url || "";
      form.elements.secret_reference.value = provider.secret_reference || "";
      form.elements.pricing_reference_url.value = provider.pricing_reference_url || "";
      form.elements.pricing_reference_text.value = provider.pricing_reference_text || "";
      form.elements.api_key.placeholder = provider.has_stored_secret ? "Leave blank to keep encrypted key" : "Stored encrypted";
      form.querySelector(".form-status").textContent = "";
      dialog.showModal();
    });
    root.querySelectorAll("[data-validate]").forEach(button => button.onclick = async () => { button.textContent = "Checking…"; try { const result = await api(`/providers/${button.dataset.validate}/validate`, { method: "POST" }); button.textContent = result.valid ? "Connected" : result.message; } catch(e) { button.textContent = e.message; } });
  };
  form.onsubmit = async event => { event.preventDefault(); const values = Object.fromEntries(new FormData(form)), editId = form.dataset.editId; try { await api(editId ? `/providers/${editId}` : "/providers", { method:editId ? "PUT" : "POST", body:JSON.stringify({ ...values, api_key: values.api_key || null, secret_reference: values.secret_reference || null, api_base_url: values.api_base_url || null, pricing_reference_url: values.pricing_reference_url || null, pricing_reference_text: values.pricing_reference_text || null, enabled:true }) }); form.reset(); dialog.close(); await load(); } catch(e){ form.querySelector(".form-status").textContent=e.message; } }; await load();
}
async function attachModels(root) {
  const providers = await api("/providers");
  const modelDialog = root.querySelector("#model-dialog");
  const testDialog = root.querySelector("#model-test-dialog");
  const form = root.querySelector("#model-form");
  const testForm = root.querySelector("#model-test-form");
  const imageDialog = document.createElement("dialog");
  imageDialog.className = "cost-dialog cost-image-preview-dialog";
  imageDialog.innerHTML = `<div class="cost-dialog__header"><div><p class="eyebrow">Test asset</p><h2>Image preview</h2></div><button class="cost-dialog__close" type="button" aria-label="Close image preview">×</button></div><img class="cost-image-preview-dialog__image" alt="Model test image preview"><label>Image URL<input class="cost-image-preview-dialog__url" readonly></label><div class="cost-dialog__actions"><button class="button button--quiet" type="button" data-copy-image-url>Copy URL</button><a class="button button--primary" target="_blank" rel="noopener noreferrer">Open original</a></div>`;
  root.append(imageDialog);
  imageDialog.querySelector(".cost-dialog__close").onclick = () => imageDialog.close();
  imageDialog.addEventListener("click", event => { if (event.target === imageDialog) imageDialog.close(); });
  const wireTestImagePreviews = () => root.querySelectorAll("[data-test-preview-url]").forEach(image => image.onclick = () => {
    const url = new URL(image.dataset.testPreviewUrl, location.origin).href;
    imageDialog.querySelector("img").src = url;
    imageDialog.querySelector("input").value = url;
    imageDialog.querySelector("a").href = url;
    imageDialog.querySelector("[data-copy-image-url]").textContent = "Copy URL";
    imageDialog.showModal();
  });
  imageDialog.querySelector("[data-copy-image-url]").onclick = async event => {
    await navigator.clipboard.writeText(imageDialog.querySelector("input").value);
    event.currentTarget.textContent = "Copied";
  };
  root.querySelector("#open-model-dialog").onclick = () => { form.reset(); delete form.dataset.editId; form.querySelector("h2").textContent="Add model and pricing"; form.querySelector("button[type=submit]").textContent="Save model and pricing"; modelDialog.showModal(); };
  root.querySelectorAll("[data-close-dialog]").forEach(button => button.onclick = () => root.querySelector(`#${button.dataset.closeDialog}`).close());
  modelDialog.addEventListener("click", event => { if (event.target === modelDialog) modelDialog.close(); });
  root.querySelector("#model-form select").innerHTML = providers.providers.map(p=>`<option value="${p.provider_id}">${escapeHtml(p.name)}</option>`).join("");
  const update = async () => {
    const data = await api("/models");
    root.querySelector("#model-list").innerHTML = data.models.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Provider</th><th>Model</th><th>Identifier</th><th>Pricing</th><th>Test status</th><th>Actions</th></tr></thead><tbody>${data.models.map(model => {
      const components = model.pricing?.[0]?.components || [];
      const price = (unit, quality) => components.find(item => item.unit === unit && (!quality || item.quality === quality))?.price_usd;
      const pricing = [];
      if (price("image_input_tokens") != null) pricing.push(`Input: ${money(price("image_input_tokens"))} / 1M tokens`);
      if (price("image_output_tokens") != null) pricing.push(`Output: ${money(price("image_output_tokens"))} / 1M tokens`);
      ["LOW", "MEDIUM", "HIGH"].forEach(quality => {
        if (price("output_images", quality) != null) pricing.push(`${quality}: ${money(price("output_images", quality))} / image`);
      });
      const testStatus = model.tested_at ? `<span class="admin-status">Tested · ${escapeHtml(model.tested_method === "GENERATED" ? "Generated" : "Manual")}</span><br><small>${new Date(model.tested_at).toLocaleString()}</small>${model.test_output_path ? `<br><a href="${API}/models/${model.model_id}/test-image" target="_blank">View sample</a>` : ""}` : `<span class="admin-status">Not tested</span>`;
      return `<tr><td>${escapeHtml(model.provider_name)}</td><td>${escapeHtml(model.name)}</td><td><code>${escapeHtml(model.api_identifier)}</code></td><td>${pricing.length ? pricing.join("<br>") : "—"}</td><td>${testStatus}</td><td><div class="cost-row-actions"><button class="admin-history-button" data-test-model="${model.model_id}">Test model</button><button class="admin-history-button" data-toggle-tested="${model.model_id}" data-tested="${model.tested_at ? "true" : "false"}">${model.tested_at ? "Mark untested" : "Mark tested"}</button><button class="admin-history-button" data-edit-model="${model.model_id}">Edit</button></div></td></tr>`;
    }).join("")}</tbody></table></div>` : "No models configured.";
    root.querySelectorAll("[data-edit-model]").forEach(button => button.onclick = () => {
      const model = data.models.find(item => item.model_id === button.dataset.editModel);
      if (!model) return;
      const components = model.pricing?.[0]?.components || [];
      const price = (unit, quality) => components.find(item => item.unit === unit && (!quality || item.quality === quality))?.price_usd;
      form.reset();
      form.dataset.editId = model.model_id;
      form.querySelector("h2").textContent = "Edit model and pricing";
      form.querySelector("button[type=submit]").textContent = "Update model and pricing";
      form.elements.provider_id.value = model.provider_id;
      form.elements.name.value = model.name;
      form.elements.api_identifier.value = model.api_identifier;
      form.elements.version.value = model.version || "";
      form.elements.image_input_price_usd_per_million.value = price("image_input_tokens") ?? "";
      form.elements.image_output_price_usd_per_million.value = price("image_output_tokens") ?? "";
      form.elements.output_image_price_usd_low.value = price("output_images", "LOW") ?? "";
      form.elements.output_image_price_usd_medium.value = price("output_images", "MEDIUM") ?? "";
      form.elements.output_image_price_usd_high.value = price("output_images", "HIGH") ?? "";
      form.querySelector(".form-status").textContent = "";
      modelDialog.showModal();
    });
    root.querySelectorAll("[data-test-model]").forEach(button => button.onclick = () => {
      const model = data.models.find(item => item.model_id === button.dataset.testModel);
      if (!model) return;
      testForm.reset();
      testForm.dataset.modelId = model.model_id;
      root.querySelector("#model-test-name").textContent = `${model.provider_name} · ${model.name}`;
      testForm.elements.prompt.value = model.test_prompt || "";
      const existingInputs = (model.test_input_paths || []).map((_, index) => { const url = `${API}/models/${model.model_id}/test-input/${index}`; return `<img class="cost-result-card__image cost-clickable-image" src="${url}" data-test-preview-url="${url}" alt="Stored test input ${index + 1}">`; }).join("");
      const outputUrl = `${API}/models/${model.model_id}/test-image`;
      root.querySelector("#model-test-preview").innerHTML = model.test_output_path ? `<div class="cost-dialog__section"><strong>Previous successful test</strong><small>Prompt: ${escapeHtml(model.test_prompt || "No prompt stored")}</small></div>${existingInputs ? `<div class="cost-dialog__section"><strong>Input images</strong></div><div class="cost-result-gallery">${existingInputs}</div>` : ""}<div class="cost-dialog__section"><strong>Generated output</strong></div><img class="cost-result-card__image cost-clickable-image" src="${outputUrl}" data-test-preview-url="${outputUrl}" alt="Stored generated test output">` : "";
      wireTestImagePreviews();
      testForm.querySelector(".form-status").textContent = "";
      testDialog.showModal();
    });
    root.querySelectorAll("[data-toggle-tested]").forEach(button => button.onclick = async () => {
      const tested = button.dataset.tested !== "true";
      button.disabled = true;
      try {
        await api(`/models/${button.dataset.toggleTested}/test-status`, { method: "PUT", body: JSON.stringify({ tested }) });
        await update();
      } catch (error) {
        button.disabled = false;
        button.textContent = error.message;
      }
    });
  };
  form.onsubmit = async event => {
    event.preventDefault();
    const currentForm = event.currentTarget;
    const values = Object.fromEntries(new FormData(currentForm));
    const editId = currentForm.dataset.editId;
    const optionalPrices = ["image_input_price_usd_per_million", "image_output_price_usd_per_million", "output_image_price_usd_low", "output_image_price_usd_medium", "output_image_price_usd_high"];
    optionalPrices.forEach(key => { values[key] = values[key] === "" ? null : values[key]; });
    try {
      await api(editId ? `/models-with-pricing/${editId}` : "/models-with-pricing", { method: editId ? "PUT" : "POST", body: JSON.stringify({ ...values, version: values.version || null, input_formats: ["png", "jpeg"], output_formats: ["png"], quality_levels: ["LOW", "MEDIUM", "HIGH"], enabled: true }) });
      currentForm.reset(); modelDialog.close(); await update();
    } catch (error) { currentForm.querySelector(".form-status").textContent = error.message; }
  };
  testForm.onsubmit = async event => {
    event.preventDefault();
    const files = testForm.elements.images.files;
    const status = testForm.querySelector(".form-status");
    if (files.length > 2) { status.textContent = "Select no more than two input images."; return; }
    const submit = testForm.querySelector("button[type=submit]");
    submit.disabled = true;
    submit.textContent = "Generating…";
    try {
      const payload = new FormData(testForm);
      if (!files.length) payload.delete("images");
      const result = await api(`/models/${testForm.dataset.modelId}/test`, { method: "POST", body: payload });
      const inputImages = (result.input_urls || []).map((url, index) => `<img class="cost-result-card__image cost-clickable-image" src="${url}?v=${Date.now()}" data-test-preview-url="${url}" alt="Test input ${index + 1}">`).join("");
      root.querySelector("#model-test-preview").innerHTML = `<div class="cost-dialog__section"><strong>Successful test</strong><small>Prompt: ${escapeHtml(result.prompt)}</small></div>${inputImages ? `<div class="cost-dialog__section"><strong>Input images</strong></div><div class="cost-result-gallery">${inputImages}</div>` : ""}<div class="cost-dialog__section"><strong>Generated output</strong></div><img class="cost-result-card__image cost-clickable-image" src="${result.image_url}?v=${Date.now()}" data-test-preview-url="${result.image_url}" alt="Generated model test image"><p class="field-help">Generation succeeded in ${Number(result.latency_ms).toLocaleString()} ms. The model is now marked tested.</p>`;
      wireTestImagePreviews();
      status.textContent = "Model test succeeded.";
      await update();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      submit.disabled = false;
      submit.textContent = "Generate test image";
    }
  };
  await update();
}
async function attachDatasets(root){const models=await api("/models"),generationDialog=root.querySelector("#dataset-generation-dialog"),uploadDialog=root.querySelector("#asset-upload-dialog");root.querySelector("#open-generation-dialog").onclick=()=>generationDialog.showModal();root.querySelector("#open-upload-dialog").onclick=()=>uploadDialog.showModal();root.querySelectorAll("[data-close-dialog]").forEach(button=>button.onclick=()=>root.querySelector(`#${button.dataset.closeDialog}`).close());[generationDialog,uploadDialog].forEach(dialog=>dialog.addEventListener("click",event=>{if(event.target===dialog)dialog.close();}));root.querySelector("#dataset-generation-form select").innerHTML=models.models.filter(m=>m.enabled).map(m=>`<option value="${m.model_id}">${escapeHtml(m.provider_name)} · ${escapeHtml(m.name)}</option>`).join("");const load=async()=>{const [data,generations]=await Promise.all([api("/assets"),api("/dataset-generations")]),counts={};data.assets.forEach(a=>counts[a.kind]=(counts[a.kind]||0)+1);root.querySelector("#asset-summary").innerHTML=`<div class="admin-stat-grid cost-dataset-summary">${[["PERSON","Person"],["JEWELLERY","Jewellery"],["SAREE","Sarees"],["DRESS","Dresses"]].map(([kind,label])=>`<article><span>${label}</span><strong>${counts[kind]||0}<small> / ${kind==="PERSON"?1:10}</small></strong></article>`).join("")}</div>`;root.querySelector("#asset-gallery").innerHTML=data.assets.length?data.assets.map(a=>`<article><img src="${a.url}" alt="${escapeHtml(a.name)}"><strong>${escapeHtml(a.name)}</strong><span>${escapeHtml(a.kind)}</span></article>`).join(""):"<p class=\"field-help\">No dataset images yet. Generate the reusable dataset or upload an image.</p>";root.querySelector("#dataset-generation-status").innerHTML=generations.jobs.length?`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Status</th><th>Progress</th><th>Generation cost</th><th>Started</th></tr></thead><tbody>${generations.jobs.map(j=>`<tr><td>${escapeHtml(j.provider_name)} · ${escapeHtml(j.model_name)}</td><td><span class="admin-status">${j.status}</span></td><td>${j.completed_items+j.failed_items}/${j.total_items}${j.failed_items?` (${j.failed_items} failed)`:""}</td><td>${money(j.total_cost_usd)}</td><td>${new Date(j.created_at).toLocaleString()}</td></tr>`).join("")}</tbody></table></div>`:"<p class=\"field-help\">No dataset generation has been started.</p>";};root.querySelector("#dataset-generation-form").onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,s=f.querySelector(".form-status"),d=new FormData(f);try{await api("/dataset-generations",{method:"POST",body:JSON.stringify({model_id:d.get("model_id")})});f.reset();generationDialog.close();await load();}catch(x){s.textContent=x.message;}};root.querySelector("#asset-form").onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,s=f.querySelector(".form-status");try{await api("/assets",{method:"POST",body:new FormData(f)});f.reset();uploadDialog.close();await load();}catch(x){s.textContent=x.message;}};await load();setInterval(()=>route(location.pathname)==="datasets"&&load(),5000);}

async function attachQualityDatasets(root) {
  const models = await api("/models");
  const generationDialog = root.querySelector("#dataset-generation-dialog");
  const uploadDialog = root.querySelector("#asset-upload-dialog");
  const qualityFilter = root.querySelector("#dataset-quality-filter");

  root.querySelector("#open-generation-dialog").onclick = () => generationDialog.showModal();
  root.querySelector("#open-upload-dialog").onclick = () => uploadDialog.showModal();
  root.querySelectorAll("[data-close-dialog]").forEach(button => {
    button.onclick = () => root.querySelector(`#${button.dataset.closeDialog}`).close();
  });
  [generationDialog, uploadDialog].forEach(dialog => dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  }));
  root.querySelector("#dataset-generation-form select[name=model_id]").innerHTML = models.models
    .filter(model => model.enabled)
    .map(model => `<option value="${model.model_id}">${escapeHtml(model.provider_name)} · ${escapeHtml(model.name)}</option>`)
    .join("");
  const generationForm = root.querySelector("#dataset-generation-form");
  const categorySelect = generationForm.querySelector("select[name=category]");
  categorySelect.closest("label").insertAdjacentHTML("afterend", '<label>Item complexity<select name="complexity"><option value="SIMPLE">Simple</option><option value="MEDIUM" selected>Medium</option><option value="COMPLEX">Complex</option></select><small>Classifies pattern, material and construction detail for benchmark selection.</small></label>');
  const uploadCategory = uploadDialog.querySelector("select[name=kind]");
  uploadCategory.closest("label").insertAdjacentHTML("afterend", '<label>Item complexity<select name="complexity"><option value="SIMPLE">Simple</option><option value="MEDIUM" selected>Medium</option><option value="COMPLEX">Complex</option></select></label>');
  const countInput = generationForm.querySelector("input[name=count]");
  const updateGenerationFields = () => {
    root.querySelector("#dataset-generation-notice").innerHTML = `<strong>${escapeHtml(countInput.value || "0")} ${escapeHtml(categorySelect.options[categorySelect.selectedIndex].text.toLowerCase())}</strong><br>Low, Medium and High local variants are retained.`;
  };
  categorySelect.onchange = updateGenerationFields;
  countInput.oninput = updateGenerationFields;
  updateGenerationFields();

  let assets = [];
  const renderAssets = () => {
    const quality = qualityFilter.value;
    root.querySelector("#asset-gallery").innerHTML = assets.length
      ? assets.map(asset => `<article><img src="${asset.url}?quality=${quality}" alt="${escapeHtml(asset.name)}"><strong>${escapeHtml(asset.name)}</strong><span>${escapeHtml(asset.kind)} · ${quality}</span>${asset.kind === "PERSON" ? "" : `<label>Complexity<select data-asset-complexity="${asset.asset_id}">${["SIMPLE","MEDIUM","COMPLEX"].map(value => `<option value="${value}" ${asset.complexity === value ? "selected" : ""}>${value}</option>`).join("")}</select></label>`}<button class="admin-history-button cost-delete-button cost-icon-action" type="button" data-delete-asset="${asset.asset_id}" data-asset-name="${escapeHtml(asset.name)}" aria-label="Delete ${escapeHtml(asset.name)}" title="Delete image">${DELETE_ICON}</button></article>`).join("")
      : "<p class=\"field-help\">No dataset images yet. Generate the reusable dataset or upload an image.</p>";
    root.querySelectorAll("[data-delete-asset]").forEach(button => button.onclick = async () => {
      if (!await wearoConfirm({ eyebrow: "Dataset image", title: `Delete ${button.dataset.assetName}?`, message: "This image will be removed from the active dataset and will not be selected for future benchmarks.", note: "Existing benchmark history remains available.", confirmLabel: "Delete image", cancelLabel: "Keep image" })) return;
      await api(`/assets/${button.dataset.deleteAsset}`, { method: "DELETE" });
      await load();
    });
    root.querySelectorAll("[data-asset-complexity]").forEach(select => select.onchange = async () => {
      select.disabled = true;
      try { await api(`/assets/${select.dataset.assetComplexity}/complexity`, {method:"PATCH", body:JSON.stringify({complexity:select.value})}); }
      finally { select.disabled = false; }
    });
  };
  const load = async () => {
    const [data, generations] = await Promise.all([api("/assets"), api("/dataset-generations")]);
    assets = data.assets;
    const counts = {};
    assets.forEach(asset => { counts[asset.kind] = (counts[asset.kind] || 0) + 1; });
    root.querySelector("#asset-summary").innerHTML = `<div class="admin-stat-grid cost-dataset-summary">${[["PERSON", "Person"], ["JEWELLERY", "Jewellery"], ["SAREE", "Sarees"], ["DRESS", "Dresses"]].map(([kind, label]) => `<article><span>${label}</span><strong>${counts[kind] || 0}</strong></article>`).join("")}</div>`;
    renderAssets();
    root.querySelector("#dataset-generation-status").innerHTML = generations.jobs.length
      ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Category</th><th>Complexity</th><th>Prompt / direction</th><th>Quality</th><th>Status</th><th>Progress</th><th>Generation cost</th><th>Started</th><th></th></tr></thead><tbody>${generations.jobs.map(job => `<tr><td>${escapeHtml(job.provider_name)} · ${escapeHtml(job.model_name)}</td><td>${escapeHtml(job.category || "ALL")}</td><td><span class="admin-status">${escapeHtml(job.complexity || "MEDIUM")}</span></td><td>${job.custom_prompt ? escapeHtml(job.custom_prompt) : "Built-in prompt"}${job.direction ? `<br><small>${escapeHtml(job.direction)}</small>` : ""}</td><td><span class="admin-status cost-quality-badge">${escapeHtml(job.generation_quality || "HIGH")}</span></td><td><span class="admin-status">${escapeHtml(job.status)}</span></td><td>${job.completed_items + job.failed_items + Number(job.cancelled_items || 0)}/${job.total_items}${job.failed_items ? ` (${job.failed_items} failed)` : ""}${job.cancelled_items ? ` (${job.cancelled_items} cancelled)` : ""}</td><td>${money(job.total_cost_usd)}</td><td>${new Date(job.created_at).toLocaleString()}</td><td>${["QUEUED", "RUNNING"].includes(job.status) ? `<button class="admin-history-button" type="button" data-cancel-dataset="${job.job_id}">Cancel</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`
      : "<p class=\"field-help\">No dataset generation has been started.</p>";
    root.querySelectorAll("[data-cancel-dataset]").forEach(button => button.onclick = async () => {
      if (!await wearoConfirm({ eyebrow: "Dataset generation", title: "Cancel this generation?", message: "No additional queued images will be generated.", note: "The image currently being processed may still finish, and completed images will remain in the dataset.", confirmLabel: "Cancel generation", cancelLabel: "Keep running" })) return;
      await api(`/dataset-generations/${button.dataset.cancelDataset}/cancel`, { method: "POST" });
      await load();
    });
  };

  qualityFilter.onchange = renderAssets;
  root.querySelector("#dataset-generation-form").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = form.querySelector(".form-status");
    const values = new FormData(form);
    try {
      await api("/dataset-generations", {
        method: "POST",
        body: JSON.stringify({
          model_id: values.get("model_id"),
          generation_quality: values.get("generation_quality"),
          category: values.get("category"),
          complexity: values.get("complexity"),
          count: Number(values.get("count")),
          prompt: values.get("prompt")?.trim() || null,
          direction: values.get("direction")?.trim() || null,
        }),
      });
      form.reset();
      updateGenerationFields();
      generationDialog.close();
      await load();
    } catch (error) {
      status.textContent = error.message;
    }
  };
  root.querySelector("#asset-form").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = form.querySelector(".form-status");
    try {
      await api("/assets", { method: "POST", body: new FormData(form) });
      form.reset();
      uploadDialog.close();
      await load();
    } catch (error) {
      status.textContent = error.message;
    }
  };
  await load();
  setInterval(() => route(location.pathname) === "datasets" && load(), 5000);
}
async function attachBenchmarks(root){const models=await api("/models"),dialog=root.querySelector("#benchmark-dialog"),form=root.querySelector("#benchmark-form");root.querySelector("#open-benchmark-dialog").onclick=()=>dialog.showModal();root.querySelectorAll("[data-close-dialog]").forEach(button=>button.onclick=()=>root.querySelector(`#${button.dataset.closeDialog}`).close());dialog.addEventListener("click",event=>{if(event.target===dialog)dialog.close();});form.querySelector("select[name=model_id]").innerHTML=models.models.filter(m=>m.enabled).map(m=>`<option value="${m.model_id}">${escapeHtml(m.provider_name)} · ${escapeHtml(m.name)}</option>`).join("");const load=async()=>{const data=await api("/benchmarks");root.querySelector("#run-list").innerHTML=data.runs.length?`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Quality profiles</th><th>Status</th><th>Progress</th><th>Try-ons</th><th></th></tr></thead><tbody>${data.runs.map(r=>`<tr><td><strong>${escapeHtml(r.provider_name)} · ${escapeHtml(r.model_name)}</strong><br><small>${new Date(r.created_at).toLocaleString()}</small></td><td>${r.qualities.map(quality=>`<span class="admin-status cost-quality-badge">${escapeHtml(quality)}</span>`).join(" ")}</td><td><span class="admin-status">${escapeHtml(r.status)}</span></td><td><strong>${r.completed_jobs}/${r.total_jobs}</strong></td><td>${r.total_jobs} total</td><td>${["QUEUED","RUNNING"].includes(r.status)?`<button data-cancel="${r.run_id}" class="admin-history-button">Cancel</button>`:""}</td></tr>`).join("")}</tbody></table></div>`:"<div class=\"cost-empty-state\"><strong>No benchmark runs yet</strong><p>Run the first benchmark to compare model cost across Low, Medium and High quality.</p></div>";root.querySelectorAll("[data-cancel]").forEach(button=>button.onclick=async()=>{await api(`/benchmarks/${button.dataset.cancel}/cancel`,{method:"POST"});await load();});};form.onsubmit=async event=>{event.preventDefault();const status=form.querySelector(".form-status"),values=new FormData(form);status.textContent="";try{await api("/benchmarks",{method:"POST",body:JSON.stringify({model_id:values.get("model_id")})});form.reset();dialog.close();await load();}catch(error){status.textContent=error.message;}};await load();setInterval(()=>route(location.pathname)==="benchmarks"&&load(),5000);}
async function attachInputOutputBenchmarks(root) {
  const [models, resultImages, dataset] = await Promise.all([api("/models"), api("/results/person-candidates"), api("/assets")]);
  const dialog = root.querySelector("#benchmark-dialog");
  const form = root.querySelector("#benchmark-form");
  root.querySelector("#open-benchmark-dialog").onclick = () => dialog.showModal();
  root.querySelectorAll("[data-close-dialog]").forEach(button => {
    button.onclick = () => root.querySelector(`#${button.dataset.closeDialog}`).close();
  });
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
  form.querySelector("select[name=model_id]").innerHTML = models.models.filter(model => model.enabled).map(model => `<option value="${model.model_id}">${escapeHtml(model.provider_name)} · ${escapeHtml(model.name)}</option>`).join("");
  const personField = form.querySelector("select[name=person_asset_id]").closest("label");
  const datasetPeople = dataset.assets.filter(asset => asset.kind === "PERSON");
  personField.innerHTML = `Person image<select name="person_asset_id"><option value="">Automatic (default)</option>${datasetPeople.map(person => `<option value="${person.asset_id}">${escapeHtml(person.name)}</option>`).join("")}</select><input name="person_result_tryon_id" type="hidden"><div class="cost-row-actions"><button id="open-result-person-picker" class="button button--quiet" type="button">Choose from Results</button><button id="clear-result-person" class="button button--quiet" type="button" hidden>Use automatic</button></div><small id="benchmark-person-selection">Automatic dataset person will be used.</small>`;
  const datasetPersonInput = form.elements.person_asset_id;
  const personInput = form.elements.person_result_tryon_id;
  const people = resultImages.images;
  const renderPersonPreview = () => {
    const resultPerson = people.find(item => item.tryon_id === personInput.value);
    const datasetPerson = datasetPeople.find(item => item.asset_id === datasetPersonInput.value);
    const selected = resultPerson || datasetPerson;
    const imageUrl = resultPerson?.image_url || datasetPerson?.url;
    root.querySelector("#benchmark-person-preview").innerHTML = selected
      ? `<img class="cost-result-card__image" src="${imageUrl}" alt="Selected person image">`
      : "<p class=\"field-help\">A person image will be selected automatically.</p>";
    root.querySelector("#benchmark-person-selection").textContent = resultPerson
      ? `${resultPerson.provider_name} · ${resultPerson.model_name} · Result ${resultPerson.ordinal + 1}`
      : datasetPerson
        ? `${datasetPerson.name} · Uploaded dataset image`
      : "Automatic dataset person will be used.";
    root.querySelector("#clear-result-person").hidden = !selected;
  };
  const picker = document.createElement("dialog");
  picker.className = "cost-dialog cost-image-preview-dialog";
  picker.innerHTML = `<div class="cost-dialog__header"><div><p class="eyebrow">Previous benchmark outputs</p><h2>Choose person image</h2></div><button class="cost-dialog__close" type="button" aria-label="Close person picker">×</button></div><div class="cost-result-gallery">${people.length ? people.map(item => `<button class="cost-result-person-choice" type="button" data-result-person="${item.tryon_id}"><img class="cost-result-card__image" src="${item.image_url}" alt="Result ${item.ordinal + 1}"><span>${escapeHtml(item.provider_name)} · ${escapeHtml(item.model_name)} · Result ${item.ordinal + 1}</span></button>`).join("") : "<p class=\"field-help\">No successful result images are available yet.</p>"}</div>`;
  root.append(picker);
  picker.querySelector(".cost-dialog__close").onclick = () => picker.close();
  picker.addEventListener("click", event => { if (event.target === picker) picker.close(); });
  picker.querySelectorAll("[data-result-person]").forEach(button => button.onclick = () => {
    personInput.value = button.dataset.resultPerson;
    datasetPersonInput.value = "";
    renderPersonPreview();
    picker.close();
  });
  datasetPersonInput.onchange = () => {
    if (datasetPersonInput.value) personInput.value = "";
    renderPersonPreview();
  };
  root.querySelector("#open-result-person-picker").onclick = () => picker.showModal();
  root.querySelector("#clear-result-person").onclick = () => { personInput.value = ""; datasetPersonInput.value = ""; renderPersonPreview(); };
  renderPersonPreview();
  const categoryInput = form.elements.category;
  categoryInput.closest("label").insertAdjacentHTML("afterend", '<label>Input complexity<select name="input_complexity"><option value="SIMPLE">Simple</option><option value="MEDIUM" selected>Medium</option><option value="COMPLEX">Complex</option></select><small>Only product images with this complexity are eligible.</small></label>');
  const complexityInput = form.elements.input_complexity;
  const selectedProducts = new Set();
  const productSourceField = document.createElement("div");
  productSourceField.className = "cost-benchmark-product-sources";
  productSourceField.innerHTML = `<strong>Product source images</strong><div class="cost-row-actions"><button id="open-benchmark-products" class="button button--quiet" type="button">Choose source images</button><button id="clear-benchmark-products" class="button button--quiet" type="button" hidden>Use all category images</button></div><small id="benchmark-product-selection">All active images in this category will be used.</small>`;
  categoryInput.closest("label").insertAdjacentElement("afterend", productSourceField);
  const productPicker = document.createElement("dialog");
  productPicker.className = "cost-dialog cost-image-preview-dialog";
  root.append(productPicker);
  const categoryProducts = () => dataset.assets.filter(asset => asset.kind === categoryInput.value && asset.complexity === complexityInput.value);
  const renderProductSelection = () => {
    const count = selectedProducts.size;
    root.querySelector("#benchmark-product-selection").textContent = count
      ? `${count} selected source image${count === 1 ? "" : "s"}. Only these products will be used.`
      : "All active images in this category will be used.";
    root.querySelector("#clear-benchmark-products").hidden = count === 0;
  };
  const renderProductPicker = () => {
    const products = categoryProducts();
    productPicker.innerHTML = `<div class="cost-dialog__header"><div><p class="eyebrow">${escapeHtml(categoryInput.value)} products</p><h2>Choose source images</h2></div><button class="cost-dialog__close" type="button" aria-label="Close product picker">×</button></div><p class="field-help">Select one or more source images. Leave all unselected to use every active image in this category.</p><div class="cost-result-gallery">${products.length ? products.map(item => `<button class="cost-result-person-choice${selectedProducts.has(item.asset_id) ? " is-selected" : ""}" type="button" data-benchmark-product="${item.asset_id}" aria-pressed="${selectedProducts.has(item.asset_id)}"><img class="cost-result-card__image" src="${item.url}" alt="${escapeHtml(item.name)}"><span>${escapeHtml(item.name)}</span></button>`).join("") : '<p class="field-help">No active product images are available in this category.</p>'}</div><div class="cost-dialog__actions"><button class="button button--primary" type="button" data-product-picker-done>Done</button></div>`;
    productPicker.querySelector(".cost-dialog__close").onclick = () => productPicker.close();
    productPicker.querySelector("[data-product-picker-done]").onclick = () => productPicker.close();
    productPicker.querySelectorAll("[data-benchmark-product]").forEach(button => button.onclick = () => {
      const id = button.dataset.benchmarkProduct;
      if (selectedProducts.has(id)) selectedProducts.delete(id); else selectedProducts.add(id);
      button.classList.toggle("is-selected", selectedProducts.has(id));
      button.setAttribute("aria-pressed", String(selectedProducts.has(id)));
      renderProductSelection();
    });
  };
  root.querySelector("#open-benchmark-products").onclick = () => { renderProductPicker(); productPicker.showModal(); };
  root.querySelector("#clear-benchmark-products").onclick = () => { selectedProducts.clear(); renderProductSelection(); };
  categoryInput.addEventListener("change", () => { selectedProducts.clear(); renderProductSelection(); });
  complexityInput.addEventListener("change", () => { selectedProducts.clear(); renderProductSelection(); });
  productPicker.addEventListener("click", event => { if (event.target === productPicker) productPicker.close(); });
  renderProductSelection();
  const imageCount = form.querySelector("input[name=image_count]");
  imageCount.oninput = () => { root.querySelector("#benchmark-image-count").textContent = imageCount.value || "0"; };
  const load = async () => {
    const data = await api("/benchmarks");
    root.querySelector("#run-list").innerHTML = data.runs.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model</th><th>Product</th><th>Images</th><th>Input quality</th><th>Output quality</th><th>Status</th><th>Progress</th><th>Actions</th></tr></thead><tbody>${data.runs.map(run => { const outputQuality = run.output_quality || run.qualities?.[0] || "HIGH"; return `<tr><td><strong>${escapeHtml(run.provider_name)} · ${escapeHtml(run.model_name)}</strong><br><small>${new Date(run.created_at).toLocaleString()}</small></td><td><span class="admin-status">${escapeHtml(run.category)}</span></td><td><strong>${run.total_jobs}</strong></td><td><span class="admin-status cost-quality-badge">${escapeHtml(run.input_quality || "HIGH")}</span></td><td><span class="admin-status cost-quality-badge">${escapeHtml(outputQuality)}</span></td><td><span class="admin-status">${escapeHtml(run.status)}</span></td><td><strong>${run.completed_jobs}/${run.total_jobs}</strong></td><td><div class="cost-row-actions"><button data-view-benchmark="${run.run_id}" data-view-benchmark-quality="${escapeHtml(outputQuality)}" class="admin-history-button cost-icon-action" type="button" aria-label="View benchmark results" title="View results">${VIEW_ICON}</button>${["QUEUED", "RUNNING"].includes(run.status) ? `<button data-cancel="${run.run_id}" class="admin-history-button" type="button">Cancel</button>` : ""}${["COMPLETED", "FAILED", "CANCEL_REQUESTED", "CANCELLED"].includes(run.status) ? `<button data-delete-benchmark="${run.run_id}" class="admin-history-button cost-delete-button cost-icon-action" type="button" aria-label="Delete benchmark" title="Delete benchmark">${DELETE_ICON}</button>` : ""}</div></td></tr>`; }).join("")}</tbody></table></div>` : "<div class=\"cost-empty-state\"><strong>No benchmark runs yet</strong><p>Run the first benchmark with selected product and image quality.</p></div>";
    root.querySelectorAll("[data-view-benchmark]").forEach(button => button.onclick = () => go(`results/${button.dataset.viewBenchmark}?quality=${encodeURIComponent(button.dataset.viewBenchmarkQuality)}`));
    root.querySelectorAll("[data-delete-benchmark]").forEach(button => button.onclick = async () => {
      if (!await wearoConfirm({eyebrow:"Benchmark result",title:"Delete this benchmark?",message:"The complete benchmark row, all try-on records, usage data and generated images will be permanently removed.",note:"This cannot be undone. Benchmarks used by a final model check are protected.",confirmLabel:"Delete benchmark",cancelLabel:"Keep benchmark",tone:"danger"})) return;
      try { await api(`/results/${button.dataset.deleteBenchmark}`, {method:"DELETE"}); await load(); } catch(error) { form.querySelector(".form-status").textContent=error.message; }
    });
    root.querySelectorAll("[data-cancel]").forEach(button => button.onclick = async () => {
      await api(`/benchmarks/${button.dataset.cancel}/cancel`, { method: "POST" });
      await load();
    });
  };
  form.onsubmit = async event => {
    event.preventDefault();
    const values = new FormData(form);
    const status = form.querySelector(".form-status");
    status.textContent = "";
    try {
      await api("/benchmarks", { method: "POST", body: JSON.stringify({ model_id: values.get("model_id"), person_asset_id: values.get("person_asset_id") || null, person_result_tryon_id: values.get("person_result_tryon_id") || null, product_asset_ids: [...selectedProducts], category: values.get("category"), input_complexity: values.get("input_complexity"), image_count: Number(values.get("image_count")), input_quality: values.get("input_quality"), output_quality: values.get("output_quality") }) });
      form.reset();
      selectedProducts.clear();
      renderProductSelection();
      renderPersonPreview();
      root.querySelector("#benchmark-image-count").textContent = "10";
      dialog.close();
      await load();
    } catch (error) { status.textContent = error.message; }
  };
  await load();
  setInterval(() => route(location.pathname) === "benchmarks" && load(), 5000);
}
async function attachResults(root, compare){const models=await api("/models");root.querySelector("#result-filter select[name=model_id]").insertAdjacentHTML("beforeend",models.models.map(m=>`<option value="${m.model_id}">${escapeHtml(m.provider_name)} · ${escapeHtml(m.name)}</option>`).join(""));const load=async()=>{const form=root.querySelector("#result-filter"),values=new FormData(form),query=new URLSearchParams();if(values.get("model_id"))query.set("model_id",values.get("model_id"));if(values.get("quality"))query.set("quality",values.get("quality"));const data=await api(`/results?${query}`),rate=Number(data.fx_rate?.rate||0),currency=values.get("currency"),rows=data.summaries,totalTryons=rows.reduce((sum,row)=>sum+Number(row.total_tryons||0),0),successfulTryons=rows.reduce((sum,row)=>sum+Number(row.successful_tryons||0),0),totalInputTokens=rows.reduce((sum,row)=>sum+Number(row.input_tokens||0),0),totalOutputTokens=rows.reduce((sum,row)=>sum+Number(row.output_tokens||0),0),totalCostUsd=rows.reduce((sum,row)=>sum+Number(row.total_cost_usd||0),0),displayCost=currency==="INR"&&rate?money(totalCostUsd*rate,"INR"):money(totalCostUsd);root.querySelector("#fx-note").textContent=currency==="INR"?(data.fx_rate?`USD/INR ${rate} from ${data.fx_rate.source}, fetched ${new Date(data.fx_rate.fetched_at).toLocaleString()}. Stored USD values remain unchanged.`:"No cached USD/INR rate. Refresh the rate or view results in USD."):"Costs are shown in the canonical stored currency, USD.";root.querySelector("#result-summary").innerHTML=`<article class="admin-metric-card"><div><span>Result groups</span><span class="metric-icon">◇</span></div><strong>${rows.length}</strong><small>Model and quality combinations</small></article><article class="admin-metric-card"><div><span>Successful try-ons</span><span class="metric-icon">✓</span></div><strong>${successfulTryons}/${totalTryons}</strong><small>Completed generations</small></article><article class="admin-metric-card"><div><span>Total input tokens</span><span class="metric-icon">↓</span></div><strong>${totalInputTokens.toLocaleString("en-IN")}</strong><small>Provider-reported filtered input</small></article><article class="admin-metric-card"><div><span>Total output tokens</span><span class="metric-icon">↑</span></div><strong>${totalOutputTokens.toLocaleString("en-IN")}</strong><small>Provider-reported filtered output</small></article><article class="admin-metric-card"><div><span>Success rate</span><span class="metric-icon">◎</span></div><strong>${totalTryons?((successfulTryons/totalTryons)*100).toFixed(1):"0.0"}%</strong><small>Across filtered try-ons</small></article><article class="admin-metric-card"><div><span>Total cost</span><span class="metric-icon">$</span></div><strong>${displayCost}</strong><small>Filtered generation spend</small></article>`;root.querySelector("#results-list").innerHTML=rows.length?`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Provider and model</th><th>Quality</th><th>Successful try-ons</th><th>Image tokens</th><th>Total cost</th><th>Average / success</th><th>Average latency</th></tr></thead><tbody>${rows.map(row=>{const convertedTotal=currency==="INR"&&rate?money(Number(row.total_cost_usd)*rate,"INR"):money(row.total_cost_usd),convertedAverage=currency==="INR"&&rate?money(Number(row.average_cost_usd)*rate,"INR"):money(row.average_cost_usd);return `<tr><td><strong>${escapeHtml(row.provider_name)} · ${escapeHtml(row.model_name)}</strong></td><td><span class="admin-status cost-quality-badge">${escapeHtml(row.quality)}</span></td><td><strong>${row.successful_tryons}/${row.total_tryons}</strong><br><small>${(Number(row.success_rate||0)*100).toFixed(1)}% success</small></td><td>${Number(row.input_tokens||0).toLocaleString("en-IN")} input<br>${Number(row.output_tokens||0).toLocaleString("en-IN")} output<br><small>${Number(row.total_reported_tokens||0).toLocaleString("en-IN")} total reported</small></td><td><strong>${convertedTotal}</strong></td><td>${convertedAverage}</td><td>${Math.round(Number(row.average_latency_ms||0))} ms</td></tr>`;}).join("")}</tbody></table></div>`:"<div class=\"cost-empty-state\"><strong>No completed results found</strong><p>Run a benchmark or change the selected filters.</p></div>";};root.querySelector("#result-filter").onsubmit=event=>{event.preventDefault();load();};root.querySelector("#refresh-fx").onclick=async()=>{try{await api("/fx/refresh",{method:"POST"});await load();}catch(error){root.querySelector("#fx-note").textContent=error.message;}};await load();}
async function attachCompare(root){const currencySelect=root.querySelector("#compare-currency select[name=currency]");const load=async()=>{const data=await api("/results"),rate=Number(data.fx_rate?.rate||0),currency=currencySelect.value,models=new Map();data.summaries.forEach(row=>{const key=`${row.provider_name}\u0000${row.model_name}`,current=models.get(key)||{provider_name:row.provider_name,model_name:row.model_name,total_tryons:0,total_tokens:0,total_cost_usd:0};current.total_tryons+=Number(row.total_tryons||0);current.total_tokens+=Number(row.total_reported_tokens||0);current.total_cost_usd+=Number(row.total_cost_usd||0);models.set(key,current);});const rows=[...models.values()];root.querySelector("#fx-note").textContent=currency==="INR"?(data.fx_rate?`USD/INR ${rate} from ${data.fx_rate.source}, fetched ${new Date(data.fx_rate.fetched_at).toLocaleString()}. Stored USD values remain unchanged.`:"No cached USD/INR rate. Refresh the rate or use USD."):"Costs are shown in the canonical stored currency, USD.";root.querySelector("#compare-list").innerHTML=rows.length?`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Model provider</th><th>Model used</th><th>Number of try-ons</th><th>Tokens consumed</th><th>Average tokens / try-on</th><th>Average cost / try-on</th></tr></thead><tbody>${rows.map(row=>{const averageTokens=row.total_tryons?row.total_tokens/row.total_tryons:0,averageCostUsd=row.total_tryons?row.total_cost_usd/row.total_tryons:0,averageCost=currency==="INR"&&rate?money(averageCostUsd*rate,"INR"):money(averageCostUsd);return `<tr><td>${escapeHtml(row.provider_name)}</td><td><strong>${escapeHtml(row.model_name)}</strong></td><td>${row.total_tryons}</td><td>${Math.round(row.total_tokens).toLocaleString("en-IN")}</td><td>${Math.round(averageTokens).toLocaleString("en-IN")}</td><td><strong>${averageCost}</strong></td></tr>`;}).join("")}</tbody></table></div>`:"<div class=\"cost-empty-state\"><strong>No models to compare yet</strong><p>Complete a benchmark to populate the comparison list.</p></div>";};currencySelect.onchange=load;root.querySelector("#refresh-fx").onclick=async()=>{try{await api("/fx/refresh",{method:"POST"});await load();}catch(error){root.querySelector("#fx-note").textContent=error.message;}};await load();}

async function attachModelComparisons(root) {
  const [persons, assets] = await Promise.all([api("/results/person-candidates"), api("/assets")]);
  const dialog = root.querySelector("#comparison-dialog"), form = root.querySelector("#comparison-form");
  const imageDialog = document.createElement("dialog");
  imageDialog.className = "cost-dialog cost-image-preview-dialog";
  imageDialog.innerHTML = `<div class="cost-dialog__header"><div><p class="eyebrow">Comparison image</p><h2>Full image</h2></div><button class="cost-dialog__close" type="button" aria-label="Close full image">×</button></div><img class="cost-image-preview-dialog__image" alt="Full comparison image"><div class="cost-dialog__actions"><a class="button button--primary" download>Download image</a></div>`;
  root.append(imageDialog);
  imageDialog.querySelector(".cost-dialog__close").onclick = () => imageDialog.close();
  imageDialog.addEventListener("click", event => { if (event.target === imageDialog) imageDialog.close(); });
  const wireComparisonImages = () => root.querySelectorAll("[data-comparison-image]").forEach(image => image.onclick = () => {
    const url = new URL(image.dataset.comparisonImage, location.origin).href;
    imageDialog.querySelector("img").src = url;
    imageDialog.querySelector("h2").textContent = image.alt || "Full image";
    imageDialog.querySelector("a").href = url;
    imageDialog.querySelector("a").download = `${(image.alt || "comparison-image").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.png`;
    imageDialog.showModal();
  });
  root.querySelector("#open-comparison").onclick = () => dialog.showModal();
  dialog.querySelector(".cost-dialog__close").onclick = () => dialog.close();
  const choose = (items, title, onSelect) => {
    const picker = document.createElement("dialog"); picker.className = "cost-dialog cost-image-preview-dialog";
    picker.innerHTML = `<div class="cost-dialog__header"><h2>${escapeHtml(title)}</h2><button class="cost-dialog__close" type="button">×</button></div><div class="cost-result-gallery">${items.map((item,index)=>`<button class="cost-result-person-choice" type="button" data-choice="${index}"><img class="cost-result-card__image" src="${item.image_url || item.url}" alt="Choice ${index+1}"><span>${escapeHtml(item.name || `${item.provider_name} · ${item.model_name} · Result ${item.ordinal+1}`)}</span></button>`).join("")}</div>`;
    root.append(picker); picker.querySelector(".cost-dialog__close").onclick=()=>picker.close();
    picker.querySelectorAll("[data-choice]").forEach(button=>button.onclick=()=>{onSelect(items[Number(button.dataset.choice)]);picker.close();}); picker.showModal();
  };
  root.querySelector("#choose-comparison-person").onclick=()=>choose(persons.images,"Choose person from Results",item=>{form.elements.person_result_tryon_id.value=item.tryon_id;root.querySelector("#comparison-person").innerHTML=`<img class="cost-result-card__image" src="${item.image_url}" alt="Selected person">`;});
  const chooseProduct=()=>{const category=form.elements.category.value, products=assets.assets.filter(item=>item.kind===category);choose(products,`Choose ${category.toLowerCase()}`,item=>{form.elements.product_asset_id.value=item.asset_id;root.querySelector("#comparison-product").innerHTML=`<img class="cost-result-card__image" src="${item.url}" alt="Selected product">`;});};
  root.querySelector("#choose-comparison-product").onclick=chooseProduct;
  form.elements.category.onchange=()=>{form.elements.product_asset_id.value="";root.querySelector("#comparison-product").innerHTML="";};
  const detail=async id=>{const data=await api(`/model-comparisons/${id}`),c=data.comparison;root.querySelector("#comparison-detail").innerHTML=`<div class="cost-panel-heading"><h2>Comparison results</h2><p>${escapeHtml(c.category)} · ${escapeHtml(c.output_quality)}</p></div><div class="cost-result-gallery"><article class="cost-result-card"><img class="cost-result-card__image cost-clickable-image" src="${c.person_url}" data-comparison-image="${c.person_url}" alt="Person input"><div class="cost-result-card__body"><strong>Person input</strong><small>Click image to view full size</small></div></article><article class="cost-result-card"><img class="cost-result-card__image cost-clickable-image" src="${c.product_url}" data-comparison-image="${c.product_url}" alt="Product input"><div class="cost-result-card__body"><strong>Product input</strong><small>Click image to view full size</small></div></article>${data.results.map(item=>`<article class="cost-result-card">${item.image_url?`<img class="cost-result-card__image cost-clickable-image" src="${item.image_url}" data-comparison-image="${item.image_url}" alt="${escapeHtml(item.model_name)} output">`:`<div class="cost-result-card__missing">${escapeHtml(item.tryon_status)}</div>`}<div class="cost-result-card__body"><strong>${escapeHtml(item.provider_name)} · ${escapeHtml(item.model_name)}</strong><span>${money(item.calculated_cost_usd)}</span><span>${Number(item.total_reported_tokens||0).toLocaleString()} tokens</span><small>Input ${Number(item.image_input_tokens||0).toLocaleString()} · Output ${Number(item.image_output_tokens||0).toLocaleString()}</small>${item.image_url?"<small>Click image to view full size</small>":""}</div></article>`).join("")}</div>`;wireComparisonImages();};
  const load=async()=>{const data=await api("/model-comparisons");root.querySelector("#comparison-list").innerHTML=data.comparisons.length?`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Created</th><th>Category</th><th>Quality</th><th>Models</th><th>Status</th><th></th></tr></thead><tbody>${data.comparisons.map(c=>`<tr><td>${new Date(c.created_at).toLocaleString()}</td><td>${escapeHtml(c.category)}</td><td>${escapeHtml(c.output_quality)}</td><td>${c.finished_count}/${c.model_count}</td><td>${escapeHtml(c.status)}</td><td><button class="admin-history-button cost-icon-action" data-view-comparison="${c.comparison_id}" aria-label="View comparison" title="View comparison">${VIEW_ICON}</button></td></tr>`).join("")}</tbody></table></div>`:"<p class=\"field-help\">No comparisons yet.</p>";root.querySelectorAll("[data-view-comparison]").forEach(b=>b.onclick=()=>detail(b.dataset.viewComparison));};
  form.onsubmit=async event=>{event.preventDefault();const values=new FormData(form),status=form.querySelector(".form-status");try{const result=await api("/model-comparisons",{method:"POST",body:JSON.stringify(Object.fromEntries(values))});dialog.close();await load();await detail(result.comparison_id);}catch(error){status.textContent=error.message;}};
  await load(); setInterval(()=>route(location.pathname)==="compare"&&load(),5000);
}

function resultDetailId(pathname) {
  return pathname.match(/^\/admin\/cost-lab\/results\/([^/?]+)/)?.[1] || null;
}

function resultDetailView() {
  return `<section class="cost-result-detail"><a class="admin-back-link" href="/admin/cost-lab/results">← Back to results</a><div id="result-detail-content" class="admin-data-panel">Loading result images…</div></section>`;
}

async function attachResultDetail(root, pathname) {
  const runId = resultDetailId(pathname);
  const quality = new URLSearchParams(location.search).get("quality");
  const data = await api(`/results/${runId}`);
  const tryons = quality ? data.tryons.filter(item => item.quality === quality) : data.tryons;
  const totalCost = tryons.reduce((sum, item) => sum + Number(item.calculated_cost_usd || 0), 0);
  root.querySelector("#result-detail-content").innerHTML = `<div class="cost-panel-heading"><p class="eyebrow">Generated try-on images</p><h2>${escapeHtml(data.run.provider_name)} · ${escapeHtml(data.run.model_name)}</h2><p>${quality ? `${escapeHtml(quality)} output quality · ` : ""}${tryons.length} try-ons · ${money(totalCost)} calculated cost</p></div><div class="cost-result-view-list">${tryons.map(item => { const inputTokens = Number(item.text_input_tokens || 0) + Number(item.image_input_tokens || 0) + Number(item.cached_input_tokens || 0); return `<article class="cost-result-card cost-result-view"><div class="cost-result-view__images"><figure><figcaption>Person</figcaption><img src="${item.person_url}" alt="Person input for try-on ${item.ordinal + 1}"></figure><figure class="cost-result-view__generated"><figcaption>Generated try-on</figcaption>${item.image_url ? `<img src="${item.image_url}" alt="Generated try-on ${item.ordinal + 1}">` : `<div class="cost-result-card__missing">${escapeHtml(item.status)}<small>${escapeHtml(item.error_detail || "No generated image")}</small></div>`}</figure><figure><figcaption>Wear item</figcaption><img src="${item.product_url}" alt="${escapeHtml(item.product_asset_name)}"></figure></div><div class="cost-result-card__body"><div class="cost-result-card__title"><strong>Try-on ${item.ordinal + 1}</strong><span class="admin-status">Input ${escapeHtml(item.input_quality)} · Output ${escapeHtml(item.output_quality)}</span></div><dl><div><dt>Actual output pixels</dt><dd>${item.pixel_width && item.pixel_height ? `${item.pixel_width} × ${item.pixel_height}` : "—"}</dd></div><div><dt>Format</dt><dd>${escapeHtml(item.image_format || "—")}</dd></div><div><dt>File size</dt><dd>${item.file_size_bytes ? `${(Number(item.file_size_bytes) / 1024).toFixed(1)} KB` : "—"}</dd></div><div><dt>Input tokens</dt><dd>${inputTokens.toLocaleString("en-IN")}</dd></div><div><dt>Output tokens</dt><dd>${Number(item.image_output_tokens || 0).toLocaleString("en-IN")}</dd></div><div><dt>Total reported tokens</dt><dd>${Number(item.total_reported_tokens || 0).toLocaleString("en-IN")}</dd></div><div><dt>Cost</dt><dd>${money(item.calculated_cost_usd)}</dd></div><div><dt>Latency</dt><dd>${item.latency_ms ? `${item.latency_ms} ms` : "—"}</dd></div></dl>${item.download_url ? `<a class="button button--primary" href="${item.download_url}">Download generated image</a>` : ""}</div></article>`; }).join("")}</div>`;
  const inputDialog = document.createElement("dialog");
  inputDialog.className = "cost-dialog cost-image-preview-dialog";
  inputDialog.innerHTML = `<div class="cost-dialog__header"><div><p class="eyebrow">Benchmark input</p><h2>Product input image</h2></div><button class="cost-dialog__close" type="button" aria-label="Close product image preview">×</button></div><img class="cost-image-preview-dialog__image" alt="Product input image"><label>Image URL<input class="cost-image-preview-dialog__url" readonly></label><div class="cost-dialog__actions"><button class="button button--quiet" type="button" data-copy-product-url>Copy URL</button><a class="button button--primary" target="_blank" rel="noopener noreferrer">Open original</a></div>`;
  root.append(inputDialog);
  inputDialog.querySelector(".cost-dialog__close").onclick = () => inputDialog.close();
  inputDialog.addEventListener("click", event => { if (event.target === inputDialog) inputDialog.close(); });
  root.querySelectorAll("[data-product-preview-url]").forEach(button => button.onclick = () => {
    const url = new URL(button.dataset.productPreviewUrl, location.origin).href;
    inputDialog.querySelector("h2").textContent = button.dataset.productPreviewName || "Product input image";
    inputDialog.querySelector("img").src = url;
    inputDialog.querySelector("input").value = url;
    inputDialog.querySelector("a").href = url;
    inputDialog.querySelector("[data-copy-product-url]").textContent = "Copy URL";
    inputDialog.showModal();
  });
  inputDialog.querySelector("[data-copy-product-url]").onclick = async event => {
    await navigator.clipboard.writeText(inputDialog.querySelector("input").value);
    event.currentTarget.textContent = "Copied";
  };
}

function refreshedResultsView() {
  return resultsView(false).replace(
    '<button id="refresh-fx" class="button button--quiet" type="button">Refresh USD/INR</button>',
    '<button id="refresh-costs" class="button button--quiet" type="button">Refresh costs</button><button id="refresh-fx" class="button button--quiet" type="button">Refresh USD/INR</button>',
  );
}

async function attachRefreshedResults(root) {
  await attachResults(root, false);
  const decorateRows = async () => {
    const table = root.querySelector("#results-list table");
    if (!table || table.dataset.actionsAdded) return;
    const values = new FormData(root.querySelector("#result-filter")), query = new URLSearchParams();
    if (values.get("model_id")) query.set("model_id", values.get("model_id"));
    if (values.get("quality")) query.set("quality", values.get("quality"));
    const data = await api(`/results?${query}`);
    table.querySelector("thead tr").insertAdjacentHTML("beforeend", "<th>Action</th>");
    table.querySelectorAll("tbody tr").forEach((row, index) => {
      const item = data.summaries[index];
      if (item && row.cells[1]) row.cells[1].innerHTML = `<span class="admin-status cost-quality-badge">Input ${escapeHtml(item.input_quality)}</span><br><span class="admin-status cost-quality-badge">Output ${escapeHtml(item.output_quality)}</span>`;
      if (item) row.insertAdjacentHTML("beforeend", `<td><div class="cost-row-actions"><a class="admin-history-button cost-icon-action" href="/admin/cost-lab/results/${item.run_id}?quality=${encodeURIComponent(item.quality)}" aria-label="View benchmark result" title="View result">${VIEW_ICON}</a>${["COMPLETED", "FAILED", "CANCEL_REQUESTED", "CANCELLED"].includes(item.run_status) ? `<button class="admin-history-button cost-delete-button cost-icon-action" type="button" data-delete-result="${item.run_id}" aria-label="Delete benchmark result" title="Delete benchmark result">${DELETE_ICON}</button>` : ""}</div></td>`);
    });
    table.querySelectorAll("[data-delete-result]").forEach(button => button.onclick = async () => {
      if (!await wearoConfirm({
        eyebrow: "Benchmark result",
        title: "Delete this benchmark result?",
        message: "The complete benchmark row, all try-on records, usage data and generated images will be permanently removed.",
        note: "This cannot be undone. Benchmarks used by a final model check are protected.",
        confirmLabel: "Delete benchmark",
        cancelLabel: "Keep run",
        tone: "danger",
      })) return;
      const original = button.innerHTML;
      button.disabled = true;
      button.textContent = "…";
      button.setAttribute("aria-label", "Deleting benchmark result");
      try {
        await api(`/results/${button.dataset.deleteResult}`, { method: "DELETE" });
        await renderAuthenticated(root, location.pathname);
      } catch (error) {
        button.disabled = false;
        button.innerHTML = original;
        button.setAttribute("aria-label", "Delete benchmark result");
        root.querySelector("#fx-note").textContent = error.message;
      }
    });
    table.dataset.actionsAdded = "true";
  };
  const resultsList = root.querySelector("#results-list");
  new MutationObserver(() => { decorateRows(); }).observe(resultsList, { childList: true });
  await decorateRows();
  const button = root.querySelector("#refresh-costs");
  button.onclick = async () => {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Refreshing…";
    try {
      const result = await api("/results/recalculate", { method: "POST" });
      await renderAuthenticated(root, location.pathname);
      root.querySelector("#fx-note").textContent = `${result.updated} try-on cost records recalculated from current model pricing${result.skipped ? `; ${result.skipped} skipped without pricing` : ""}.`;
    } catch (error) {
      button.disabled = false;
      button.textContent = original;
      root.querySelector("#fx-note").textContent = error.message;
    }
  };
}

async function attachKnowledge(root) {
  const textDialog = root.querySelector("#knowledge-text-dialog");
  const pdfDialog = root.querySelector("#knowledge-pdf-dialog");
  root.querySelector("#open-knowledge-text").onclick = () => textDialog.showModal();
  root.querySelector("#open-knowledge-pdf").onclick = () => pdfDialog.showModal();
  root.querySelectorAll("[data-close-dialog]").forEach(button => {
    button.onclick = () => root.querySelector(`#${button.dataset.closeDialog}`).close();
  });
  [textDialog, pdfDialog].forEach(dialog => dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  }));
  const load = async () => {
    const data = await api("/knowledge");
    root.querySelector("#knowledge-list").innerHTML = data.items.length ? `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Title</th><th>Type</th><th>Details</th><th>Added</th><th>Actions</th></tr></thead><tbody>${data.items.map(item => `<tr><td><strong>${escapeHtml(item.title)}</strong>${item.preview ? `<br><small class="cost-knowledge-preview">${escapeHtml(item.preview)}${item.preview.length >= 240 ? "…" : ""}</small>` : ""}</td><td><span class="admin-status">${escapeHtml(item.source_type)}</span></td><td>${item.source_type === "PDF" ? `${escapeHtml(item.original_filename || "PDF document")}<br>` : "Pasted text<br>"}<small>${Math.max(1, Math.ceil(Number(item.size_bytes || 0) / 1024)).toLocaleString("en-IN")} KB</small></td><td>${new Date(item.created_at).toLocaleString()}</td><td><div class="cost-row-actions"><a class="admin-history-button" href="${API}/knowledge/${item.knowledge_id}/content" target="_blank" rel="noreferrer">View</a><button class="admin-history-button cost-delete-button" type="button" data-delete-knowledge="${item.knowledge_id}" data-knowledge-title="${escapeHtml(item.title)}">Delete</button></div></td></tr>`).join("")}</tbody></table></div>` : `<div class="cost-empty-state"><strong>No knowledge added yet</strong><p>Upload a PDF or paste text to build the Cost Lab reference library.</p></div>`;
    root.querySelectorAll("[data-delete-knowledge]").forEach(button => button.onclick = async () => {
      if (!window.confirm(`Delete “${button.dataset.knowledgeTitle}”? This cannot be undone.`)) return;
      button.disabled = true;
      button.textContent = "Deleting…";
      try { await api(`/knowledge/${button.dataset.deleteKnowledge}`, { method: "DELETE" }); await load(); }
      catch (error) { button.disabled = false; button.textContent = error.message; }
    });
  };
  root.querySelector("#knowledge-text-form").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget, status = form.querySelector(".form-status"), submit = form.querySelector("button[type=submit]"), values = Object.fromEntries(new FormData(form));
    submit.disabled = true;
    submit.textContent = "Formatting…";
    status.textContent = "Formatting the complete text with the Wearo analysis model…";
    try {
      await api("/knowledge/text", { method: "POST", body: JSON.stringify(values) });
      form.reset(); textDialog.close(); await load();
    } catch (error) { status.textContent = error.message; }
    finally { submit.disabled = false; submit.textContent = "Save knowledge"; }
  };
  root.querySelector("#knowledge-pdf-form").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget, status = form.querySelector(".form-status");
    status.textContent = "";
    try {
      await api("/knowledge/pdf", { method: "POST", body: new FormData(form) });
      form.reset(); pdfDialog.close(); await load();
    } catch (error) { status.textContent = error.message; }
  };
  await load();
}

async function renderAuthenticated(root, pathname) {
  const active=route(pathname),detailId=resultDetailId(pathname);const views={"":overview,providers:providersView,models:modelsView,datasets:datasetsView,knowledge:knowledgeView,benchmarks:benchmarksView,results:detailId?resultDetailView:refreshedResultsView,compare:modelComparisonsView,"final-checks":finalChecksView,"promoted-models":promotedModelsView};root.innerHTML=shell(active,(views[active]||overview)());actionIconObserver?.disconnect();actionIconObserver=new MutationObserver(()=>syncActionIcons(root));actionIconObserver.observe(root,{childList:true,subtree:true});root.querySelectorAll("a[href^='/admin/cost-lab']").forEach(a=>a.onclick=e=>{e.preventDefault();go(a.getAttribute("href").replace("/admin/cost-lab/","").replace("/admin/cost-lab",""));});root.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>go(b.dataset.go));root.querySelector("#cost-logout").onclick=async()=>{await api("/auth/logout",{method:"POST"});go("login");};try{if(active==="")await attachOverview(root);if(active==="providers")await attachProviders(root);if(active==="models")await attachModels(root);if(active==="datasets")await attachQualityDatasets(root);if(active==="knowledge")await attachKnowledge(root);if(active==="benchmarks")await attachInputOutputBenchmarks(root);if(active==="results"&&detailId)await attachResultDetail(root,pathname);if(active==="results"&&!detailId)await attachRefreshedResults(root);if(active==="compare")await attachModelComparisons(root);if(active==="final-checks")await attachFinalChecks(root);if(active==="promoted-models")await attachPromotedModels(root);syncActionIcons(root);}catch(e){if(e.status===401)go("login");else{const p=document.createElement("p");p.className="form-status form-status--error";p.textContent=e.message;root.querySelector(".admin-content")?.prepend(p);}}
}
export async function renderCostLab(root, pathname) {
  const login=route(pathname)==="login";let authenticated=false;try{await api("/auth/session");authenticated=true;}catch{}
  if(!authenticated){root.innerHTML=loginView();root.querySelector("#cost-login").onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,d=Object.fromEntries(new FormData(f));try{await api("/auth/login",{method:"POST",body:JSON.stringify(d)});go("");}catch(x){f.querySelector(".form-status").textContent=x.message;}};return;}
  if(login){go("");return;}await renderAuthenticated(root,pathname);
}
