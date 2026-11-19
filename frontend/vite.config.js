import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// base: "./" garantisce che bundle e scouter_snapshot.json funzionino sia su localhost sia su GitHub Pages (/nome-repo/)
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
