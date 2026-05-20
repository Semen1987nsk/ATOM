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

test("SimpleFact section has 3 columns with statements", async ({ page }) => {
  await page.goto("/");
  const section = page.locator("#simple-fact");
  await expect(section).toBeVisible();
  await expect(section.locator('[data-testid="simple-fact-column"]')).toHaveCount(3);
  await expect(section.getByText("01").first()).toBeVisible();
  await expect(section.getByText("02").first()).toBeVisible();
  await expect(section.getByText("03").first()).toBeVisible();
});

test("SimpleFact columns show large orange numerals", async ({ page }) => {
  await page.goto("/");
  const section = page.locator("#simple-fact");
  const numerals = section.locator('[data-fact-numeral]');
  await expect(numerals).toHaveCount(3);
  const color = await numerals.first().evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe("rgb(232, 78, 28)");
  const fontFamily = await numerals.first().evaluate((el) => getComputedStyle(el).fontFamily);
  expect(fontFamily.toLowerCase()).toContain("manrope");
});

test('Champions section has 6 cards', async ({ page }) => {
  await page.goto('/');
  const section = page.locator('#champions');
  await expect(section).toBeVisible();
  await expect(section.locator('[data-testid="champion-card"]')).toHaveCount(6);
  for (const name of ['Ливермор', 'Дарвас', 'Минервини', 'Тюдор Джонс', 'Элдер', 'Рашке']) {
    await expect(section.getByText(name).first()).toBeVisible();
  }
});

test("Champion cards have Manrope names and orange quote rule", async ({ page }) => {
  await page.goto("/");
  const card = page.locator('[data-testid="champion-card"]').first();
  await expect(card).toBeVisible();
  const name = card.locator('[data-champion-name]');
  const nameFont = await name.evaluate((el) => getComputedStyle(el).fontFamily);
  expect(nameFont.toLowerCase()).toContain("manrope");
  const quote = card.locator('[data-champion-quote]').first();
  const borderColor = await quote.evaluate((el) => getComputedStyle(el).borderLeftColor);
  expect(borderColor).toBe("rgb(232, 78, 28)");
});

test("Champion cards have uplift-raise scroll-trigger class", async ({ page }) => {
  await page.goto("/");
  const cards = page.locator('[data-testid="champion-card"]');
  await expect(cards.first()).toHaveClass(/uplift-raise/);
});
