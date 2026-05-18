import { test, expect } from "@playwright/test";

test.describe("Landing — visual regression @visual", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    await page.addStyleTag({ content: `[aria-label="live"] { animation: none !important; }` });
  });

  test("Hero — desktop 1440", async ({ page }) => {
    await expect(page.locator("section").nth(1)).toHaveScreenshot("hero-1440.png", { maxDiffPixels: 100 });
  });

  test("MAE/MFE section — desktop 1440", async ({ page }) => {
    const section = page.locator("section", { has: page.getByText("Раздел 02 · MAE / MFE") });
    await expect(section).toHaveScreenshot("mae-mfe-1440.png", { maxDiffPixels: 100 });
  });

  test("Trade Replay section — desktop 1440", async ({ page }) => {
    const section = page.locator("section", { has: page.getByText("Раздел 03 · Trade Replay") });
    await expect(section).toHaveScreenshot("replay-1440.png", { maxDiffPixels: 100 });
  });

  test("МААТТ origin section — desktop 1440", async ({ page }) => {
    const section = page.locator("section", { has: page.getByText("Раздел 05 · Аудитория") });
    await expect(section).toHaveScreenshot("origin-1440.png", { maxDiffPixels: 100 });
  });

  test("Full page — mobile 375", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot("full-mobile.png", { fullPage: true, maxDiffPixels: 500 });
  });
});
