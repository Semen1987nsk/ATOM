import { test, expect } from "@playwright/test";

const EXPECTED_RHYTHM: Array<{ section: string; bg: string }> = [
  { section: "live-ticker",   bg: "rgb(232, 78, 28)"   }, // orange strip
  { section: "hero",          bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "simple-fact",   bg: "rgb(250, 248, 242)" }, // LIGHT paper
  { section: "champions",     bg: "rgb(250, 248, 242)" }, // LIGHT paper
  { section: "numbers-band",  bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "manifest",      bg: "rgb(244, 236, 220)" }, // LIGHT tint
  { section: "replay-01",     bg: "rgb(250, 248, 242)" }, // LIGHT paper
  { section: "mae-mfe-02",    bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "metrics-03",    bg: "rgb(250, 248, 242)" }, // LIGHT paper
  { section: "pull-quote",    bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "heuristics-04", bg: "rgb(250, 248, 242)" }, // LIGHT paper
  { section: "audience-05",   bg: "rgb(244, 236, 220)" }, // LIGHT tint
  { section: "pricing-06",    bg: "rgb(250, 248, 242)" }, // LIGHT paper (SPLIT root paper, inner Pro is dark)
  { section: "final-cta",     bg: "rgb(10, 10, 10)"    }, // DARK
];

test("landing follows expected dark/light/orange rhythm in order", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  await page.waitForSelector('[data-theme="maatt-cream"]');
  const ys: number[] = [];
  for (const { section, bg } of EXPECTED_RHYTHM) {
    const locator = page.locator(`[data-section="${section}"]`);
    await expect(locator, `section ${section} present`).toBeVisible();
    const actualBg = await locator.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(actualBg, `${section} background`).toBe(bg);
    const box = await locator.boundingBox();
    if (!box) throw new Error(`No box for ${section}`);
    ys.push(box.y);
  }
  for (let i = 1; i < ys.length; i++) {
    expect(
      ys[i],
      `${EXPECTED_RHYTHM[i].section} should appear after ${EXPECTED_RHYTHM[i - 1].section}`
    ).toBeGreaterThan(ys[i - 1]);
  }
});

test("no two consecutive sections share DARK background (visual rhythm intact)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector('[data-theme="maatt-cream"]');
  const sections = EXPECTED_RHYTHM;
  for (let i = 1; i < sections.length; i++) {
    if (sections[i].bg === "rgb(10, 10, 10)" && sections[i - 1].bg === "rgb(10, 10, 10)") {
      throw new Error(`Two consecutive DARK sections: ${sections[i - 1].section} → ${sections[i].section}`);
    }
  }
});

test("rhythm map covers all 14 uplift sections", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector('[data-theme="maatt-cream"]');
  // Use document.querySelectorAll directly — locator.evaluateAll() can return empty
  // before hydration completes even when elements are present in the DOM.
  const uplift = await page.evaluate(() =>
    Array.from(document.querySelectorAll("[data-section]")).map(
      (el) => el.getAttribute("data-section")
    )
  ) as (string | null)[];
  for (const { section } of EXPECTED_RHYTHM) {
    expect(uplift, `expected section ${section} in DOM`).toContain(section);
  }
});

test("page has exactly 14 uplift sections (no accidental additions or renames)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector('[data-theme="maatt-cream"]');
  const sections = await page.locator('[data-section]').count();
  expect(sections).toBe(14);
});
