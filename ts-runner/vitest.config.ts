import { defineConfig } from "vitest/config";

/**
 * Local vitest config. Present so vitest doesn't walk up the filesystem
 * and pick up an unrelated `vite.config.ts` from a parent directory
 * (e.g. the user's ~/vite.config.ts).
 */
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    globals: false,
  },
});
