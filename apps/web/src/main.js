import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import { renderBusinessApp } from "./business-app.js";
import { renderConsumerApp } from "./consumer-app.js";
import "./styles.css";

function currentExperience(pathname) {
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
      <div class="launch-splash__logo"><img src="/wearo-brand.png" alt="Wearo.ai" /></div>
      <p>Private AI-powered virtual try-on</p>
    </div>`;
  document.body.append(splash);
  window.setTimeout(() => splash.classList.add("is-exiting"), 2600);
  window.setTimeout(() => splash.remove(), 3000);
}

const root = document.querySelector("#app");
const experience = currentExperience(window.location.pathname);

if (experience === "business") {
  renderBusinessApp(root, window.location.pathname);
} else {
  showConsumerSplash();
  renderConsumerApp(root, window.location.pathname);
  if ("serviceWorker" in navigator && import.meta.env.PROD) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/app/" });
    });
  }
}

export { currentExperience, showConsumerSplash };
