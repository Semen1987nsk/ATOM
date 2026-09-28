/**
 * FE-12 (Sprint 5, Batch 8): E2E smoke — login → dashboard.
 *
 * ТРЕБОВАНИЯ для запуска:
 *   1. Backend (FastAPI) поднят на http://localhost:8000.
 *   2. Frontend (Next.js dev) поднят на http://localhost:3000.
 *   3. Seed-юзер test@example.com / testpassword123 в БД.
 *
 * Запуск:
 *   npx playwright test               # headless
 *   npx playwright test --ui          # с UI-отладчиком
 *   PLAYWRIGHT_BASE_URL=https://...   # override baseURL (CI / staging)
 *
 * Тест НЕ запускается автоматически в `npm test` (vitest exclude'ит e2e/).
 * Это инфраструктура для CI и ручного smoke'а — отдельная job в pipeline.
 */
import { test, expect } from '@playwright/test';

test.describe('Login → Dashboard happy-path', () => {
  test('пользователь логинится и попадает на главную', async ({ page }) => {
    await page.goto('/login');

    // Дожидаемся, пока форма реально готова к вводу.
    const emailInput = page.locator('input[name="email"]');
    const passwordInput = page.locator('input[name="password"]');
    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    await emailInput.fill('test@example.com');
    await passwordInput.fill('testpassword123');

    await page.locator('button[type="submit"]').click();

    // После успешного логина AuthContext делает router.push('/').
    await page.waitForURL('**/', { timeout: 15_000 });

    // Дашборд содержит хотя бы один h1/h2 (StatsCard / hero).
    const heading = page.locator('h1, h2').first();
    await expect(heading).toBeVisible({ timeout: 15_000 });
  });

  test('неверные креды → видимая ошибка на /login', async ({ page }) => {
    await page.goto('/login');

    await page.locator('input[name="email"]').fill('test@example.com');
    await page.locator('input[name="password"]').fill('wrong-password');
    await page.locator('button[type="submit"]').click();

    // Сообщение об ошибке (см. login/page.tsx — div c AlertCircle и текстом detail).
    const errorBanner = page.locator('text=Неверный email').or(page.locator('text=Ошибка входа'));
    await expect(errorBanner.first()).toBeVisible({ timeout: 10_000 });

    // Остались на /login, не редиректнулись.
    await expect(page).toHaveURL(/\/login/);
  });
});
