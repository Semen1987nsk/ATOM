/**
 * Захват PNG-скриншотов из живого dev-сервера для статических ассетов лендинга.
 * Используем editorial-stub HTML — production-quality пример AI-карточки в том же
 * design language что и dashboard. Заменяется на real screenshot когда появится
 * стабильная test fixture с реальными данными.
 */
import { chromium } from "@playwright/test";
import { resolve } from "node:path";

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 720, height: 540 } });
  const page = await ctx.newPage();

  const stub = `
    <!doctype html><html><body style="margin:0;font-family:Georgia,serif;background:#FAF8F2;padding:32px;color:#14110B;">
    <div style="border:1px solid rgba(20,17,11,0.20);padding:28px;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:rgba(20,17,11,0.4);margin-bottom:20px;">
        Из журнала · SBER · Long · 14 мая
      </div>
      <div style="border-bottom:1px solid rgba(20,17,11,0.08);padding-bottom:18px;margin-bottom:18px;">
        <div style="font-size:13px;color:rgba(20,17,11,0.4);margin-bottom:8px;">Вердикт</div>
        <div style="font-size:22px;font-style:italic;line-height:1.25;">«Преждевременный выход. Тейк-профит не достигнут, MFE +1.8R упущен.»</div>
      </div>
      <div style="border-bottom:1px solid rgba(20,17,11,0.08);padding-bottom:18px;margin-bottom:18px;">
        <div style="font-size:13px;color:rgba(20,17,11,0.4);margin-bottom:8px;">Что повторяется</div>
        <div style="font-size:15px;line-height:1.6;color:rgba(20,17,11,0.62);">
          Третий выход в зоне 0.7–0.9R за неделю. Паттерн: на третий час удержания закрываете «на всякий случай» — статистически невыгодно.
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:24px;font-family:'JetBrains Mono',monospace;">
        <div><div style="font-size:11px;color:rgba(20,17,11,0.4);margin-bottom:4px;">MAE</div><div style="font-size:20px;">−0.42 R</div></div>
        <div><div style="font-size:11px;color:rgba(20,17,11,0.4);margin-bottom:4px;">MFE</div><div style="font-size:20px;color:#1F6A47;">+1.84 R</div></div>
        <div><div style="font-size:11px;color:rgba(20,17,11,0.4);margin-bottom:4px;">Реализовано</div><div style="font-size:20px;">+0.71 R</div></div>
      </div>
    </div>
    </body></html>
  `;
  await page.setContent(stub);
  await page.waitForLoadState("networkidle");
  const out = resolve("public/landing/ai-card-sber-screenshot.png");
  await page.screenshot({ path: out, fullPage: true });
  console.log(`wrote ${out}`);
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
