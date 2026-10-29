// Browser smoke test against a running stack: node e2e/smoke.mjs [baseUrl] [fixturesDir] [screenshotsDir]
// Covers on-device processing, server processing, sign-up, signing, the page organizer and Pro gating.
import { createRequire } from "node:module";
import assert from "node:assert/strict";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] ?? "http://localhost:3000";
const FIX = process.argv[3] ?? "/tmp/e2e";
const SHOTS = process.argv[4] ?? FIX;
const fixture = (n) => path.join(FIX, n);

const browser = await chromium.launch();
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
const apiJobs = [];
page.on("request", (r) => r.url().includes("/api/jobs") && r.method() === "POST" && apiJobs.push(r.url()));

async function step(name, fn) {
  process.stdout.write(`• ${name} … `);
  await fn();
  console.log("ok");
}

await step("home page lists the tools", async () => {
  await page.goto(BASE);
  await page.getByRole("heading", { name: /Every tool you need/ }).waitFor();
  assert.ok((await page.locator('a[href^="/tools/"]').count()) > 40);
  await page.screenshot({ path: path.join(SHOTS, "home.png"), fullPage: false });
});

await step("merge runs on-device (no upload)", async () => {
  await page.goto(`${BASE}/tools/merge`);
  await page.locator('input[type=file]').first().setInputFiles([fixture("alpha.pdf"), fixture("beta.pdf")]);
  await page.getByText("Private mode").waitFor();
  await page.screenshot({ path: path.join(SHOTS, "merge-ready.png") });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /Merge PDF/ }).last().click();
  assert.equal((await download).suggestedFilename(), "merged.pdf");
  await page.getByText("Nothing was uploaded").waitFor();
  assert.equal(apiJobs.length, 0, "merge should not hit the server");
  await page.screenshot({ path: path.join(SHOTS, "merge-done.png") });
});

await step("compress runs on the server", async () => {
  await page.goto(`${BASE}/tools/compress`);
  await page.locator('input[type=file]').first().setInputFiles(fixture("alpha.pdf"));
  const download = page.waitForEvent("download", { timeout: 60_000 });
  await page.getByRole("button", { name: /Compress PDF/ }).last().click();
  assert.match((await download).suggestedFilename(), /alpha-compressed\.pdf/);
  await page.getByText("Delete from server now").click();
  await page.getByText("Deleted from our servers").waitFor();
});

await step("organize shows thumbnails and runs on-device", async () => {
  await page.goto(`${BASE}/tools/organize`);
  await page.locator('input[type=file]').first().setInputFiles(fixture("alpha.pdf"));
  await page.getByText("3 pages.").waitFor({ timeout: 20_000 });
  await page.locator("ol li").first().hover();
  await page.getByRole("button", { name: "Rotate right" }).first().click();
  await page.locator("ol li").nth(1).hover();
  await page.getByRole("button", { name: "Delete page" }).nth(1).click();
  await page.getByText("2 pages.").waitFor();
  await page.screenshot({ path: path.join(SHOTS, "organize.png") });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /Organize PDF/ }).last().click();
  await download;
});

await step("sign up and see the account", async () => {
  await page.goto(`${BASE}/register`);
  await page.getByLabel("Name").fill("Ada");
  await page.getByLabel("Email").fill(`ada+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct horse battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(/\/account/);
  await page.getByText("Free", { exact: true }).waitFor();
  await page.screenshot({ path: path.join(SHOTS, "account.png") });
});

await step("sign a PDF with a drawn signature", async () => {
  await page.goto(`${BASE}/tools/sign`);
  await page.locator('input[type=file]').first().setInputFiles(fixture("alpha.pdf"));
  const pad = page.locator("canvas").first();
  await pad.waitFor();
  const box = await pad.boundingBox();
  await page.mouse.move(box.x + 30, box.y + 80);
  await page.mouse.down();
  for (let i = 0; i < 12; i++) await page.mouse.move(box.x + 40 + i * 25, box.y + 60 + (i % 2) * 40);
  await page.mouse.up();
  await page.getByText("Click the page to place").waitFor();
  const preview = page.getByAltText("Page 1");
  await preview.waitFor({ timeout: 20_000 });
  const pb = await preview.boundingBox();
  await preview.click({ position: { x: pb.width * 0.7, y: pb.height * 0.85 } });
  await page.getByText("1 signature placed").waitFor();
  await page.screenshot({ path: path.join(SHOTS, "sign.png") });
  const download = page.waitForEvent("download", { timeout: 60_000 });
  await page.getByRole("button", { name: /Sign PDF/ }).last().click();
  assert.match((await download).suggestedFilename(), /signed\.pdf$/);
});

await step("Pro tools are gated for free accounts", async () => {
  await page.goto(`${BASE}/tools/ocr`);
  await page.getByText("is part of Pro").waitFor();
  await page.goto(`${BASE}/pricing`);
  await page.getByRole("heading", { name: "Pro" }).waitFor();
  await page.screenshot({ path: path.join(SHOTS, "pricing.png") });
});

await step("history lists server tasks", async () => {
  await page.goto(`${BASE}/account?tab=history`);
  await page.getByText("Sign PDF").waitFor();
});

await step("mobile layout", async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/tools/merge`);
  await page.screenshot({ path: path.join(SHOTS, "mobile.png") });
});

assert.deepEqual(errors, [], `page errors: ${errors.join("\n")}`);
await browser.close();
console.log("All smoke checks passed.");
