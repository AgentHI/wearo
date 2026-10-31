import { compactBrandMarkup } from "./brand.js";

const API_BASE = "/api/v1";
const AUTH_KEY = "wearo_consumer_auth";
const AUTH_IDENTITY_VERSION = 2;
const SHOP_CONTEXT_KEY = "wearo_shop_context";
const SHOP_DETAILS_KEY = "wearo_shop_details";
const SHOP_DETAILS_VERSION = 6;
const SPONSORED_SESSION_KEY = "wearo_sponsored_session";
const TRY_ON_COMPLETE_SOUND = "/wearo-tryon-complete.wav";

function captureShopContext(pathname) {
  const match = pathname.match(/^\/shop\/([^/]+)(?:\/([^/]+))?\/?$/);
  if (!match) return;
  const key = new URLSearchParams(window.location.search).get("key");
  if (!key) return;
  const nextContext = {
    businessReference: decodeURIComponent(match[1]),
    storeReference: match[2] ? decodeURIComponent(match[2]) : null,
    key,
  };
  const previousContext = readShopContext();
  sessionStorage.setItem(SHOP_CONTEXT_KEY, JSON.stringify(nextContext));
  if (
    previousContext?.businessReference !== nextContext.businessReference
    || previousContext?.storeReference !== nextContext.storeReference
    || previousContext?.key !== nextContext.key
  ) {
    sessionStorage.removeItem(SHOP_DETAILS_KEY);
    sessionStorage.removeItem(SPONSORED_SESSION_KEY);
  }
}

function readShopContext() {
  try { return JSON.parse(sessionStorage.getItem(SHOP_CONTEXT_KEY) || "null"); }
  catch { return null; }
}

function readShopDetails() {
  try {
    const details = JSON.parse(sessionStorage.getItem(SHOP_DETAILS_KEY) || "null");
    return details?._cacheVersion === SHOP_DETAILS_VERSION ? details : null;
  }
  catch { return null; }
}

async function loadShopDetails() {
  const context = readShopContext();
  if (!context) return null;
  const shopPath = context.storeReference
    ? `/public/shops/${encodeURIComponent(context.businessReference)}/stores/${encodeURIComponent(context.storeReference)}`
    : `/public/shops/${encodeURIComponent(context.businessReference)}`;
  const details = await api(`${shopPath}?key=${encodeURIComponent(context.key)}`);
  let logoDataUrl = null;
  if (details.logo_url) {
    try {
      const logoResponse = await fetch(details.logo_url, { credentials: "same-origin", cache: "no-store" });
      if (!logoResponse.ok) throw new Error("Business logo unavailable.");
      const logoBlob = await logoResponse.blob();
      if (!logoBlob.type.startsWith("image/")) throw new Error("Invalid business logo response.");
      logoDataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.addEventListener("load", () => resolve(reader.result), { once: true });
        reader.addEventListener("error", () => reject(reader.error), { once: true });
        reader.readAsDataURL(logoBlob);
      });
    } catch {
      // The business initial remains a safe fallback when the logo cannot be loaded.
    }
  }
  const cachedDetails = { ...details, logo_data_url: logoDataUrl, _cacheVersion: SHOP_DETAILS_VERSION };
  sessionStorage.setItem(SHOP_DETAILS_KEY, JSON.stringify(cachedDetails));
  return cachedDetails;
}

function saveSponsoredSession(value) {
  sessionStorage.setItem(SPONSORED_SESSION_KEY, JSON.stringify(value));
}

function leaveBusinessExperience() {
  sessionStorage.removeItem(SHOP_CONTEXT_KEY);
  sessionStorage.removeItem(SHOP_DETAILS_KEY);
  sessionStorage.removeItem(SPONSORED_SESSION_KEY);
  window.location.assign("/app/");
}

function readSponsoredSession() {
  try { return JSON.parse(sessionStorage.getItem(SPONSORED_SESSION_KEY) || "null"); }
  catch { return null; }
}

async function ensureSponsoredSession(auth) {
  const context = readShopContext();
  if (!context) return null;
  const existing = readSponsoredSession();
  if (existing?.session_id) {
    try {
      const session = await api(
        `/sponsored-sessions/${encodeURIComponent(existing.session_id)}`,
        {},
        auth,
      );
      saveSponsoredSession(session);
      return session;
    } catch (error) {
      if (error.code !== "SESSION_UNAVAILABLE") throw error;
      sessionStorage.removeItem(SPONSORED_SESSION_KEY);
    }
  }
  const sessionPath = context.storeReference
    ? `/public/shops/${encodeURIComponent(context.businessReference)}/stores/${encodeURIComponent(context.storeReference)}/sessions`
    : `/public/shops/${encodeURIComponent(context.businessReference)}/sessions`;
  const session = await api(
    sessionPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: context.key }),
    },
    auth,
  );
  saveSponsoredSession(session);
  return session;
}

let installPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  document.querySelector("#install-app")?.removeAttribute("hidden");
});

function readAuth() {
  try {
    const auth = JSON.parse(sessionStorage.getItem(AUTH_KEY) || "null");
    return auth?.csrfToken ? auth : null;
  } catch {
    return null;
  }
}

function saveAuth(auth) {
  sessionStorage.setItem(AUTH_KEY, JSON.stringify(auth));
}

function clearAuth() {
  sessionStorage.removeItem(AUTH_KEY);
}

function consumerRoute(pathname) {
  if (pathname.startsWith("/app/sign-in")) return "sign-in";
  if (pathname.startsWith("/app/account-status")) return "account-status";
  if (pathname.startsWith("/app/history")) return "history";
  if (pathname.startsWith("/app/profile")) return "profile";
  if (pathname === "/shop" || pathname.startsWith("/shop/") || pathname.startsWith("/app/try-on")) return "home";
  return "home";
}

function resolvedRoute(pathname, auth) {
  let route = consumerRoute(pathname);
  if (!auth && route !== "sign-in") route = "sign-in";
  if (auth && route === "sign-in") route = auth.hasProfile ? "home" : "profile";
  if (auth?.accountStatus === "DELETION_PENDING") route = "account-status";
  if (auth && !auth.hasProfile && !["profile", "account-status"].includes(route)) route = "profile";
  const expectedPath = {
    "sign-in": "/app/sign-in",
    home: "/app/",
    history: "/app/history",
    profile: "/app/profile",
    "account-status": "/app/account-status",
  }[route];
  const isShopEntry = pathname.startsWith("/shop/");
  if (!isShopEntry && window.location.pathname !== expectedPath) window.history.replaceState({}, "", expectedPath);
  return route;
}

async function api(path, options = {}, auth = readAuth()) {
  const headers = new Headers(options.headers || {});
  if (auth?.csrfToken && options.method && !["GET", "HEAD"].includes(options.method)) {
    headers.set("X-CSRF-Token", auth.csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  let body = {};
  if (response.status !== 204) {
    const responseText = await response.text();
    if (responseText) {
      try {
        body = JSON.parse(responseText);
      } catch {
        body = {
          code: "INVALID_API_RESPONSE",
          message:
            response.status >= 500
              ? `Wearo API returned ${response.status} ${response.statusText || "Internal Server Error"}. Make sure the backend is running on 127.0.0.1:8000 and check its terminal log.`
              : `Wearo API returned an unreadable response (${response.status}).`,
        };
      }
    }
  }
  if (!response.ok) {
    const error = new Error(body.message || "The request could not be completed.");
    error.code = body.code;
    error.status = response.status;
    throw error;
  }
  return body;
}

function consumerFrame(route, content, authenticated, shopDetails = null) {
  const nav = [
    ["home", "/app/", "✦", "Try on"],
    ["history", "/app/history", "◫", "Looks"],
    ["profile", "/app/profile", "○", "Profile"],
  ]
    .map(
      ([id, href, icon, label]) => `
        <a href="${href}" ${route === id ? 'aria-current="page"' : ""}>
          <span aria-hidden="true">${icon}</span><small>${label}</small>
        </a>`,
    )
    .join("");
  return `
    <div class="consumer-app consumer-app--${route}${shopDetails ? " consumer-app--shop" : ""}">
      <header class="consumer-header">
        ${shopDetails ? `<div class="shop-brand">${shopDetails.logo_data_url ? `<img src="${escapeHtml(shopDetails.logo_data_url)}" alt="${escapeHtml(shopDetails.display_name)} logo" />` : `<span>${escapeHtml(shopDetails.display_name).slice(0, 1)}</span>`}<strong>${escapeHtml(shopDetails.display_name)}</strong><small>with Wearo.ai</small></div>` : compactBrandMarkup(authenticated ? "/app/" : "/app/sign-in")}
        <div class="consumer-header__actions">
          <button id="install-app" class="icon-button install-button" type="button" hidden aria-label="Install Wearo app">↓</button>
          ${authenticated ? '<a class="avatar-button" href="/app/profile" aria-label="Open profile">M</a>' : ""}
        </div>
      </header>
      <main id="main" class="consumer-main consumer-main--${route}">${content}</main>
      ${authenticated && route !== "account-status" ? `<nav class="bottom-nav" aria-label="Consumer app">${nav}</nav>` : ""}
    </div>`;
}

function signInView(shopDetails = null) {
  const shopName = shopDetails?.display_name;
  return `
    <section class="consumer-auth">
      ${shopName ? `<div class="shop-welcome"><img class="shop-welcome__wearo-logo" src="/wearo-brand.png" alt="Wearo.ai" /><p class="eyebrow">Private virtual try-on</p><h1>Wearo.ai</h1><p>${escapeHtml(shopDetails.caption || "Try before you buy with your private Wearo profile.")}</p></div>` : ""}
      <div class="flow-progress" aria-label="Account setup progress"><span class="is-active">1</span><i></i><span>2</span><i></i><span>3</span></div>
      <p class="eyebrow">Step 1 of 3</p>
      <h1>${shopName ? "Start your try-on" : "Sign up or sign in"}</h1>
      <p id="consumer-auth-intro" class="lede">Use your email or mobile number. New accounts are created automatically.</p>
      <form id="auth-form" class="consumer-card">
        ${shopName ? `<label>Your name
          <input name="name" type="text" autocomplete="name" minlength="2" maxlength="80" required placeholder="Enter your name" />
        </label>` : ""}
        <label>Email or mobile number
          <input name="destination" type="text" autocomplete="username" required placeholder="you@example.com or +91…" />
        </label>
        <button id="request-code" class="button button--primary button--full" type="button">Send sign-in code</button>
        <div id="code-step" class="code-step" hidden>
          <label>Sign-in code
            <input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" minlength="4" maxlength="8" placeholder="Enter code" />
          </label>
          <button id="verify-code" class="button button--primary button--full" type="button">Continue</button>
        </div>
        <p class="field-help">Local test mode displays the fake code after you press Send.</p>
        <p id="auth-status" class="form-status status-panel" role="status" aria-live="polite"></p>
      </form>
      <div class="privacy-card"><span aria-hidden="true">⌾</span><div><strong>Private by design</strong><p>Your personal images are not authorised for model training.</p></div></div>
    </section>`;
}

function homeView() {
  return `
    <header class="home-heading">
      <div><p class="eyebrow">Your private fitting room</p><h1>Try it on</h1><p>Upload or photograph a wearable and see it with your saved person profile.</p></div>
      <a class="profile-shortcut" href="/app/profile"><span>○</span> Edit profile</a>
    </header>
    <section id="sponsored-session-card" class="notice sponsored-session-card" hidden aria-live="polite"></section>
    <section class="allowance-card" aria-label="Daily beta allowance"><div><span id="allowance-count" class="allowance-ring">—</span><div><strong><span id="allowance-copy">Loading</span> previews available</strong><p id="allowance-note">Beta testing · 3 successful previews per day.</p></div></div><div class="allowance-actions"><span>Beta · Today</span><button id="refresh-allowance" class="allowance-refresh" type="button" aria-label="Refresh try-on balance" title="Refresh try-on balance">↻</button></div></section>
    <section class="tryon-studio" aria-labelledby="tryon-title">
      <div class="tryon-studio__heading"><div><p class="eyebrow">Wearable item</p><h2 id="tryon-title">Choose what you want to wear</h2></div><span>Apparel + jewellery</span></div>
      <div class="tryon-workspace">
        <div id="preview-canvas" class="mobile-preview__canvas" role="img" aria-label="Generated preview will appear here">
          <span aria-hidden="true">✦</span><strong>Your result appears here</strong><small>Choose the best saved photo for this wearable</small>
        </div>
        <form id="try-on-form" class="wearable-dock" novalidate>
          <fieldset id="person-photo-selector" class="person-photo-selector" aria-label="Person photo">
            <legend>Use person photo</legend>
            <p>Loading your saved photos…</p>
          </fieldset>
          <div class="wearable-picker">
            <span id="item-thumb" class="wearable-picker__thumb" aria-hidden="true">＋</span>
            <strong>Add wearable</strong>
            <small>Shirt, saree, blouse, necklace, earrings, or a contextual photo where the intended item is visible</small>
            <div class="wearable-source-actions">
              <label class="wearable-source">
                <span aria-hidden="true">↑</span> Upload image
                <input name="item_upload" type="file" accept="image/jpeg,image/png,image/webp" />
              </label>
              <button id="open-camera" class="wearable-source wearable-source--camera" type="button">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4 16 7h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-3z"/><circle cx="12" cy="13" r="3.5"/></svg>
                Take photo
              </button>
            </div>
            <small class="camera-permission-note">Camera permission is controlled and remembered by your browser or device.</small>
          </div>
          <button id="generate-button" class="button button--primary button--full" type="submit"><span aria-hidden="true">✦</span> Generate try-on</button>
        </form>
      </div>
      <p id="tryon-status" class="form-status status-panel" role="status" aria-live="polite"></p>
      <div class="notice" role="note"><strong>Visual preview only.</strong> This is not a fit, size, measurement, material, or purchase guarantee.</div>
    </section>
    <dialog id="photo-picker-dialog" class="photo-picker-dialog" aria-labelledby="photo-picker-title">
      <div class="photo-picker-dialog__panel">
        <header><div><p class="eyebrow">Your photo library</p><h2 id="photo-picker-title">Choose a photo</h2><p>Pick the angle that best matches this wearable.</p></div><button id="close-photo-picker" class="camera-dialog__close" type="button" aria-label="Close photo picker">×</button></header>
        <div id="photo-picker-grid" class="photo-picker-grid"></div>
      </div>
    </dialog>
    <dialog id="camera-dialog" class="camera-dialog" aria-labelledby="camera-title">
      <div class="camera-dialog__panel">
        <header><div><p class="eyebrow">Wearable camera</p><h2 id="camera-title">Take a photo</h2></div><button id="close-camera" class="camera-dialog__close" type="button" aria-label="Close camera">×</button></header>
        <div class="camera-dialog__view"><video id="camera-preview" autoplay muted playsinline aria-label="Live camera preview"></video></div>
        <p id="camera-status" class="camera-dialog__status" role="status" aria-live="polite">Preparing camera…</p>
        <button id="capture-photo" class="button button--primary button--full camera-dialog__capture" type="button" disabled>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/></svg>
          Capture photo
        </button>
      </div>
    </dialog>`;
}

function profileView(auth) {
  const setup = !auth.hasProfile;
  return `
    <header class="mobile-title profile-title">
      <div class="flow-progress" aria-label="Account setup progress"><span>1</span><i class="is-complete"></i><span class="is-active">2</span><i></i><span>3</span></div>
      <p class="eyebrow">${setup ? "Step 2 of 3" : "Personal profile"}</p>
      <h1>${setup ? "Create your profile" : "Update your profile"}</h1>
      <p>Add at least one photo. Use full-body for clothing and close-up for necklaces or earrings; adding both is optional.</p>
    </header>
    <form id="profile-form" class="profile-editor">
      <section class="consumer-card profile-photo-card">
        <div class="profile-photo-grid">
          <div class="profile-photo-slot">
            <div id="full-body-preview" class="person-preview"><span aria-hidden="true">◎</span><strong>${setup ? "Add a full-body photo" : "Loading…"}</strong></div>
            <label class="upload-zone">Full-body photo ${setup ? "(optional if adding close-up)" : "(optional replacement)"}
              <input name="full_body" type="file" accept="image/jpeg,image/png,image/webp" />
              <small>Best for shirts, jeans, sarees, blouses and full outfits</small>
            </label>
            <button class="profile-camera-button" type="button" data-profile-camera="full_body">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4 16 7h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-3z"/><circle cx="12" cy="13" r="3.5"/></svg>
              Take full-body photo
            </button>
          </div>
          <div class="profile-photo-slot">
            <div id="close-up-preview" class="person-preview"><span aria-hidden="true">◇</span><strong>Add a close-up photo</strong></div>
            <label class="upload-zone">Close-up face photo ${setup ? "(optional if adding full-body)" : "(optional replacement)"}
              <input name="close_up" type="file" accept="image/jpeg,image/png,image/webp" />
              <small>Best for necklaces, earrings and face-level accessories</small>
            </label>
            <button class="profile-camera-button" type="button" data-profile-camera="close_up">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4 16 7h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-3z"/><circle cx="12" cy="13" r="3.5"/></svg>
              Take close-up photo
            </button>
          </div>
        </div>
        <div class="profile-library">
          <div class="profile-library__heading">
            <div><strong>Your photo library</strong><small id="profile-photo-count">0 of 10 photos</small></div>
            <div class="profile-library__actions">
              <label class="profile-library__add"><span aria-hidden="true">＋</span> Upload
                <input name="additional_photos" type="file" accept="image/jpeg,image/png,image/webp" multiple />
              </label>
              <button id="capture-additional-photo" class="profile-library__add" type="button" data-profile-camera="additional"><span aria-hidden="true">◎</span> Capture</button>
            </div>
          </div>
          <div id="profile-photo-library" class="profile-library__grid" aria-live="polite"></div>
        </div>
        <p class="field-help">Store up to 10 JPEG, PNG or WebP photos · Maximum 7 MB each. Originals remain private.</p>
        <p class="field-help">Used only as visual guidance, never for sizing or measurements.</p>
      </section>
      <fieldset id="consent-fields" class="consent-card" ${setup ? "" : "hidden"}>
        <legend>Photo consent</legend>
        <label class="check"><input name="adult" type="checkbox" /> I am at least 18 years old.</label>
        <label class="check"><input name="permission" type="checkbox" /> I own or have permission to transform this person’s photo.</label>
        <label class="check"><input name="transform" type="checkbox" /> I agree to AI transformation for virtual try-on.</label>
        <label class="check"><input name="retention" type="checkbox" /> I understand profile and 30-day image retention.</label>
        <label class="check"><input name="training" type="checkbox" /> My images are not authorised for model training.</label>
      </fieldset>
      <button id="save-profile" class="button button--primary button--full" type="submit">${setup ? "Save profile and continue" : "Save profile changes"}</button>
      <p id="profile-status" class="form-status status-panel" role="status" aria-live="polite"></p>
    </form>
    <dialog id="profile-camera-dialog" class="camera-dialog" aria-labelledby="profile-camera-title">
      <div class="camera-dialog__panel">
        <header><div><p class="eyebrow">Profile camera</p><h2 id="profile-camera-title">Take profile photo</h2></div><button id="close-profile-camera" class="camera-dialog__close" type="button" aria-label="Close camera">×</button></header>
        <div class="camera-dialog__view"><video id="profile-camera-preview" autoplay muted playsinline aria-label="Live camera preview"></video></div>
        <p id="profile-camera-status" class="camera-dialog__status" role="status" aria-live="polite">Preparing camera…</p>
        <button id="capture-profile-photo" class="button button--primary button--full camera-dialog__capture" type="button" disabled>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/></svg>
          Capture photo
        </button>
      </div>
    </dialog>
    <section class="mobile-menu account-menu">
      <div><span>◷</span><div><strong>Retention</strong><small>Product and accepted result media: 30 days</small></div></div>
      <div><span>⌾</span><div><strong>Privacy</strong><small>Not authorised for model training</small></div></div>
      <button id="logout" type="button"><span>↗</span><div><strong>Sign out</strong><small>End this session on this device</small></div></button>
      <button id="open-cancellation" class="account-menu__danger" type="button"><span>⌫</span><div><strong>Cancel subscription &amp; delete account</strong><small>Account and photos remain recoverable for 30 days</small></div></button>
    </section>
    <dialog id="cancellation-dialog" class="cancellation-dialog" aria-labelledby="cancellation-title" aria-describedby="cancellation-description">
      <div class="cancellation-dialog__panel">
        <header><div><p class="eyebrow">Account settings</p><h2 id="cancellation-title">Cancel subscription and delete account?</h2></div><button id="close-cancellation" class="camera-dialog__close" type="button" aria-label="Close cancellation confirmation">×</button></header>
        <div id="cancellation-description" class="cancellation-dialog__details">
          <p>This will delete all your profile and try-on photos permanently after 30 days. Do you want to continue?</p>
          <p>Your account remains unchanged unless you explicitly select Yes, Cancel.</p>
        </div>
        <p id="cancellation-status" class="form-status status-panel" role="status" aria-live="polite"></p>
        <div class="cancellation-dialog__actions">
          <button id="keep-subscription" class="button button--quiet" type="button">No, Keep My Account</button>
          <button id="confirm-cancellation" class="button button--danger" type="button">Yes, Cancel</button>
        </div>
      </div>
    </dialog>`;
}

function pendingDeletionView() {
  return `
    <section class="pending-deletion" aria-labelledby="pending-deletion-title">
      <div class="pending-deletion__icon" aria-hidden="true">◷</div>
      <p class="eyebrow">Cancellation confirmed</p>
      <h1 id="pending-deletion-title">Your account is scheduled for deletion</h1>
      <p id="pending-deletion-message" class="lede">Loading your deletion date…</p>
      <div class="notice" role="note">Your profile and try-on photos remain retained until the scheduled deletion date.</div>
      <button id="pending-logout" class="button button--quiet button--full" type="button">Sign out</button>
      <p id="pending-deletion-status" class="form-status status-panel" role="status" aria-live="polite"></p>
    </section>`;
}

function historyView() {
  return `
    <header class="mobile-title"><p class="eyebrow">Your wardrobe</p><h1>Saved looks</h1><p>Accepted previews remain available for up to 30 days.</p></header>
    <section id="queue-panel" class="queue-panel" hidden>
      <div class="queue-panel__heading"><div><p class="eyebrow">Generation activity</p><h2>Queue details</h2></div><span id="queue-count" class="status-chip"></span></div>
      <div id="queue-list" class="queue-list"></div>
    </section>
    <p id="looks-status" class="form-status status-panel" role="status" aria-live="polite">Loading your private previews…</p>
    <section id="looks-gallery" class="looks-gallery" aria-busy="true"></section>`;
}

function setButtonBusy(button, busy, busyLabel, idleLabel) {
  button.disabled = busy;
  button.setAttribute("aria-busy", String(busy));
  if (button.classList.contains("icon-button")) {
    button.setAttribute("aria-label", busy ? busyLabel : idleLabel);
    button.title = busy ? busyLabel : idleLabel;
    return;
  }
  button.textContent = busy ? busyLabel : idleLabel;
}

function setStatus(element, message, tone = "info") {
  element.textContent = message;
  element.dataset.tone = tone;
}

function attachCameraCapture({ dialog, video, cameraStatus, captureButton, closeButton, onCapture }) {
  let stream = null;
  let captureContext = null;
  let requestVersion = 0;

  const stop = () => {
    requestVersion += 1;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    captureButton.disabled = true;
  };

  const open = async (context = null) => {
    captureContext = context;
    if (!dialog.open) dialog.showModal();
    cameraStatus.textContent = "Requesting camera access…";
    stop();
    const currentRequest = requestVersion;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Camera access requires a supported browser opened through HTTPS or localhost.");
      }
      const nextStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      });
      if (currentRequest !== requestVersion || !dialog.open) {
        nextStream.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = nextStream;
      video.srcObject = stream;
      await video.play();
      captureButton.disabled = false;
      cameraStatus.textContent = "Center the subject in the frame, then capture the photo.";
    } catch (error) {
      stop();
      if (error.name === "NotAllowedError") {
        cameraStatus.textContent = "Camera permission was denied. Allow camera access in your browser settings and try again.";
      } else if (error.name === "NotFoundError") {
        cameraStatus.textContent = "No camera was found on this device.";
      } else if (error.name === "NotReadableError") {
        cameraStatus.textContent = "The camera is already being used by another application.";
      } else {
        cameraStatus.textContent = error.message || "The camera could not be started.";
      }
    }
  };

  captureButton.addEventListener("click", async () => {
    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) {
      cameraStatus.textContent = "The camera is not ready yet. Try again in a moment.";
      return;
    }
    captureButton.disabled = true;
    cameraStatus.textContent = "Capturing photo…";
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) {
      captureButton.disabled = false;
      cameraStatus.textContent = "The photo could not be captured. Please try again.";
      return;
    }
    context.drawImage(video, 0, 0, width, height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) {
      captureButton.disabled = false;
      cameraStatus.textContent = "The photo could not be captured. Please try again.";
      return;
    }
    try {
      await onCapture(
        new File([blob], `wearo-camera-${Date.now()}.jpg`, { type: "image/jpeg" }),
        captureContext,
      );
      dialog.close();
    } catch (error) {
      captureButton.disabled = false;
      cameraStatus.textContent = error.message || "The photo could not be saved.";
    }
  });

  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", stop);
  window.addEventListener("pagehide", stop, { once: true });

  return { open, stop };
}

function attachInstallButton() {
  const button = document.querySelector("#install-app");
  if (installPrompt) button?.removeAttribute("hidden");
  button?.addEventListener("click", async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    installPrompt = null;
    button.setAttribute("hidden", "");
  });
}

function attachSignInFlow() {
  const form = document.querySelector("#auth-form");
  const codeStep = document.querySelector("#code-step");
  const requestButton = document.querySelector("#request-code");
  const verifyButton = document.querySelector("#verify-code");
  const status = document.querySelector("#auth-status");
  let challengeId = null;
  let verifying = false;
  const shopContext = readShopContext();
  if (shopContext) {
    const intro = document.querySelector("#consumer-auth-intro");
    intro.textContent = "Use your existing email or mobile number to start this business-sponsored try-on session.";
  }

  requestButton.addEventListener("click", async () => {
    if (form.elements.name && !form.elements.name.reportValidity()) return;
    if (!form.elements.destination.reportValidity()) return;
    const destination = form.elements.destination.value.trim();
    challengeId = null;
    setStatus(status, "Requesting your sign-in code…");
    setButtonBusy(requestButton, true, "Sending…", "Send sign-in code");
    try {
      const result = await api("/auth/email-otp/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination, purpose: "SIGN_IN" }),
      });
      challengeId = result.challenge_id;
      codeStep.hidden = false;
      form.elements.code.required = true;
      setStatus(status, result.message, "success");
      form.elements.code.focus();
    } catch (error) {
      setStatus(status, error.message, "error");
    } finally {
      setButtonBusy(requestButton, false, "Sending…", "Send again");
    }
  });

  verifyButton.addEventListener("click", async () => {
    if (verifying) return;
    if (!challengeId) return setStatus(status, "Press Send sign-in code first.", "error");
    if (!form.elements.code.reportValidity()) return;
    verifying = true;
    setStatus(status, "Checking your code…");
    setButtonBusy(verifyButton, true, "Signing in…", "Continue");
    try {
      const result = await api("/auth/email-otp/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challenge_id: challengeId, code: form.elements.code.value.trim() }),
      });
      const auth = {
        csrfToken: result.csrf_token,
        hasProfile: result.has_person_profile,
        destination: form.elements.destination.value.trim(),
        displayName: form.elements.name?.value.trim() || "",
        identityVersion: AUTH_IDENTITY_VERSION,
        accountStatus: "ACTIVE",
      };
      saveAuth(auth);
      if (shopContext) {
        try {
          await ensureSponsoredSession(auth);
        } catch (error) {
          if (!["TRYONS_PAUSED", "SUBSCRIPTION_CANCELLED"].includes(error.code)) throw error;
        }
      }
      const restorationDate = result.restored_from_deletion_at
        ? new Date(result.restored_from_deletion_at).toLocaleDateString()
        : null;
      setStatus(status, restorationDate
        ? `Account restored. It had been scheduled for permanent deletion on ${restorationDate}.`
        : auth.hasProfile
          ? "Signed in. Opening your fitting room…"
          : "Account ready. Let’s create your profile…", "success");
      const nextLocation = shopContext
        ? window.location.href
        : (auth.hasProfile ? "/app/" : "/app/profile");
      window.setTimeout(() => window.location.assign(nextLocation), restorationDate ? 1200 : 350);
    } catch (error) {
      setStatus(status, error.message, "error");
      verifying = false;
      setButtonBusy(verifyButton, false, "Signing in…", "Continue");
    }
  });
}

async function upload(kind, file, auth) {
  const data = new FormData();
  data.set("kind", kind);
  data.set("image", file);
  return api("/assets", { method: "POST", body: data }, auth);
}

function attachProfileFlow(auth) {
  const form = document.querySelector("#profile-form");
  const fullBodyInput = form.elements.namedItem("full_body");
  const closeUpInput = form.elements.namedItem("close_up");
  const additionalPhotosInput = form.elements.namedItem("additional_photos");
  const consentFields = document.querySelector("#consent-fields");
  const fullBodyPreview = document.querySelector("#full-body-preview");
  const closeUpPreview = document.querySelector("#close-up-preview");
  const submit = document.querySelector("#save-profile");
  const status = document.querySelector("#profile-status");
  const photoLibrary = document.querySelector("#profile-photo-library");
  const photoCount = document.querySelector("#profile-photo-count");
  let existingProfile = null;
  const previewUrls = new Map();
  const selectedProfileFiles = new Map();
  let additionalFiles = [];

  const cancellationDialog = document.querySelector("#cancellation-dialog");
  const cancellationStatus = document.querySelector("#cancellation-status");
  const confirmCancellation = document.querySelector("#confirm-cancellation");
  document.querySelector("#open-cancellation").addEventListener("click", () => {
    cancellationStatus.textContent = "";
    cancellationDialog.showModal();
  });
  const closeCancellation = () => {
    cancellationStatus.textContent = "";
    cancellationDialog.close();
  };
  document.querySelector("#close-cancellation").addEventListener("click", closeCancellation);
  document.querySelector("#keep-subscription").addEventListener("click", closeCancellation);
  cancellationDialog.addEventListener("cancel", () => {
    cancellationStatus.textContent = "";
  });
  confirmCancellation.addEventListener("click", async () => {
    setButtonBusy(
      confirmCancellation,
      true,
      "Cancelling subscription…",
      "Yes, Cancel",
    );
    setStatus(cancellationStatus, "Confirming your cancellation…");
    try {
      const lifecycle = await api("/me/account", { method: "DELETE" }, auth);
      auth.accountStatus = lifecycle.status;
      auth.deletionAt = lifecycle.deletion_at;
      saveAuth(auth);
      setStatus(
        cancellationStatus,
        `Subscription cancelled. Your account is scheduled for deletion on ${new Date(lifecycle.deletion_at).toLocaleDateString()}.`,
        "success",
      );
      window.setTimeout(() => window.location.assign("/app/account-status"), 500);
    } catch (error) {
      setStatus(cancellationStatus, error.message, "error");
      setButtonBusy(
        confirmCancellation,
        false,
        "Cancelling subscription…",
        "Yes, Cancel",
      );
    }
  });

  const setConsentRequired = (required) => {
    consentFields.hidden = !required;
    for (const checkbox of consentFields.querySelectorAll('input[type="checkbox"]')) {
      checkbox.required = required;
    }
  };

  const showPersonImage = (preview, src, label) => {
    preview.innerHTML = `<img src="${src}" alt="${label}" />`;
  };

  const currentImages = () => {
    if (existingProfile?.images?.length) {
      return existingProfile.images.map((image) => ({
        person_asset_id: image.person_asset_id,
        consent_id: image.consent_id,
        photo_type: image.photo_type,
        label: image.label,
        is_primary: image.is_primary,
      }));
    }
    if (!existingProfile?.person_asset_id || !existingProfile?.consent_id) return [];
    return [{
      person_asset_id: existingProfile.person_asset_id,
      consent_id: existingProfile.consent_id,
      photo_type: "FULL_BODY",
      label: "Full body",
      is_primary: true,
    }];
  };

  const renderPhotoLibrary = () => {
    const replacedTypes = new Set([
      selectedProfileFiles.has("full_body") ? "FULL_BODY" : null,
      selectedProfileFiles.has("close_up") ? "CLOSE_UP" : null,
    ].filter(Boolean));
    const saved = currentImages().filter((image) => !replacedTypes.has(image.photo_type));
    const entries = [
      ...saved.map((image) => ({
        src: `${API_BASE}/assets/${encodeURIComponent(image.person_asset_id)}`,
        label: image.label,
        primary: image.is_primary,
      })),
      ...Array.from(selectedProfileFiles.entries()).map(([name]) => ({
        src: previewUrls.get(name),
        label: name === "full_body" ? "New full-body photo" : "New close-up photo",
        pending: true,
      })),
      ...additionalFiles.map((file, index) => ({
        src: previewUrls.get(`additional_${index}`),
        label: `New photo ${index + 1}`,
        pending: true,
      })),
    ];
    photoCount.textContent = `${entries.length} of 10 photos`;
    photoLibrary.innerHTML = entries.length
      ? entries.map((entry) => `<figure class="profile-library__item"><img src="${entry.src}" alt="${escapeHtml(entry.label)}" /><figcaption>${entry.primary ? "Primary" : entry.pending ? "Ready to save" : escapeHtml(entry.label)}</figcaption></figure>`).join("")
      : '<p class="profile-library__empty">Your saved photos will appear here.</p>';
    additionalPhotosInput.disabled = entries.length >= 10;
    document.querySelector("#capture-additional-photo").disabled = entries.length >= 10;
  };

  if (auth.hasProfile) {
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    setStatus(status, "Loading your saved profile…");
    api("/me/person-profile", {}, auth)
      .then((profile) => {
        existingProfile = profile;
        const fullBody = currentImages().find((image) => image.photo_type === "FULL_BODY");
        const closeUp = currentImages().find((image) => image.photo_type === "CLOSE_UP");
        if (fullBody) {
          showPersonImage(
            fullBodyPreview,
            `${API_BASE}/assets/${encodeURIComponent(fullBody.person_asset_id)}`,
            "Your saved full-body profile photo",
          );
        }
        if (closeUp) {
          showPersonImage(
            closeUpPreview,
            `${API_BASE}/assets/${encodeURIComponent(closeUp.person_asset_id)}`,
            "Your saved close-up profile photo",
          );
        }
        renderPhotoLibrary();
        submit.disabled = false;
        submit.setAttribute("aria-busy", "false");
        setStatus(status, "Your profile is ready to update.", "success");
      })
      .catch((error) => {
        if (error.code === "PROFILE_NOT_FOUND") {
          auth.hasProfile = false;
          saveAuth(auth);
          setConsentRequired(true);
          fullBodyPreview.innerHTML = '<span aria-hidden="true">◎</span><strong>Add a full-body photo</strong>';
          submit.disabled = false;
          submit.setAttribute("aria-busy", "false");
          setStatus(status, "Add a photo to finish your profile.");
        } else {
          setStatus(status, error.message, "error");
        }
      });
  } else {
    setConsentRequired(true);
    setStatus(status, "Add your photo and consent to continue.");
    renderPhotoLibrary();
  }

  const selectProfilePhoto = (input, file, preview, label) => {
    if (!file) return;
    selectedProfileFiles.set(input.name, file);
    setConsentRequired(selectedProfileFiles.size > 0 || !existingProfile);
    if (previewUrls.has(input.name)) URL.revokeObjectURL(previewUrls.get(input.name));
    const nextUrl = URL.createObjectURL(file);
    previewUrls.set(input.name, nextUrl);
    showPersonImage(preview, nextUrl, label);
    renderPhotoLibrary();
    setStatus(status, "Photo selected. Review consent, then save your profile.");
  };

  const attachPhotoPreview = (input, preview, label) => {
    input.addEventListener("change", () => {
      selectProfilePhoto(input, input.files?.[0], preview, label);
    });
  };
  attachPhotoPreview(fullBodyInput, fullBodyPreview, "Selected full-body profile photo");
  attachPhotoPreview(closeUpInput, closeUpPreview, "Selected close-up profile photo");

  additionalPhotosInput.addEventListener("change", () => {
    const replacedTypes = new Set([
      selectedProfileFiles.has("full_body") ? "FULL_BODY" : null,
      selectedProfileFiles.has("close_up") ? "CLOSE_UP" : null,
    ].filter(Boolean));
    const savedCount = currentImages().filter((image) => !replacedTypes.has(image.photo_type)).length;
    const available = Math.max(0, 10 - savedCount - selectedProfileFiles.size);
    const chosen = Array.from(additionalPhotosInput.files || []).slice(0, available);
    for (const url of previewUrls.entries()) {
      if (String(url[0]).startsWith("additional_")) URL.revokeObjectURL(url[1]);
    }
    additionalFiles = chosen;
    chosen.forEach((file, index) => previewUrls.set(`additional_${index}`, URL.createObjectURL(file)));
    setConsentRequired(chosen.length > 0 || selectedProfileFiles.size > 0 || !existingProfile);
    renderPhotoLibrary();
    setStatus(
      status,
      chosen.length < (additionalPhotosInput.files?.length || 0)
        ? `You can keep up to 10 photos. The first ${chosen.length} selected photos were added.`
        : `${chosen.length} photo${chosen.length === 1 ? "" : "s"} selected. Review consent, then save.`,
    );
  });

  const profilePhotoTargets = {
    full_body: {
      input: fullBodyInput,
      preview: fullBodyPreview,
      label: "Selected full-body profile photo",
      title: "Take a full-body photo",
    },
    close_up: {
      input: closeUpInput,
      preview: closeUpPreview,
      label: "Selected close-up profile photo",
      title: "Take a close-up photo",
    },
    additional: {
      title: "Capture another profile photo",
    },
  };
  const profileCameraTitle = document.querySelector("#profile-camera-title");
  const profileCamera = attachCameraCapture({
    dialog: document.querySelector("#profile-camera-dialog"),
    video: document.querySelector("#profile-camera-preview"),
    cameraStatus: document.querySelector("#profile-camera-status"),
    captureButton: document.querySelector("#capture-profile-photo"),
    closeButton: document.querySelector("#close-profile-camera"),
    onCapture: (file, photoType) => {
      const target = profilePhotoTargets[photoType];
      if (!target) throw new Error("Choose which profile photo you want to capture.");
      if (photoType === "additional") {
        const replacedTypes = new Set([
          selectedProfileFiles.has("full_body") ? "FULL_BODY" : null,
          selectedProfileFiles.has("close_up") ? "CLOSE_UP" : null,
        ].filter(Boolean));
        const savedCount = currentImages().filter(
          (image) => !replacedTypes.has(image.photo_type),
        ).length;
        if (savedCount + selectedProfileFiles.size + additionalFiles.length >= 10) {
          throw new Error("Your profile can keep up to 10 photos.");
        }
        const index = additionalFiles.length;
        additionalFiles.push(file);
        previewUrls.set(`additional_${index}`, URL.createObjectURL(file));
        setConsentRequired(true);
        renderPhotoLibrary();
        setStatus(status, "Photo captured. Review consent, then save your profile.");
        return;
      }
      target.input.value = "";
      selectProfilePhoto(target.input, file, target.preview, target.label);
    },
  });
  for (const button of document.querySelectorAll("[data-profile-camera]")) {
    button.addEventListener("click", () => {
      const photoType = button.dataset.profileCamera;
      const target = profilePhotoTargets[photoType];
      if (!target) return;
      profileCameraTitle.textContent = target.title;
      profileCamera.open(photoType);
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const fullBodyFile = selectedProfileFiles.get("full_body") || null;
    const closeUpFile = selectedProfileFiles.get("close_up") || null;
    const hasSavedRequiredPhoto = currentImages().some(
      (image) => image.photo_type === "FULL_BODY" || image.photo_type === "CLOSE_UP",
    );
    if (!fullBodyFile && !closeUpFile && !hasSavedRequiredPhoto) {
      setStatus(status, "Upload or take at least one full-body or close-up photo to create your profile.", "error");
      return;
    }
    if (!form.reportValidity()) return;
    setButtonBusy(submit, true, "Saving profile…", auth.hasProfile ? "Save profile changes" : "Save profile and continue");
    const newPhotos = [fullBodyFile, closeUpFile, ...additionalFiles].filter(Boolean);
    setStatus(status, newPhotos.length ? "Uploading your private profile photos…" : "Saving your profile details…");
    try {
      let images = currentImages().map((image) => ({ ...image }));
      const savePhoto = async (file, photoType, label, replaceSameType = true) => {
        if (!file) return;
        const person = await upload("PERSON", file, auth);
        setStatus(status, "Recording your photo consent…");
        const consent = await api(
          "/consents",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              subject_asset_id: person.asset_id,
              adult_confirmed: form.elements.adult.checked,
              depicted_person_permission: form.elements.permission.checked,
              transformation_approved: form.elements.transform.checked,
              retention_notice_acknowledged: form.elements.retention.checked,
              no_training_notice_acknowledged: form.elements.training.checked,
            }),
          },
          auth,
        );
        if (replaceSameType) images = images.filter((image) => image.photo_type !== photoType);
        images.push({
          person_asset_id: person.asset_id,
          consent_id: consent.id,
          photo_type: photoType,
          label,
          is_primary: photoType === "FULL_BODY",
        });
      };
      await savePhoto(fullBodyFile, "FULL_BODY", "Full body");
      await savePhoto(closeUpFile, "CLOSE_UP", "Close-up");
      for (const [index, file] of additionalFiles.entries()) {
        await savePhoto(file, "OTHER", `Photo ${images.length + 1}`, false);
      }
      if (!images.some((image) => image.photo_type === "FULL_BODY" || image.photo_type === "CLOSE_UP")) {
        throw new Error("Choose at least one full-body or close-up photo to create your profile.");
      }
      const primaryImage = images.find((image) => image.photo_type === "FULL_BODY")
        || images.find((image) => image.is_primary)
        || images.find((image) => image.photo_type === "CLOSE_UP");
      const primaryAssetId = primaryImage?.person_asset_id;
      images = images.map((image) => ({
        ...image,
        is_primary: image.person_asset_id === primaryAssetId,
      }));
      await api(
        "/me/person-profile",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            images,
            height_cm: existingProfile?.height_cm ?? null,
            weight_kg: existingProfile?.weight_kg ?? null,
          }),
        },
        auth,
      );
      auth.hasProfile = true;
      saveAuth(auth);
      setStatus(status, "Profile saved. Opening your fitting room…", "success");
      window.setTimeout(
        () => window.location.assign(readShopContext() ? window.location.href : "/app/"),
        450,
      );
    } catch (error) {
      setStatus(status, error.message, "error");
      setButtonBusy(submit, false, "Saving profile…", auth.hasProfile ? "Save profile changes" : "Save profile and continue");
    }
  });

  document.querySelector("#logout")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, "Signing out…", "Sign out");
    try {
      await api("/auth/logout", { method: "POST" }, auth);
    } finally {
      clearAuth();
      window.location.assign("/app/sign-in");
    }
  });
}

function attachHomeFlow(auth) {
  const form = document.querySelector("#try-on-form");
  const itemUploadInput = form.elements.namedItem("item_upload");
  const openCameraButton = document.querySelector("#open-camera");
  const cameraDialog = document.querySelector("#camera-dialog");
  const cameraVideo = document.querySelector("#camera-preview");
  const cameraStatus = document.querySelector("#camera-status");
  const capturePhotoButton = document.querySelector("#capture-photo");
  const closeCameraButton = document.querySelector("#close-camera");
  const itemThumb = document.querySelector("#item-thumb");
  const personPhotoSelector = document.querySelector("#person-photo-selector");
  const photoPickerDialog = document.querySelector("#photo-picker-dialog");
  const photoPickerGrid = document.querySelector("#photo-picker-grid");
  const closePhotoPicker = document.querySelector("#close-photo-picker");
  const preview = document.querySelector("#preview-canvas");
  const submit = document.querySelector("#generate-button");
  const status = document.querySelector("#tryon-status");
  const allowanceCount = document.querySelector("#allowance-count");
  const allowanceCopy = document.querySelector("#allowance-copy");
  const allowanceNote = document.querySelector("#allowance-note");
  const allowanceRefresh = document.querySelector("#refresh-allowance");
  let itemPreviewUrl = null;
  let selectedItemFile = null;
  let generationActive = false;
  let selectedPersonAssetId = null;
  let sponsoredSession = null;
  let businessTryOnsAllowed = true;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const completionAudioContext = AudioContextClass ? new AudioContextClass() : null;
  const fallbackCompletionSound = new Audio(TRY_ON_COMPLETE_SOUND);
  fallbackCompletionSound.preload = "auto";
  const completionSoundBuffer = completionAudioContext
    ? fetch(TRY_ON_COMPLETE_SOUND, { cache: "force-cache" })
      .then((response) => {
        if (!response.ok) throw new Error("Completion sound unavailable.");
        return response.arrayBuffer();
      })
      .then((data) => completionAudioContext.decodeAudioData(data))
      .catch(() => null)
    : Promise.resolve(null);

  const unlockCompletionSound = () => {
    completionAudioContext?.resume().catch(() => {});
  };

  const playCompletionSound = () => {
    completionSoundBuffer.then((buffer) => {
      if (buffer && completionAudioContext) {
        const source = completionAudioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(completionAudioContext.destination);
        source.start(0);
        return;
      }
      fallbackCompletionSound.currentTime = 0;
      fallbackCompletionSound.play().catch(() => {
        // A browser or device sound policy may still prevent playback.
      });
    });
  };

  const setBusinessAvailability = (businessStatus) => {
    businessTryOnsAllowed = businessStatus === "ACTIVE";
    const card = document.querySelector("#sponsored-session-card");
    const studio = document.querySelector(".tryon-studio");
    const allowancePanel = allowanceCount.closest(".allowance-card");
    if (businessTryOnsAllowed) {
      card.hidden = true;
      studio.hidden = false;
      allowancePanel.hidden = false;
      return;
    }
    const businessName = readShopDetails()?.display_name || "This business";
    const message = businessStatus === "PAUSED"
      ? "Try-ons are paused for this business."
      : "This business subscription is cancelled.";
    card.hidden = false;
    card.innerHTML = `<div class="business-tryon-lock"><span aria-hidden="true">⌑</span><div><small>${escapeHtml(businessName)}</small><strong>${message}</strong><p>Your profile, photos, saved data, and previous results remain available in Profile and Looks.</p></div></div><button id="open-personal-tryons" class="button button--primary button--full" type="button">Try on your app</button><p class="business-tryon-lock__note">Continue with your personal Wearo try-ons.</p>`;
    card.querySelector("#open-personal-tryons").addEventListener("click", leaveBusinessExperience);
    studio.hidden = true;
    allowancePanel.hidden = true;
    allowanceCount.textContent = "—";
    allowanceCopy.textContent = "Unavailable";
    allowanceNote.textContent = message;
    submit.disabled = true;
  };

  const refreshSponsoredSession = async () => {
    if (!readShopContext()) return null;
    try {
      sponsoredSession = await ensureSponsoredSession(auth);
    } catch (error) {
      if (error.code === "TRYONS_PAUSED") {
        setBusinessAvailability("PAUSED");
        return null;
      }
      if (error.code === "SUBSCRIPTION_CANCELLED") {
        setBusinessAvailability("CANCELLED");
        return null;
      }
      throw error;
    }
    const card = document.querySelector("#sponsored-session-card");
    const unavailable = sponsoredSession.business_try_on_status !== "ACTIVE";
    setBusinessAvailability(sponsoredSession.business_try_on_status);
    if (unavailable) return sponsoredSession;
    card.hidden = false;
    card.innerHTML = `<strong>${escapeHtml(sponsoredSession.business_name)} sponsored session</strong><div class="sponsored-session-stats"><span><small>Allotted</small><b>${sponsoredSession.try_ons_allotted}</b></span><span><small>Used</small><b>${sponsoredSession.try_ons_used}</b></span><span><small>Available</small><b>${sponsoredSession.try_ons_remaining}</b></span></div><p>Valid for 24 hours from verification.</p>`;
    allowanceCount.textContent = sponsoredSession.try_ons_remaining;
    allowanceCopy.textContent = sponsoredSession.try_ons_remaining;
    allowanceNote.textContent = `Sponsored by ${sponsoredSession.business_name} · Valid until ${new Date(sponsoredSession.expires_at).toLocaleString()}.`;
    submit.disabled = unavailable || sponsoredSession.try_ons_remaining <= 0;
    return sponsoredSession;
  };

  if (readShopContext()) {
    setBusinessAvailability(readShopDetails()?.try_on_status || "ACTIVE");
  }

  const loadProfilePhotos = async () => {
    submit.disabled = true;
    try {
      const profile = await api("/me/person-profile", {}, auth);
      const images = profile.images?.length
        ? profile.images
        : [{
            person_asset_id: profile.person_asset_id,
            photo_type: "FULL_BODY",
            label: "Full body",
            is_primary: true,
          }];
      const selected = images.find((image) => image.is_primary) || images[0];
      selectedPersonAssetId = selected?.person_asset_id || null;
      const photoLabel = (image) => image.label || (image.photo_type === "CLOSE_UP" ? "Close-up" : "Full body");
      const renderSelectedPhoto = () => {
        const current = images.find((image) => image.person_asset_id === selectedPersonAssetId) || images[0];
        const label = escapeHtml(photoLabel(current));
        personPhotoSelector.innerHTML = `<legend>Use person photo</legend><div class="selected-person-photo"><img src="${API_BASE}/assets/${encodeURIComponent(current.person_asset_id)}" alt="${label} profile photo" /><div><small>Selected photo</small><strong>${label}</strong><span>${images.length} saved photo${images.length === 1 ? "" : "s"}</span></div><button id="open-photo-picker" type="button">Choose</button></div>`;
        personPhotoSelector.querySelector("#open-photo-picker").addEventListener("click", () => photoPickerDialog.showModal());
      };
      photoPickerGrid.innerHTML = images.map((image) => {
        const assetId = escapeHtml(image.person_asset_id);
        const label = escapeHtml(photoLabel(image));
        return `<button class="photo-picker-option${image.person_asset_id === selectedPersonAssetId ? " is-selected" : ""}" type="button" data-person-asset-id="${assetId}" aria-pressed="${image.person_asset_id === selectedPersonAssetId}"><img src="${API_BASE}/assets/${encodeURIComponent(image.person_asset_id)}" alt="${label} profile photo" /><span><strong>${label}</strong><small>${image.is_primary ? "Primary photo" : "Tap to select"}</small></span><i aria-hidden="true">✓</i></button>`;
      }).join("");
      photoPickerGrid.querySelectorAll("[data-person-asset-id]").forEach((option) => {
        option.addEventListener("click", () => {
          selectedPersonAssetId = option.dataset.personAssetId;
          photoPickerGrid.querySelectorAll("[data-person-asset-id]").forEach((item) => {
            const active = item.dataset.personAssetId === selectedPersonAssetId;
            item.classList.toggle("is-selected", active);
            item.setAttribute("aria-pressed", String(active));
          });
          renderSelectedPhoto();
          photoPickerDialog.close();
          setStatus(status, "Person photo selected. Add a wearable when ready.", "success");
        });
      });
      renderSelectedPhoto();
      submit.disabled = !businessTryOnsAllowed;
    } catch (error) {
      setStatus(status, error.message, "error");
      if (error.code === "PROFILE_NOT_FOUND") {
        auth.hasProfile = false;
        saveAuth(auth);
        window.location.assign("/app/profile");
      }
    }
  };

  closePhotoPicker.addEventListener("click", () => photoPickerDialog.close());
  photoPickerDialog.addEventListener("click", (event) => {
    if (event.target === photoPickerDialog) photoPickerDialog.close();
  });

  const showGeneratedPreview = (assetId) => {
    if (!assetId) return;
    delete preview.dataset.state;
    delete preview.dataset.partial;
    preview.setAttribute("aria-label", "AI-generated try-on preview");
    preview.innerHTML = `<img src="${API_BASE}/assets/${encodeURIComponent(assetId)}" alt="AI-generated try-on preview" />`;
  };

  const showGeneratingPreview = () => {
    delete preview.dataset.partial;
    preview.dataset.state = "generating";
    preview.setAttribute("aria-label", "Wearo is creating your try-on preview");
    preview.innerHTML = `<div class="tryon-generation" role="status"><div class="tryon-generation__sky" aria-hidden="true"><i class="tryon-generation__twinkle tryon-generation__twinkle--one">✦</i><i class="tryon-generation__twinkle tryon-generation__twinkle--two">✧</i><i class="tryon-generation__twinkle tryon-generation__twinkle--three">✦</i><i class="tryon-generation__twinkle tryon-generation__twinkle--four">✧</i><i class="tryon-generation__twinkle tryon-generation__twinkle--five">✦</i><i class="tryon-generation__twinkle tryon-generation__twinkle--six">✦</i><i class="tryon-generation__twinkle tryon-generation__twinkle--seven">✧</i></div><strong>Creating your Wearo look</strong><small>Fitting your selected wearable to your photo…</small><div class="tryon-generation__progress" aria-hidden="true"><i></i></div></div>`;
  };

  const waitForGeneratingPreviewPaint = () => new Promise((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
  });

  const showGenerationFailure = () => {
    delete preview.dataset.partial;
    preview.dataset.state = "failed";
    preview.setAttribute("aria-label", "Try-on preview could not be created");
    preview.innerHTML = `<span aria-hidden="true">✦</span><strong>Preview not created</strong><small>Review the message below and try again</small>`;
  };

  const loadLatestPreview = async () => {
    try {
      const result = await api("/renders", {}, auth);
      const latest = result.items?.[0];
      if (!generationActive && latest?.result_asset_id) {
        showGeneratedPreview(latest.result_asset_id);
      }
    } catch {
      // Saved-preview restoration must not block the try-on form.
    }
  };

  const refreshAllowance = async () => {
    try {
      if (readShopContext()) {
        await refreshSponsoredSession();
        return true;
      }
      const allowance = await api("/me/daily-allowance", {}, auth);
      allowanceCount.textContent = allowance.unlimited ? "∞" : allowance.remaining;
      allowanceCopy.textContent = allowance.unlimited ? "Unlimited" : allowance.remaining;
      allowanceNote.textContent = allowance.unlimited
        ? `Local testing mode · ${allowance.successful_used} successful try-on${allowance.successful_used === 1 ? "" : "s"}.`
        : `${allowance.successful_used} successful try-on${allowance.successful_used === 1 ? "" : "s"} · Resets at midnight IST.`;
      return true;
    } catch (error) {
      if (error.status === 401) {
        clearAuth();
        window.location.assign("/app/sign-in");
        return false;
      }
      setStatus(status, error.message, "error");
      return false;
    }
  };

  allowanceRefresh.addEventListener("click", async () => {
    allowanceRefresh.disabled = true;
    allowanceRefresh.setAttribute("aria-busy", "true");
    try {
      if (await refreshAllowance()) {
        setStatus(status, "Try-on balance refreshed.", "success");
      }
    } finally {
      allowanceRefresh.disabled = false;
      allowanceRefresh.removeAttribute("aria-busy");
    }
  });

  const waitForRender = async (renderId) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const job = await api(`/renders/${renderId}`, {}, auth);
      if (job.status === "SUCCEEDED") return job;
      if (["FAILED", "CANCELLED"].includes(job.status)) {
        throw new Error(`Generation stopped: ${job.error_code || "UNKNOWN"}.`);
      }
      setStatus(status, `Creating your preview… ${job.status.toLowerCase()}`);
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    throw new Error("Generation is taking longer than expected. Check again shortly.");
  };

  const selectItemFile = (file, sourceLabel) => {
    selectedItemFile = file;
    if (itemPreviewUrl) URL.revokeObjectURL(itemPreviewUrl);
    itemPreviewUrl = URL.createObjectURL(file);
    itemThumb.innerHTML = `<img src="${itemPreviewUrl}" alt="Selected wearable" />`;
    setStatus(status, `${sourceLabel} selected. Press Generate try-on when ready.`, "success");
  };

  itemUploadInput.addEventListener("change", () => {
    const file = itemUploadInput.files?.[0];
    if (file) selectItemFile(file, "Wearable image");
  });

  const itemCamera = attachCameraCapture({
    dialog: cameraDialog,
    video: cameraVideo,
    cameraStatus,
    captureButton: capturePhotoButton,
    closeButton: closeCameraButton,
    onCapture: (file) => {
      itemUploadInput.value = "";
      selectItemFile(file, "Camera photo");
    },
  });
  openCameraButton.addEventListener("click", () => itemCamera.open());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    unlockCompletionSound();
    if (!selectedItemFile) {
      setStatus(status, "Upload or take a wearable photo before generating.", "error");
      itemUploadInput.focus();
      return;
    }
    if (!selectedPersonAssetId) {
      setStatus(status, "Choose a saved person photo before generating.", "error");
      return;
    }
    generationActive = true;
    showGeneratingPreview();
    await waitForGeneratingPreviewPaint();
    setButtonBusy(submit, true, "Uploading wearable…", "Generate try-on");
    setStatus(status, "Uploading your wearable item…");
    try {
      if (readShopContext()) {
        const activeSession = await refreshSponsoredSession();
        if (!businessTryOnsAllowed) {
          throw new Error("This business is not accepting new try-ons.");
        }
        if (!activeSession || activeSession.try_ons_remaining <= 0) {
          throw new Error("No try-ons remain in this 24-hour business session.");
        }
      }
      const item = await upload("PRODUCT", selectedItemFile, auth);
      setButtonBusy(submit, true, "Checking item…", "Generate try-on");
      setStatus(status, "Understanding the uploaded item…");
      const quote = await api(
        "/quotes",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            item_asset_id: item.asset_id,
            person_asset_id: selectedPersonAssetId,
            sponsored_session_id: sponsoredSession?.session_id || null,
          }),
        },
        auth,
      );
      setButtonBusy(submit, true, "Creating preview…", "Generate try-on");
      const generationKey = crypto.randomUUID();
      if (sponsoredSession) {
        sponsoredSession = {
          ...sponsoredSession,
          ...await api(
            `/sponsored-sessions/${encodeURIComponent(sponsoredSession.session_id)}/try-ons`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ request_key: generationKey }),
            },
            auth,
          ),
        };
        saveSponsoredSession(sponsoredSession);
      }
      const job = await api(
        "/renders",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": generationKey },
          body: JSON.stringify({ quote_id: quote.quote_id }),
        },
        auth,
      );
      const result = await waitForRender(job.render_id);
      showGeneratedPreview(result.result_asset_id);
      playCompletionSound();
      setStatus(status, "Your private try-on preview is ready.", "success");
      await refreshAllowance();
    } catch (error) {
      showGenerationFailure();
      setStatus(status, error.message, "error");
    } finally {
      generationActive = false;
      setButtonBusy(submit, false, "Creating preview…", "Generate try-on");
      submit.disabled = !businessTryOnsAllowed;
    }
  });

  loadLatestPreview();
  loadProfilePhotos().then(refreshAllowance);
}

function formatLookDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function formatQueueTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function queueMarkup(items) {
  const labels = {
    QUEUED: ["Queued", "Waiting for the render worker"],
    PROCESSING: ["Processing", "Creating and checking your preview"],
    FAILED: ["Failed", "Generation did not complete"],
    CANCELLED: ["Cancelled", "Generation was cancelled"],
  };
  return items
    .map((item) => {
      const [label, description] = labels[item.status] || [item.status, "Generation update"];
      const error = item.error_code
        ? `<small class="queue-card__error">${escapeHtml(item.error_code)}</small>`
        : "";
      const remove = item.can_cancel
        ? `<button class="queue-card__remove" type="button" data-cancel-render-id="${escapeHtml(item.render_id)}">Remove from queue</button>`
        : "";
      return `
        <article class="queue-card" data-status="${escapeHtml(item.status.toLowerCase())}">
          <span class="queue-card__indicator" aria-hidden="true"></span>
          <div>
            <strong>${escapeHtml(label)}</strong>
            <small>${escapeHtml(description)}</small>
            ${error}
          </div>
          <div class="queue-card__facts">
            <small>${formatQueueTime(item.created_at)}</small>
            <small>${item.attempts} ${item.attempts === 1 ? "attempt" : "attempts"}</small>
            ${remove}
          </div>
        </article>`;
    })
    .join("");
}

function emptyLooksMarkup() {
  return `
    <section class="mobile-empty looks-empty">
      <span aria-hidden="true">✦</span>
      <h2>No looks yet</h2>
      <p>Create a preview from Home. Successful results will appear here automatically.</p>
      <a class="button button--primary" href="/app/">Try on a wearable</a>
    </section>`;
}

function attachHistoryFlow(auth) {
  const gallery = document.querySelector("#looks-gallery");
  const status = document.querySelector("#looks-status");
  const queuePanel = document.querySelector("#queue-panel");
  const queueList = document.querySelector("#queue-list");
  const queueCount = document.querySelector("#queue-count");

  const prepareLookFile = async (assetId, createdAt) => {
    const response = await fetch(`${API_BASE}/assets/${encodeURIComponent(assetId)}`, {
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("The saved look could not be prepared for sharing.");
    const blob = await response.blob();
    const extension = { "image/jpeg": "jpg", "image/webp": "webp" }[blob.type] || "png";
    const date = new Date(createdAt);
    const stamp = Number.isNaN(date.getTime()) ? "saved" : date.toISOString().slice(0, 10);
    return new File([blob], `wearo-look-${stamp}.${extension}`, { type: blob.type });
  };

  const downloadLook = (file) => {
    const downloadUrl = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = file.name;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
  };

  const shareLook = async (assetId, createdAt) => {
    const file = await prepareLookFile(assetId, createdAt);
    const payload = {
      title: "My Wearo look",
      text: "My virtual try-on from Wearo.ai",
      files: [file],
    };
    if (
      typeof navigator.share === "function" &&
      (typeof navigator.canShare !== "function" || navigator.canShare({ files: [file] }))
    ) {
      await navigator.share(payload);
      return "shared";
    }
    downloadLook(file);
    return "downloaded";
  };

  queueList.addEventListener("click", async (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-cancel-render-id]") : null;
    if (!button) return;
    const renderId = button.dataset.cancelRenderId;
    setButtonBusy(button, true, "Removing…", "Remove from queue");
    setStatus(status, "Removing the delayed item from your queue…");
    try {
      await api(`/renders/${encodeURIComponent(renderId)}`, { method: "DELETE" }, auth);
      setStatus(status, "The item was removed from your active queue.", "success");
      await loadLooks();
    } catch (error) {
      setStatus(status, error.message, "error");
      setButtonBusy(button, false, "Removing…", "Remove from queue");
    }
  });

  gallery.addEventListener("click", async (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const downloadButton = target?.closest("[data-download-look]");
    if (downloadButton) {
      setButtonBusy(downloadButton, true, "Preparing…", "Download");
      try {
        const file = await prepareLookFile(
          downloadButton.dataset.assetId,
          downloadButton.dataset.createdAt,
        );
        downloadLook(file);
        setStatus(status, "Saved look downloaded.", "success");
      } catch (error) {
        setStatus(status, error.message, "error");
      } finally {
        setButtonBusy(downloadButton, false, "Preparing…", "Download");
      }
      return;
    }

    const shareButton = target?.closest("[data-share-look]");
    if (shareButton) {
      setButtonBusy(shareButton, true, "Preparing…", "Share");
      try {
        const outcome = await shareLook(
          shareButton.dataset.assetId,
          shareButton.dataset.createdAt,
        );
        setStatus(
          status,
          outcome === "shared"
            ? "The saved look was sent to your device share sheet."
            : "File sharing is unavailable in this browser, so the look was downloaded.",
          "success",
        );
      } catch (error) {
        if (error.name !== "AbortError") setStatus(status, error.message, "error");
      } finally {
        setButtonBusy(shareButton, false, "Preparing…", "Share");
      }
      return;
    }

    const deleteButton = target?.closest("[data-delete-look]");
    if (!deleteButton) return;
    if (!window.confirm("Delete this saved look? It will no longer be available to view or share.")) {
      return;
    }
    setButtonBusy(deleteButton, true, "Deleting…", "Delete");
    setStatus(status, "Deleting the saved look…");
    try {
      await api(
        `/renders/${encodeURIComponent(deleteButton.dataset.renderId)}/result`,
        { method: "DELETE" },
        auth,
      );
      setStatus(status, "Saved look deleted.", "success");
      await loadLooks();
    } catch (error) {
      setStatus(status, error.message, "error");
      setButtonBusy(deleteButton, false, "Deleting…", "Delete");
    }
  });

  const loadLooks = async () => {
    try {
      const result = await api("/renders", {}, auth);
      const activeQueue = result.queue.filter((item) => ["QUEUED", "PROCESSING"].includes(item.status));
      queuePanel.hidden = activeQueue.length === 0;
      queueCount.textContent = activeQueue.length ? `${activeQueue.length} active` : "Recent activity";
      queueList.innerHTML = queueMarkup(activeQueue);
      if (!result.items.length) {
        gallery.innerHTML = emptyLooksMarkup();
        setStatus(status, activeQueue.length ? "Your previews will appear here when ready." : "You have no saved previews yet.");
      } else {
        gallery.innerHTML = result.items
          .map((look) => {
            const assetId = encodeURIComponent(look.result_asset_id);
            const assetUrl = `${API_BASE}/assets/${assetId}`;
            return `
              <article class="look-card">
                <a class="look-card__image" href="${assetUrl}" target="_blank" rel="noopener" aria-label="Open generated preview from ${formatLookDate(look.created_at)}">
                  <img src="${assetUrl}" alt="AI-generated try-on preview" loading="lazy" />
                </a>
                <div class="look-card__meta">
                  <strong>${formatLookDate(look.created_at)}</strong>
                  <small>Available until ${formatLookDate(look.expires_at)}</small>
                  <div class="look-card__actions">
                    <button class="icon-button" type="button" data-download-look data-asset-id="${escapeHtml(look.result_asset_id)}" data-created-at="${escapeHtml(look.created_at)}" aria-label="Download" title="Download"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 5-5-5M5 20h14" /></svg></button>
                    <button class="icon-button" type="button" data-share-look data-asset-id="${escapeHtml(look.result_asset_id)}" data-created-at="${escapeHtml(look.created_at)}" aria-label="Share" title="Share"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.5M8.2 13.2l7.6 4.5" /></svg></button>
                    <button class="icon-button" type="button" data-delete-look data-render-id="${escapeHtml(look.render_id)}" aria-label="Delete" title="Delete"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 3h6l1 4H8l1-4Zm-2 4 1 14h8l1-14M10 11v6m4-6v6" /></svg></button>
                  </div>
                </div>
              </article>`;
          })
          .join("");
        setStatus(status, `${result.items.length} saved ${result.items.length === 1 ? "look" : "looks"}.`, "success");
      }
      if (activeQueue.length) window.setTimeout(loadLooks, 3000);
    } catch (error) {
      if (error.status === 401) {
        clearAuth();
        window.location.assign("/app/sign-in");
        return;
      }
      gallery.innerHTML = `
        <section class="mobile-empty looks-empty">
          <span aria-hidden="true">!</span>
          <h2>Looks unavailable</h2>
          <p>Your previews are still private. Try opening this page again.</p>
        </section>`;
      setStatus(status, error.message, "error");
    } finally {
      gallery.setAttribute("aria-busy", "false");
    }
  };

  loadLooks();
}

function attachPendingDeletionFlow(auth) {
  const message = document.querySelector("#pending-deletion-message");
  const status = document.querySelector("#pending-deletion-status");
  api("/me/account", {}, auth)
    .then((lifecycle) => {
      if (lifecycle.status !== "DELETION_PENDING" || !lifecycle.deletion_at) {
        auth.accountStatus = lifecycle.status;
        delete auth.deletionAt;
        saveAuth(auth);
        window.location.assign("/app/");
        return;
      }
      auth.accountStatus = lifecycle.status;
      auth.deletionAt = lifecycle.deletion_at;
      saveAuth(auth);
      const deletionDate = new Date(lifecycle.deletion_at).toLocaleDateString();
      message.textContent = `Your account is scheduled for permanent deletion on ${deletionDate}. Signing in before this date will restore your account.`;
    })
    .catch((error) => setStatus(status, error.message, "error"));

  document.querySelector("#pending-logout").addEventListener("click", async () => {
    try {
      await api("/auth/logout", { method: "POST" }, auth);
    } finally {
      clearAuth();
      window.location.assign("/app/sign-in");
    }
  });
}

export function renderConsumerApp(root, pathname) {
  document.documentElement.dataset.experience = "consumer";
  captureShopContext(pathname);
  let auth = readAuth();
  const shopContext = readShopContext();
  const shopDetails = readShopDetails();
  if (shopContext && auth && auth.identityVersion !== AUTH_IDENTITY_VERSION) {
    clearAuth();
    auth = null;
  }
  const route = resolvedRoute(pathname, auth);
  const views = {
    "sign-in": () => signInView(shopDetails),
    home: homeView,
    history: historyView,
    profile: () => profileView(auth),
    "account-status": pendingDeletionView,
  };
  const titles = { "sign-in": "Sign in", home: "Try on", history: "Looks", profile: "Profile", "account-status": "Account status" };
  document.title = `${titles[route]} · Wearo`;
  root.innerHTML = consumerFrame(route, views[route](), Boolean(auth), shopDetails);
  attachInstallButton();
  if (route === "sign-in") attachSignInFlow();
  if (route === "profile") attachProfileFlow(auth);
  if (route === "home") attachHomeFlow(auth);
  if (route === "history") attachHistoryFlow(auth);
  if (route === "account-status") attachPendingDeletionFlow(auth);
  if (auth && shopContext && route !== "home") {
    ensureSponsoredSession(auth).catch(() => { /* The home screen will show actionable errors. */ });
  }
  if (shopContext && !shopDetails) {
    loadShopDetails()
      .then(() => renderConsumerApp(root, window.location.pathname))
      .catch((error) => {
        const status = document.querySelector("#auth-status");
        if (status) setStatus(status, error.message, "error");
      });
  }
}

export { consumerRoute };
