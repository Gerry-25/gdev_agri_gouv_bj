import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["packages/**/*.test.ts"],
    environment: "node",
    setupFiles: ["./scripts/vitest.setup.ts"],
  },
});
