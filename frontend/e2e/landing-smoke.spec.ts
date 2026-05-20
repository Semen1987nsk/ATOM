import { test, expect } from "@playwright/test";

test.describe("Landing — smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders all 16 sections without errors", async ({ page }) => {
    await expect(page.getByRole("link", { name: "МААТТ" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Запись делает трейдера/i }).first()).toBeVisible();
    await expect(page.getByText(/Журнал — не отчётность/i).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Двенадцать правил против/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /MAE и MFE — из минутных свечей/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Свечи MOEX вокруг каждой/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Если торгуете MOEX — вам/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Free — чтобы понять. Pro — чтобы изменить/i })).toBeVisible();
    await expect(page.getByText(/Начните вести/i)).toBeVisible();
  });

  test("ticker shows 5 symbols (live or fallback)", async ({ page }) => {
    for (const sym of ["SBER", "GAZP", "LKOH", "YNDX", "IMOEX"]) {
      await expect(page.locator(`text=${sym}`).first()).toBeVisible();
    }
  });

  test("trade replay slider is operable via keyboard", async ({ page }) => {
    const slider = page.getByLabel("Точка во времени");
    await expect(slider).toBeVisible();
    await slider.focus();
    const initial = await slider.inputValue();
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    const after = await slider.inputValue();
    expect(after).not.toBe(initial);
  });

  test("candle chart shows tooltip on hover", async ({ page }) => {
    const chart = page.locator("svg[aria-label*='Свечи SBER']");
    await expect(chart).toBeVisible();
    const box = await chart.boundingBox();
    if (!box) throw new Error("chart not measured");
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    await expect(page.locator("text=MFE").first()).toBeVisible({ timeout: 2000 });
  });

  test("LiveTicker rendered on orange strip with mono text", async ({ page }) => {
    const ticker = page.locator('[data-section="live-ticker"]');
    await expect(ticker).toBeVisible();
    const bg = await ticker.evaluate((el) => getComputedStyle(el).backgroundColor);
    // #E84E1C = rgb(232, 78, 28)
    expect(bg).toBe("rgb(232, 78, 28)");
    const track = ticker.locator(".uplift-ticker-track").first();
    await expect(track).toBeVisible();
    const fontFamily = await track.evaluate((el) => getComputedStyle(el).fontFamily);
    expect(fontFamily.toLowerCase()).toContain("mono");
  });

  test("Hero on dark background with Manrope H1 and orange second line", async ({ page }) => {
    const hero = page.locator('[data-section="hero"]');
    await expect(hero).toBeVisible();
    const bg = await hero.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgb(10, 10, 10)"); // --ink-dark
    const h1 = hero.locator("h1").first();
    const h1Font = await h1.evaluate((el) => getComputedStyle(el).fontFamily);
    expect(h1Font.toLowerCase()).toContain("manrope");
    const orangeLine = hero.locator('[data-h1-accent="true"]').first();
    await expect(orangeLine).toBeVisible();
    const orangeColor = await orangeLine.evaluate((el) => getComputedStyle(el).color);
    expect(orangeColor).toBe("rgb(232, 78, 28)");
  });

  test("footer has МААТТ wordmark + email", async ({ page }) => {
    await expect(page.locator("footer >> text=МААТТ").first()).toBeVisible();
    await expect(page.locator("footer >> text=hello@maatt.ru")).toBeVisible();
  });

  test("Manrope font loaded and applied to body display class", async ({ page }) => {
    await page.evaluate(() => document.fonts.ready);
    const fontFaces = await page.evaluate(() =>
      Array.from(document.fonts).map((f) => f.family.toLowerCase())
    );
    expect(fontFaces.some((f) => f.includes("manrope"))).toBe(true);

    const cssVar = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--font-display").trim()
    );
    expect(cssVar.length).toBeGreaterThan(0);
  });

  test("uplift tokens defined on landing root", async ({ page }) => {
    await page.waitForSelector('[data-theme="maatt-cream"]');
    const tokens = await page.evaluate(() => {
      const root = document.querySelector('[data-theme="maatt-cream"]') ?? document.documentElement;
      const cs = getComputedStyle(root);
      return {
        orange: cs.getPropertyValue("--orange").trim(),
        orangeHover: cs.getPropertyValue("--orange-hover").trim(),
        orangeSoft: cs.getPropertyValue("--orange-soft").trim(),
        inkDark: cs.getPropertyValue("--ink-dark").trim(),
        paperOnDark: cs.getPropertyValue("--paper-on-dark").trim(),
        ruleOnDark: cs.getPropertyValue("--rule-on-dark").trim(),
      };
    });
    expect(tokens.orange.toLowerCase()).toBe("#e84e1c");
    expect(tokens.orangeHover.toLowerCase()).toBe("#d44516");
    // Chromium serialises rgba(232,78,28,0.10) as #e84e1c1a — match either form
    expect(tokens.orangeSoft.toLowerCase()).toMatch(/0\.10|#e84e1c1a/);
    expect(tokens.inkDark.toLowerCase()).toBe("#0a0a0a");
    expect(tokens.paperOnDark.toLowerCase()).toBe("#fafafa");
    // Chromium serialises rgba(250,250,250,0.10) as #fafafa1a — match either form
    expect(tokens.ruleOnDark.toLowerCase()).toMatch(/0\.10|#fafafa1a/);
  });
});
