import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: the app calls /api/* and Vite forwards to the FastAPI service,
// so no CORS dance is needed during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
