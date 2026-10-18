import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

// package.json sets "type": "module", so Vite loads this config as ESM, where
// the CommonJS directory global is not defined. Derive the path instead.
const rootDir = path.dirname(fileURLToPath(import.meta.url));

// The backend `npm run dev` talks to. 8000 is the creator's own studio, so an
// interface session against a throwaway home sets this instead, for example
// INOX_API_TARGET=http://127.0.0.1:8123.
const apiTarget = process.env.INOX_API_TARGET || "http://127.0.0.1:8000";

/**
 * Hands the dev page the studio token before any of its scripts run.
 *
 * The backend issues its token on every non-API response, as an HttpOnly
 * cookie scoped to the host and not the port, so a cookie from the backend is
 * valid for the dev server's page too. The page Vite serves never came from
 * the backend, though, so it starts without one, and the first round of API
 * calls at mount was refused. This copies the backend's Set-Cookie onto the
 * HTML response. Serve only: a build never contains it.
 */
function studioToken(): Plugin {
  return {
    name: "inox-studio-token",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const isPage = req.method === "GET" && (req.url === "/" || req.url?.startsWith("/index.html"));
        if (isPage) {
          try {
            const answer = await fetch(`${apiTarget}/manifest.webmanifest`);
            const cookie = answer.headers.get("set-cookie");
            if (cookie) res.setHeader("Set-Cookie", cookie);
          } catch {
            // The backend is not running. The page loads and says so itself.
          }
        }
        next();
      });
    },
  };
}

// The studio is served by FastAPI from studio/frontend_next at 127.0.0.1:8000.
//
// assetsDir is "static" rather than Vite's default "assets" on purpose.
// studio/backend/app.py mounts /assets -> studio/assets BEFORE it mounts the
// SPA at /, and Starlette resolves mounts in registration order. Emitting the
// bundle into /assets would put every script and stylesheet behind a mount that
// does not contain them, so the page would load and then render nothing.
export default defineConfig({
  plugins: [react(), tailwindcss(), studioToken()],
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
      // changeOrigin stays false: the backend derives the origins it accepts
      // from the Host header's port, so it must see localhost:5173.
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
});
