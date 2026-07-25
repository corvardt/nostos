import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxying keeps the UI same-origin in dev, so CORS never enters the picture.
    // The prefix is not rewritten away: the backend serves the API under /api
    // too, so `BASE` in lib/api.ts is the same string here and once installed.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
