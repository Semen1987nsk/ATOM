import { test, expect } from "@playwright/test";

test.describe("Landing — visual regression @visual", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    await page.addStyleTag({ content: `[aria-label="live"] { animation: none !important; }` });
  });

  test("Hero — desktop dark", async ({ page }) => {
    await expect(page.locator('[data-section="hero"]')).toHaveScreenshot("hero-dark-1440.png", { maxDiffPixels: 100 });
  });

  test("NumbersBand — desktop dark", async ({ page }) => {
    const section = page.locator('[data-section="numbers-band"]');
    // Scroll into view to trigger CountUp inView, then wait for 1500ms animation + buffer
    await section.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    await expect(section).toHaveScreenshot("numbers-dark-1440.png", { maxDiffPixels: 100 });
  });

  test("Champions — desktop", async ({ page }) => {
    await expect(page.locator('[data-section="champions"]')).toHaveScreenshot("champions-1440.png", { maxDiffPixels: 200 });
  });

  test("Trade Replay (01) — desktop", async ({ page }) => {
    await expect(page.locator('[data-section="replay-01"]')).toHaveScreenshot("replay-01-1440.png", { maxDiffPixels: 100 });
  });

  test("MAE/MFE (02) — desktop dark", async ({ page }) => {
    await expect(page.locator('[data-section="mae-mfe-02"]')).toHaveScreenshot("mae-mfe-02-dark-1440.png", { maxDiffPixels: 100 });
  });

  test("Pull-quote — desktop dark", async ({ page }) => {
    await expect(page.locator('[data-section="pull-quote"]')).toHaveScreenshot("pull-quote-1440.png", { maxDiffPixels: 100 });
  });

  test("AudienceQualifier (05) — desktop tint", async ({ page }) => {
    await expect(page.locator('[data-section="audience-05"]')).toHaveScreenshot("audience-05-1440.png", { maxDiffPixels: 100 });
  });

  test("Pricing split — desktop", async ({ page }) => {
    await expect(page.locator('[data-section="pricing-06"]')).toHaveScreenshot("pricing-split-1440.png", { maxDiffPixels: 100 });
  });

  test("Final CTA — desktop dark", async ({ page }) => {
    await expect(page.locator('[data-section="final-cta"]')).toHaveScreenshot("final-cta-1440.png", { maxDiffPixels: 100 });
  });

  test("Full page — mobile 375", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("full-mobile.png", { fullPage: true, maxDiffPixels: 500 });
  });
});

test.describe("Landing — reduced motion visual @visual", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
  });

  test("Hero — desktop reduced motion (curve at final state)", async ({ page }) => {
    await expect(page.locator('[data-section="hero"]')).toHaveScreenshot("hero-dark-reduced-1440.png", { maxDiffPixels: 100 });
  });

  test("Full page — mobile reduced motion", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("full-mobile-reduced.png", { fullPage: true, maxDiffPixels: 500 });
  });
});
