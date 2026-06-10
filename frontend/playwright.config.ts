import { defineConfig, devices } from '@playwright/test';

/**
 * FE-12 (Sprint 5, Batch 8): Playwright config для E2E smoke-тестов.
 *
 * Запуск локально:
 *   1. Поднять backend (FastAPI) на :8000 с seed-юзером test@example.com.
 *   2. Поднять frontend (npm run dev) на :3000.
 *   3. `npx playwright test` (или с --ui).
 *
 * В CI baseURL переопределяется через PLAYWRIGHT_BASE_URL; retries=2 чтобы
 * случайные сетевые флэки не валили pipeline.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
