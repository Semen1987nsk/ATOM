import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

// Минимальный конфиг под уже существующие vitest-тесты (filterUtils.test.ts)
// + новые. Алиас @/ зеркалит tsconfig paths; среда node — тесты на чистых
// функциях и fetch-логике, DOM не нужен.
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
});
