import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the FastAPI service so the SPA and API share an origin
// (matches production behind Traefik). Override the target with VITE_API_TARGET.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on all interfaces (so a tunnel can reach it)
    // Vite 6 blocks unknown Host headers; allow Cloudflare quick-tunnel hosts.
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
