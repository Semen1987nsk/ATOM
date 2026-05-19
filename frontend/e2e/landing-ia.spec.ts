import { test, expect } from "@playwright/test";

test("landing has 16 sections in correct order", async ({ page }) => {
  await page.goto("/");

  const sectionHeadings = [
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

  for (const h of sectionHeadings) {
    await expect(page.getByText(h, { exact: false }).first()).toBeVisible();
  }
});
