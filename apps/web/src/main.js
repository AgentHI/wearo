import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import { renderBusinessApp } from "./business-app.js";
import { renderConsumerApp } from "./consumer-app.js";
import { renderAgentApp } from "./agent-app.js";
import { renderStoreApp } from "./store-app.js";
import { renderAdminApp } from "./admin-app.js";
import { renderCostLab } from "../../../packages/cost-lab-ui/src/index.js";
import { renderAboutSite, renderContactSite, renderExperiencesSite, renderForBusinessSite, renderPublicSite } from "./public-site.js";
import "./styles.css";

// Keep consumer payment activity isolated from the administration workspace. This also
// neutralizes obsolete checkout timers that can survive Vite hot-module replacement.
const ORIGINAL_FETCH_KEY = "__wearoOriginalFetch";
const originalFetch = window[ORIGINAL_FETCH_KEY] || window.fetch.bind(window);
window[ORIGINAL_FETCH_KEY] = originalFetch;
window.fetch = (input, options = {}) => {
  const request = input instanceof Request ? input : null;
  const method = String(options.method || request?.method || "GET").toUpperCase();
  const url = new URL(request?.url || String(input), window.location.origin);
  const isConsumerOrderStatus = /^\/api\/v1\/me\/topup-orders\/[^/]+$/.test(url.pathname);
  if (/^\/admin(?:\/|$)/.test(window.location.pathname) && method === "GET" && isConsumerOrderStatus) {
    return Promise.reject(new DOMException("Consumer payment watcher stopped on admin route.", "AbortError"));
  }
  return originalFetch(input, options);
};

function currentExperience(pathname) {
  if (pathname === "/" || pathname === "/index.html") return "public";
  if (pathname === "/experiences" || pathname === "/experiences/") return "experiences";
  if (pathname === "/for-business" || pathname === "/for-business/") return "for-business";
  if (pathname === "/about" || pathname === "/about/") return "about";
  if (pathname === "/contact" || pathname === "/contact/") return "contact";
  if (pathname.startsWith("/admin/cost-lab")) return "cost-lab";
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/agent")) return "agent";
  if (pathname.startsWith("/store")) return "store";
  return pathname.startsWith("/business") ? "business" : "consumer";
}

function showConsumerSplash() {
  const key = "wearo_consumer_splash_seen";
  try {
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "true");
  } catch {
    // Storage restrictions should not prevent the visual launch experience.
  }
  const splash = document.createElement("div");
  splash.className = "launch-splash";
  splash.setAttribute("role", "status");
  splash.setAttribute("aria-label", "Wearo.ai, private AI-powered virtual try-on");
  splash.innerHTML = `
    <div class="launch-splash__glow" aria-hidden="true"></div>
    <div class="launch-splash__content">
      <div class="launch-splash__logo"><img src="/wearo-mark.png?v=20261118-pwa-2" alt="Wearo.ai" /></div>
      <p>Private AI-powered virtual try-on</p>
    </div>`;
  document.body.append(splash);
  window.setTimeout(() => splash.classList.add("is-exiting"), 2600);
  window.setTimeout(() => splash.remove(), 3000);
}

const root = document.querySelector("#app");

function renderCurrentRoute() {
  const experience = currentExperience(window.location.pathname);
  if (experience === "public") renderPublicSite(root);
  else if (experience === "about") renderAboutSite(root);
  else if (experience === "experiences") renderExperiencesSite(root);
  else if (experience === "for-business") renderForBusinessSite(root);
  else if (experience === "contact") renderContactSite(root);
  else if (experience === "cost-lab") renderCostLab(root, window.location.pathname);
  else if (experience === "admin") renderAdminApp(root, window.location.pathname);
  else if (experience === "agent") renderAgentApp(root);
  else if (experience === "store") renderStoreApp(root, window.location.pathname);
  else if (experience === "business") renderBusinessApp(root, window.location.pathname);
  else {
    showConsumerSplash();
    renderConsumerApp(root, window.location.pathname);
  }
  window.scrollTo(0, 0);
}

renderCurrentRoute();
window.addEventListener("popstate", renderCurrentRoute);

if ("serviceWorker" in navigator && import.meta.env.DEV) {
  window.addEventListener("load", async () => {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
    if ("caches" in window) {
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames
          .filter((cacheName) => cacheName.startsWith("wearo-shell-"))
          .map((cacheName) => caches.delete(cacheName)),
      );
    }
  });
} else if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
      updateViaCache: "none",
    });
    await registration.update();
  });
}

export { currentExperience, showConsumerSplash };
