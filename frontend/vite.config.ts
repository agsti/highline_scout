import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

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
      "/countries": "http://127.0.0.1:8000",
      "/regions": "http://127.0.0.1:8000",
      "/zones": "http://127.0.0.1:8000",
      "/density": "http://127.0.0.1:8000",
      "/anchors": "http://127.0.0.1:8000",
      "/restrictions": "http://127.0.0.1:8000",
    },
  },
});
