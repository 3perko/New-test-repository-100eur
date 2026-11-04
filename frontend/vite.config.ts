import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
});
