import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiOrigin = process.env.HIGHLINER_API_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/countries": apiOrigin,
      "/regions": apiOrigin,
      "/zones": apiOrigin,
      "/density": apiOrigin,
      "/anchors": apiOrigin,
      "/restrictions": apiOrigin,
    },
  },
});
