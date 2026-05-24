import { chromium } from "@playwright/test";
import { resolve } from "node:path";

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 630 } });
  const page = await ctx.newPage();
  const html = `
    <!doctype html><html><body style="margin:0;font-family:Georgia,serif;background:#FAF8F2;color:#14110B;width:1200px;height:630px;display:flex;flex-direction:column;justify-content:space-between;padding:80px;box-sizing:border-box;position:relative;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:36px;font-style:italic;letter-spacing:-0.02em;">Эмпирик</div>
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
        <svg width="64" height="160" viewBox="0 0 64 160" fill="none">
          <path d="M32 6 C 24 30, 18 60, 14 100 C 12 116, 18 130, 24 132 L 32 156 L 40 132 C 46 130, 52 116, 50 100 C 46 60, 40 30, 32 6 Z" fill="#B58A2F" opacity="0.65"/>
          <line x1="32" y1="10" x2="32" y2="158" stroke="#14110B" stroke-width="0.6"/>
        </svg>
      </div>
    </body></html>
  `;
  await page.setContent(html);
  await page.waitForLoadState("networkidle");
  const out = resolve("public/landing/og-image-empirik.png");
  await page.screenshot({ path: out, omitBackground: false });
  console.log(`wrote ${out}`);
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
