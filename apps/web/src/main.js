import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import { renderBusinessApp } from "./business-app.js";
import { renderConsumerApp } from "./consumer-app.js";
import "./styles.css";

function currentExperience(pathname) {
  return pathname.startsWith("/business") ? "business" : "consumer";
}

const root = document.querySelector("#app");
const experience = currentExperience(window.location.pathname);

if (experience === "business") {
  renderBusinessApp(root, window.location.pathname);
} else {
  renderConsumerApp(root, window.location.pathname);
  if ("serviceWorker" in navigator && import.meta.env.PROD) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/app/" });
    });
  }
}

export { currentExperience };
