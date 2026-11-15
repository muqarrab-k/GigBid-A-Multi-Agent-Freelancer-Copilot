import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type ProxyOptions } from "vite";

// api paths for the dev proxy
const API = ["/auth", "/jobs", "/runs", "/approvals", "/proposals", "/pipeline", "/messages", "/analytics",
  "/settings", "/status", "/portfolio", "/health", "/test"];

const target = process.env.API_URL ?? "http://localhost:8000";

// page loads stay in the spa
const proxy: ProxyOptions = {
  target,
  changeOrigin: true,
  bypass: (req) => (req.headers.accept?.includes("text/html") ? "/index.html" : undefined),
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: Object.fromEntries(API.map((p) => [p, proxy])) },
});
