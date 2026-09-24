import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

// package.json sets "type": "module", so Vite loads this config as ESM, where
// the CommonJS directory global is not defined. Derive the path instead.
const rootDir = path.dirname(fileURLToPath(import.meta.url));

// The studio is served by FastAPI from studio/frontend_next at 127.0.0.1:8000.
//
// assetsDir is "static" rather than Vite's default "assets" on purpose.
// studio/backend/app.py mounts /assets -> studio/assets BEFORE it mounts the
// SPA at /, and Starlette resolves mounts in registration order. Emitting the
// bundle into /assets would put every script and stylesheet behind a mount that
// does not contain them, so the page would load and then render nothing.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(rootDir, "./src") },
  },
  build: {
    outDir: path.resolve(rootDir, "../frontend_next"),
    emptyOutDir: true,
    assetsDir: "static",
    // The product claims zero cloud egress. Inlining nothing to a CDN is not
    // enough on its own, so fonts are vendored through @fontsource and bundled
    // here as local woff2 rather than fetched from fonts.gstatic.com.
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
});
