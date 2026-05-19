import { test, expect } from "@playwright/test";

test("landing has 16 sections in correct order", async ({ page }) => {
  await page.goto("/");

  const headingTexts = [
    "Журнал сделок · MOEX",
    "Сам факт записи",
    "Дисциплина чемпионов",
    "Раздел 01 — Trade Replay",
    "Раздел 02 — MAE / MFE",
    "Раздел 03 — Аналитический центр",
    "Раздел 04 — Эвристический разбор",
    "Раздел 05 — Для серьёзного трейдера",
    "Раздел 06 — Тарифы",
  ];

  const ys: number[] = [];
  for (const text of headingTexts) {
    const locator = page.getByText(text, { exact: false }).first();
    await expect(locator).toBeVisible();
    const box = await locator.boundingBox();
    if (!box) throw new Error(`No bounding box for: ${text}`);
    ys.push(box.y);
  }

  for (let i = 1; i < ys.length; i++) {
    expect(ys[i]).toBeGreaterThan(ys[i - 1]);
  }
});
