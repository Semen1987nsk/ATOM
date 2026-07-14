import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

// FE-12 (Sprint 5, Batch 8): jsdom включён для component-тестов через
// @testing-library/react. setupFiles подгружает jest-dom матчеры
// (toBeInTheDocument и пр.). globals: true даёт describe/it/expect без import
// в каждом файле — единый стиль с RTL/Jest community-tooling.
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    globals: true,
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    // E2E (Playwright) живёт в frontend/e2e/ и НЕ должен попадать в vitest
    // (другой runner, другие конвенции).
    exclude: ['node_modules', 'dist', '.next', 'e2e/**'],
  },
});
