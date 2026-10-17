import { compactBrandMarkup } from "./brand.js";

const API_BASE = "/api/v1";
const AUTH_KEY = "wearo_consumer_auth";

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
  if (pathname.startsWith("/app/history")) return "history";
  if (pathname.startsWith("/app/profile")) return "profile";
  if (pathname === "/shop" || pathname.startsWith("/app/try-on")) return "home";
  return "home";
}

function resolvedRoute(pathname, auth) {
  let route = consumerRoute(pathname);
  if (!auth && route !== "sign-in") route = "sign-in";
  if (auth && route === "sign-in") route = auth.hasProfile ? "home" : "profile";
  if (auth && !auth.hasProfile && route !== "profile") route = "profile";
  const expectedPath = {
    "sign-in": "/app/sign-in",
    home: "/app/",
    history: "/app/history",
    profile: "/app/profile",
  }[route];
  if (window.location.pathname !== expectedPath) window.history.replaceState({}, "", expectedPath);
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
  const body = response.status === 204 ? {} : await response.json();
  if (!response.ok) {
    const error = new Error(body.message || "The request could not be completed.");
    error.code = body.code;
    error.status = response.status;
    throw error;
  }
  return body;
}

function consumerFrame(route, content, authenticated) {
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
    <div class="consumer-app consumer-app--${route}">
      <header class="consumer-header">
        ${compactBrandMarkup(authenticated ? "/app/" : "/app/sign-in")}
        <div class="consumer-header__actions">
          <button id="install-app" class="icon-button install-button" type="button" hidden aria-label="Install Wearo app">↓</button>
          ${authenticated ? '<a class="avatar-button" href="/app/profile" aria-label="Open profile">M</a>' : '<a class="business-switch" href="/business">For business</a>'}
        </div>
      </header>
      <main id="main" class="consumer-main consumer-main--${route}">${content}</main>
      ${authenticated ? `<nav class="bottom-nav" aria-label="Consumer app">${nav}</nav>` : ""}
    </div>`;
}

function signInView() {
  return `
    <section class="consumer-auth">
      <div class="flow-progress" aria-label="Account setup progress"><span class="is-active">1</span><i></i><span>2</span><i></i><span>3</span></div>
      <p class="eyebrow">Step 1 of 3</p>
      <h1>Sign up or sign in</h1>
      <p class="lede">Use your email or mobile number. New accounts are created automatically.</p>
      <form id="auth-form" class="consumer-card">
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
      <div><p class="eyebrow">Your private fitting room</p><h1>Try it on</h1><p>Upload a wearable and see it with your saved person profile.</p></div>
      <a class="profile-shortcut" href="/app/profile"><span>○</span> Edit profile</a>
    </header>
    <section class="allowance-card" aria-label="Daily allowance"><div><span id="allowance-count" class="allowance-ring">—</span><div><strong><span id="allowance-copy">Loading</span> previews available</strong><p id="allowance-note">Resets at midnight IST.</p></div></div><span>Today</span></section>
    <section class="tryon-studio" aria-labelledby="tryon-title">
      <div class="tryon-studio__heading"><div><p class="eyebrow">Wearable item</p><h2 id="tryon-title">Choose what you want to wear</h2></div><span>Apparel + jewellery</span></div>
      <div class="tryon-workspace">
        <div id="preview-canvas" class="mobile-preview__canvas" role="img" aria-label="Generated preview will appear here">
          <span aria-hidden="true">✦</span><strong>Your result appears here</strong><small>Your saved profile is used automatically</small>
        </div>
        <form id="try-on-form" class="wearable-dock" novalidate>
          <label class="wearable-picker">
            <span id="item-thumb" class="wearable-picker__thumb" aria-hidden="true">＋</span>
            <strong>Add wearable</strong>
            <small>Shirt, saree, blouse, necklace, earrings, or any clear item photo</small>
            <input name="item" type="file" accept="image/jpeg,image/png,image/webp" required />
          </label>
          <button id="generate-button" class="button button--primary button--full" type="submit"><span aria-hidden="true">✦</span> Generate try-on</button>
        </form>
      </div>
      <p id="tryon-status" class="form-status status-panel" role="status" aria-live="polite"></p>
      <div class="notice" role="note"><strong>Visual preview only.</strong> This is not a fit, size, measurement, material, or purchase guarantee.</div>
    </section>`;
}

function profileView(auth) {
  const setup = !auth.hasProfile;
  return `
    <header class="mobile-title profile-title">
      <div class="flow-progress" aria-label="Account setup progress"><span>1</span><i class="is-complete"></i><span class="is-active">2</span><i></i><span>3</span></div>
      <p class="eyebrow">${setup ? "Step 2 of 3" : "Personal profile"}</p>
      <h1>${setup ? "Create your profile" : "Update your profile"}</h1>
      <p>Use one clear full-body photo. This profile is reused for every try-on.</p>
    </header>
    <form id="profile-form" class="profile-editor">
      <section class="consumer-card profile-photo-card">
        <div id="person-preview" class="person-preview"><span aria-hidden="true">◎</span><strong>${setup ? "Add your photo" : "Loading profile…"}</strong></div>
        <label class="upload-zone">${setup ? "Full-body person photo" : "Replace person photo (optional)"}
          <input name="person" type="file" accept="image/jpeg,image/png,image/webp" ${setup ? "required" : ""} />
          <small>Face and full body visible · JPEG, PNG or WebP · Maximum 7 MB</small>
        </label>
        <div class="field-row"><label>Height <span>Optional, cm</span><input name="height" type="number" min="80" max="260" inputmode="decimal" /></label><label>Weight <span>Optional, kg</span><input name="weight" type="number" min="20" max="350" inputmode="decimal" /></label></div>
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
      ${setup ? "" : '<button id="delete-profile" class="text-button" type="button">Delete saved profile</button>'}
    </form>
    <section class="mobile-menu account-menu">
      <div><span>◷</span><div><strong>Retention</strong><small>Product and accepted result media: 30 days</small></div></div>
      <div><span>⌾</span><div><strong>Privacy</strong><small>Not authorised for model training</small></div></div>
      <button id="logout" type="button"><span>↗</span><div><strong>Sign out</strong><small>End this session on this device</small></div></button>
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
  button.textContent = busy ? busyLabel : idleLabel;
}

function setStatus(element, message, tone = "info") {
  element.textContent = message;
  element.dataset.tone = tone;
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

  requestButton.addEventListener("click", async () => {
    if (!form.elements.destination.reportValidity()) return;
    challengeId = null;
    setStatus(status, "Requesting your sign-in code…");
    setButtonBusy(requestButton, true, "Sending…", "Send sign-in code");
    try {
      const result = await api("/auth/email-otp/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination: form.elements.destination.value, purpose: "SIGN_IN" }),
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
      };
      saveAuth(auth);
      setStatus(
        status,
        auth.hasProfile ? "Signed in. Opening your fitting room…" : "Account ready. Let’s create your profile…",
        "success",
      );
      window.setTimeout(() => window.location.assign(auth.hasProfile ? "/app/" : "/app/profile"), 350);
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
  const personInput = form.elements.person;
  const consentFields = document.querySelector("#consent-fields");
  const preview = document.querySelector("#person-preview");
  const submit = document.querySelector("#save-profile");
  const status = document.querySelector("#profile-status");
  let existingProfile = null;
  let previewUrl = null;

  const setConsentRequired = (required) => {
    consentFields.hidden = !required;
    for (const checkbox of consentFields.querySelectorAll('input[type="checkbox"]')) {
      checkbox.required = required;
    }
  };

  const showPersonImage = (src) => {
    preview.innerHTML = `<img src="${src}" alt="Your saved person profile" />`;
  };

  if (auth.hasProfile) {
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    setStatus(status, "Loading your saved profile…");
    api("/me/person-profile", {}, auth)
      .then((profile) => {
        existingProfile = profile;
        form.elements.height.value = profile.height_cm ?? "";
        form.elements.weight.value = profile.weight_kg ?? "";
        showPersonImage(`${API_BASE}/assets/${profile.person_asset_id}`);
        submit.disabled = false;
        submit.setAttribute("aria-busy", "false");
        setStatus(status, "Your profile is ready to update.", "success");
      })
      .catch((error) => {
        if (error.code === "PROFILE_NOT_FOUND") {
          auth.hasProfile = false;
          saveAuth(auth);
          personInput.required = true;
          setConsentRequired(true);
          preview.innerHTML = '<span aria-hidden="true">◎</span><strong>Add your photo</strong>';
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
  }

  personInput.addEventListener("change", () => {
    const file = personInput.files[0];
    setConsentRequired(Boolean(file) || !existingProfile);
    if (!file) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    showPersonImage(previewUrl);
    setStatus(status, "Photo selected. Review consent, then save your profile.");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    setButtonBusy(submit, true, "Saving profile…", auth.hasProfile ? "Save profile changes" : "Save profile and continue");
    setStatus(status, personInput.files[0] ? "Uploading your private profile photo…" : "Saving your profile details…");
    try {
      let personAssetId = existingProfile?.person_asset_id;
      let consentId = existingProfile?.consent_id;
      if (personInput.files[0]) {
        const person = await upload("PERSON", personInput.files[0], auth);
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
        personAssetId = person.asset_id;
        consentId = consent.id;
      }
      if (!personAssetId || !consentId) throw new Error("Choose a full-body photo to create your profile.");
      await api(
        "/me/person-profile",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            person_asset_id: personAssetId,
            consent_id: consentId,
            height_cm: form.elements.height.value ? Number(form.elements.height.value) : null,
            weight_kg: form.elements.weight.value ? Number(form.elements.weight.value) : null,
          }),
        },
        auth,
      );
      auth.hasProfile = true;
      saveAuth(auth);
      setStatus(status, "Profile saved. Opening your fitting room…", "success");
      window.setTimeout(() => window.location.assign("/app/"), 450);
    } catch (error) {
      setStatus(status, error.message, "error");
      setButtonBusy(submit, false, "Saving profile…", auth.hasProfile ? "Save profile changes" : "Save profile and continue");
    }
  });

  document.querySelector("#delete-profile")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, "Deleting…", "Delete saved profile");
    setStatus(status, "Revoking profile access…");
    try {
      await api("/me/person-profile", { method: "DELETE" }, auth);
      auth.hasProfile = false;
      saveAuth(auth);
      setStatus(status, "Profile deleted. Add a new photo to continue.", "success");
      window.setTimeout(() => window.location.reload(), 350);
    } catch (error) {
      setStatus(status, error.message, "error");
      setButtonBusy(button, false, "Deleting…", "Delete saved profile");
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
  const itemInput = form.elements.namedItem("item");
  const itemThumb = document.querySelector("#item-thumb");
  const preview = document.querySelector("#preview-canvas");
  const submit = document.querySelector("#generate-button");
  const status = document.querySelector("#tryon-status");
  const allowanceCount = document.querySelector("#allowance-count");
  const allowanceCopy = document.querySelector("#allowance-copy");
  const allowanceNote = document.querySelector("#allowance-note");
  let itemPreviewUrl = null;
  let generationActive = false;

  const showGeneratedPreview = (assetId) => {
    if (!assetId) return;
    preview.innerHTML = `<img src="${API_BASE}/assets/${encodeURIComponent(assetId)}" alt="AI-generated try-on preview" />`;
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
      const allowance = await api("/me/daily-allowance", {}, auth);
      allowanceCount.textContent = allowance.unlimited ? "∞" : allowance.remaining;
      allowanceCopy.textContent = allowance.unlimited ? "Unlimited" : allowance.remaining;
      allowanceNote.textContent = allowance.unlimited
        ? "Local testing mode. Provider usage may still incur charges."
        : "Resets at midnight IST.";
    } catch (error) {
      if (error.status === 401) {
        clearAuth();
        window.location.assign("/app/sign-in");
        return;
      }
      setStatus(status, error.message, "error");
    }
  };

  const waitForRender = async (renderId, onStatusChange) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const job = await api(`/renders/${renderId}`, {}, auth);
      onStatusChange?.(job.status);
      if (job.status === "SUCCEEDED") return job;
      if (["FAILED", "CANCELLED"].includes(job.status)) {
        throw new Error(`Generation stopped: ${job.error_code || "UNKNOWN"}.`);
      }
      setStatus(status, `Creating your preview… ${job.status.toLowerCase()}`);
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    throw new Error("Generation is taking longer than expected. Check again shortly.");
  };

  const watchProgressivePreview = (renderId) => {
    let stopped = false;
    let etag = null;
    let previewUrl = null;
    let activeRequest = null;
    let wake = null;
    const done = (async () => {
      while (!stopped) {
        try {
          const headers = etag ? { "If-None-Match": etag } : {};
          activeRequest = new AbortController();
          const response = await fetch(
            `${API_BASE}/renders/${encodeURIComponent(renderId)}/preview`,
            { credentials: "same-origin", headers, signal: activeRequest.signal },
          );
          if (response.status === 200) {
            const nextUrl = URL.createObjectURL(await response.blob());
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            previewUrl = nextUrl;
            etag = response.headers.get("ETag");
            preview.dataset.partial = "true";
            preview.innerHTML = `<img src="${nextUrl}" alt="Partial virtual try-on preview, still processing" />`;
            setStatus(status, "A partial preview is ready. Refining the final image…");
          } else if (response.status === 401) {
            stopped = true;
          }
        } catch {
          // A transient preview fetch must not start another generation request.
        } finally {
          activeRequest = null;
        }
        if (!stopped) {
          await new Promise((resolve) => {
            const timer = window.setTimeout(resolve, 2000);
            wake = () => {
              window.clearTimeout(timer);
              resolve();
            };
          });
          wake = null;
        }
      }
    })();
    return {
      async stop() {
        stopped = true;
        activeRequest?.abort();
        wake?.();
        await done;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        delete preview.dataset.partial;
      },
    };
  };

  itemInput.addEventListener("change", () => {
    const file = itemInput.files[0];
    if (!file) return;
    if (itemPreviewUrl) URL.revokeObjectURL(itemPreviewUrl);
    itemPreviewUrl = URL.createObjectURL(file);
    itemThumb.innerHTML = `<img src="${itemPreviewUrl}" alt="" />`;
    setStatus(status, `${file.name} selected. Press Generate try-on when ready.`, "success");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!itemInput.files?.[0]) {
      setStatus(status, "Choose a wearable photo before generating.", "error");
      itemInput.focus();
      return;
    }
    generationActive = true;
    setButtonBusy(submit, true, "Uploading wearable…", "Generate try-on");
    setStatus(status, "Uploading your wearable item…");
    try {
      const item = await upload("PRODUCT", itemInput.files[0], auth);
      setButtonBusy(submit, true, "Checking item…", "Generate try-on");
      setStatus(status, "Understanding the uploaded item…");
      const quote = await api(
        "/quotes",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_asset_id: item.asset_id }) },
        auth,
      );
      setButtonBusy(submit, true, "Creating preview…", "Generate try-on");
      const job = await api(
        "/renders",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({ quote_id: quote.quote_id }),
        },
        auth,
      );
      let progressive = null;
      let result;
      try {
        result = await waitForRender(job.render_id, (jobStatus) => {
          if (jobStatus === "PROCESSING" && !progressive) {
            progressive = watchProgressivePreview(job.render_id);
          }
        });
      } finally {
        await progressive?.stop();
      }
      showGeneratedPreview(result.result_asset_id);
      setStatus(status, "Your private try-on preview is ready.", "success");
      await refreshAllowance();
    } catch (error) {
      setStatus(status, error.message, "error");
    } finally {
      generationActive = false;
      setButtonBusy(submit, false, "Creating preview…", "Generate try-on");
    }
  });

  refreshAllowance();
  loadLatestPreview();
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

export function renderConsumerApp(root, pathname) {
  document.documentElement.dataset.experience = "consumer";
  const auth = readAuth();
  const route = resolvedRoute(pathname, auth);
  const views = {
    "sign-in": signInView,
    home: homeView,
    history: historyView,
    profile: () => profileView(auth),
  };
  const titles = { "sign-in": "Sign in", home: "Try on", history: "Looks", profile: "Profile" };
  document.title = `${titles[route]} · Wearo`;
  root.innerHTML = consumerFrame(route, views[route](), Boolean(auth));
  attachInstallButton();
  if (route === "sign-in") attachSignInFlow();
  if (route === "profile") attachProfileFlow(auth);
  if (route === "home") attachHomeFlow(auth);
  if (route === "history") attachHistoryFlow(auth);
}

export { consumerRoute };
