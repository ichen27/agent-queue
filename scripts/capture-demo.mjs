// Reproducible captures of the real browser-only demo, never a design mockup.
import { chromium } from "../dashboard/node_modules/playwright/index.mjs";
import { mkdir, rename } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const output = fileURLToPath(new URL("../docs/media/", import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1024 },
  recordVideo: { dir: output, size: { width: 1440, height: 1024 } },
});
const page = await context.newPage();
await page.goto("http://127.0.0.1:7891/?demo=1");
await page.getByRole("heading", { name: "payments / retry-policy" }).waitFor();
await page.screenshot({ path: output + "agent-queue-desktop.png", fullPage: true });
await page.waitForTimeout(1800);
await page.getByRole("button", { name: "Attention 3", exact: true }).click();
await page.waitForTimeout(1000);
await page.getByRole("button", { name: /api \/ schema-migration/ }).click();
await page.waitForTimeout(1800);
await page.getByRole("button", { name: "Review in iTerm2" }).click();
await page.waitForTimeout(1500);
await page.getByRole("button", { name: /web \/ design-tokens/ }).click();
await page.waitForTimeout(1000);
await page.getByRole("textbox", { name: "Reply to session" }).pressSequentially("Preserve the semantic names.", { delay: 65 });
await page.waitForTimeout(600);
await page.getByRole("button", { name: "Simulate reply" }).click();
await page.waitForTimeout(2200);
await page.getByRole("button", { name: "Reset demo" }).click();
await page.waitForTimeout(1200);
const video = page.video();
await context.close();
await rename(await video.path(), output + "agent-queue-demo.webm");
const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await mobile.goto("http://127.0.0.1:7891/?demo=1");
await mobile.getByRole("heading", { name: "payments / retry-policy" }).waitFor();
await mobile.screenshot({ path: output + "agent-queue-mobile.png", fullPage: true });
await browser.close();
console.log("Captured desktop, mobile, and WebM walkthrough in docs/media/.");
