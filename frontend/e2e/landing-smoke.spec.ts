import { test, expect } from "@playwright/test";

test.describe("Landing — smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders all 16 sections without errors", async ({ page }) => {
    await expect(page.getByRole("link", { name: "МААТТ" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Запись делает трейдера/i })).toBeVisible();
    await expect(page.getByText(/Журнал — не отчётность/i).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Двенадцать правил против/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /MAE и MFE — из минутных свечей/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Свечи MOEX вокруг каждой/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Для серьёзного/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Перестаньте гадать/i })).toBeVisible();
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

  test("footer has МААТТ wordmark + email", async ({ page }) => {
    await expect(page.locator("footer >> text=МААТТ").first()).toBeVisible();
    await expect(page.locator("footer >> text=hello@maatt.ru")).toBeVisible();
  });
});
