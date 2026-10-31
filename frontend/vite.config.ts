import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // `pnpm dev` proxies the API so the browser stays same-origin, exactly as nginx does in Docker.
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
  build: { sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
