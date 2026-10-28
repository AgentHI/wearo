import { defineConfig } from "vite";

export default defineConfig({
  // The monorepo keeps shared local configuration in its root .env file.
  envDir: "../../",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
