import { chromium } from "@playwright/test";
import { resolve } from "node:path";

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 630 } });
  const page = await ctx.newPage();
  const html = `
    <!doctype html><html><body style="margin:0;font-family:Georgia,serif;background:#FAF8F2;color:#14110B;width:1200px;height:630px;display:flex;flex-direction:column;justify-content:space-between;padding:80px;box-sizing:border-box;position:relative;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:36px;font-style:italic;letter-spacing:-0.02em;">Полистата</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:14px;letter-spacing:0.15em;text-transform:uppercase;color:rgba(20,17,11,0.5);">Журнал сделок · MOEX</div>
      </div>
      <div>
        <div style="font-size:96px;line-height:0.95;letter-spacing:-0.025em;font-weight:350;max-width:900px;">
          Каждая сделка <em>измерена.</em><br/>Каждое решение <em>взвешено.</em>
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:flex-end;">
        <div style="font-family:'JetBrains Mono',monospace;font-size:16px;color:rgba(20,17,11,0.5);">
          empirik.io · Точно. Чисто. Честно.
        </div>
        <svg width="150" height="80" viewBox="0 0 150 80" fill="none">
          <path d="M10,68 C50,68 56,14 75,14 C94,14 100,68 140,68" stroke="#B58A2F" stroke-width="3.5" stroke-linecap="round" fill="none"/>
          <line x1="10" y1="68" x2="140" y2="68" stroke="#14110B" stroke-width="0.6" opacity="0.5"/>
          <circle cx="75" cy="14" r="4" fill="#B58A2F"/>
        </svg>
      </div>
    </body></html>
  `;
  await page.setContent(html);
  await page.waitForLoadState("networkidle");
  const out = resolve("public/landing/og-image-polistata.png");
  await page.screenshot({ path: out, omitBackground: false });
  console.log(`wrote ${out}`);
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
