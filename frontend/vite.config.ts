import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The dev server is pinned to port 5173 because the backend's default CORS
// allow-list (src/api/config.py) contains http://localhost:5173 and
// http://127.0.0.1:5173. If that port is busy, fail loudly instead of
// silently moving to a port the API would reject.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true },
  preview: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
