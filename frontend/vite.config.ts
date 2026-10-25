import { defineConfig } from "vite";
export default defineConfig({
  server: {
    allowedHosts: ["terminal.local"],
    proxy: {
      "/api": "http://127.0.0.1:9393",
      "/downloads": "http://127.0.0.1:9393",
      "/media": "http://127.0.0.1:9393",
    },
  },
});
