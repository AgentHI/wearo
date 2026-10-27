import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import { renderBusinessApp } from "./business-app.js";
import { renderConsumerApp } from "./consumer-app.js";
import { renderAgentApp } from "./agent-app.js";
import { renderAdminApp } from "./admin-app.js";
import "./styles.css";

function currentExperience(pathname) {
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/agent")) return "agent";
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

if (experience === "admin") {
  renderAdminApp(root, window.location.pathname);
} else if (experience === "agent") {
  renderAgentApp(root);
} else if (experience === "business") {
  renderBusinessApp(root, window.location.pathname);
} else {
  showConsumerSplash();
  renderConsumerApp(root, window.location.pathname);
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
      updateViaCache: "none",
    });
    await registration.update();
  });
}

export { currentExperience, showConsumerSplash };
