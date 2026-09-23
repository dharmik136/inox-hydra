import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Vendored faces. These resolve to woff2 files inside node_modules, which Vite
// emits into the bundle directory, so the running product never reaches
// fonts.gstatic.com. Variable axes are used so one file covers every weight
// the blueprint asks for (400 to 700) instead of four static files per family.
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";

import "./styles/index.css";
import App from "./App";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root is missing from index.html");
}

// Registered purely for installability. studio/ui/public/sw.js caches
// nothing on purpose: a cache in front of a server on this same machine
// hides no latency and adds a way to serve a stale bundle after an update.
// Failure is swallowed because the studio works without it.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
