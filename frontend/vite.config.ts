/// <reference types="vitest" />
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "**/*.test.{ts,tsx}",
        "src/types/**",
        "src/main.tsx",
        "src/vite-env.d.ts",
      ],
      thresholds: {
        lines: 48,
        statements: 48,
        functions: 48,
        branches: 42,
        "src/api/**": {
          lines: 85,
          statements: 85,
          functions: 85,
          branches: 75,
        },
        "src/hooks/**": {
          lines: 85,
          statements: 85,
          functions: 85,
          branches: 75,
        },
        "src/state/**": {
          lines: 90,
          statements: 90,
          functions: 90,
          branches: 80,
        },
        "src/components/**": {
          lines: 60,
          statements: 60,
          functions: 55,
          branches: 50,
        },
        "src/pages/**": {
          lines: 50,
          statements: 50,
          functions: 50,
          branches: 45,
        },
      },
    },
  },
});
