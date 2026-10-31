// Browser test for the editor, form tools, scan and split by text: node e2e/features.mjs [baseUrl] [fixturesDir] [outDir]
// Fixtures: alpha.pdf (3 pages, "Heading 1..3") and photo.jpg. Outputs are saved to outDir for inspection.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] ?? "http://localhost:3000";
const FIX = process.argv[3] ?? "/tmp/e2e";
const OUT = process.argv[4] ?? FIX;
const fixture = (n) => path.join(FIX, n);

const browser = await chromium.launch();
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 1700 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
const uploads = [];
page.on("request", (r) => r.url().includes("/api/jobs") && r.method() === "POST" && uploads.push(r.url()));

async function step(name, fn) {
  process.stdout.write(`• ${name} … `);
  await fn();
  console.log("ok");
}

async function open(tool, files) {
  await page.goto(`${BASE}/tools/${tool}`);
  await page.locator("input[type=file]").first().setInputFiles(files);
}

async function drag(canvas, from, to) {
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width * from[0], box.y + box.height * from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * ((from[0] + to[0]) / 2), box.y + box.height * ((from[1] + to[1]) / 2), { steps: 4 });
  await page.mouse.move(box.x + box.width * to[0], box.y + box.height * to[1], { steps: 4 });
  await page.mouse.up();
}

async function runAndSave(buttonName, file, timeout = 30_000) {
  const download = page.waitForEvent("download", { timeout });
  await page.getByRole("button", { name: buttonName }).last().click();
  const d = await download;
  await d.saveAs(path.join(OUT, file));
  return d.suggestedFilename();
}

await step("edit PDF on the device: rectangle, text and a drawing", async () => {
  const before = uploads.length;
  await open("edit_pdf", fixture("alpha.pdf"));
  const canvas = page.getByTestId("editor-canvas");
  await page.locator("img[alt='Page 1']").waitFor({ timeout: 20_000 });
  await page.getByRole("button", { name: "Rectangle" }).click();
  await drag(canvas, [0.1, 0.5], [0.4, 0.6]);
  await page.getByRole("button", { name: "Text", exact: true }).click();
  await canvas.click({ position: { x: 300, y: 600 } });
  await page.keyboard.type("Hello from the editor"); // the new text box opens with its placeholder selected
  await page.getByRole("button", { name: "Draw" }).click();
  await drag(canvas, [0.6, 0.8], [0.8, 0.85]);
  await page.screenshot({ path: path.join(OUT, "editor.png") });
  assert.equal(await runAndSave(/^Edit PDF/, "edited.pdf"), "alpha-edited.pdf");
  await page.getByText("Nothing was uploaded").waitFor();
  assert.equal(uploads.length, before, "edit should run on the device");
});

await step("create a form on the device: text box and checkbox", async () => {
  const before = uploads.length;
  await open("create_forms", fixture("alpha.pdf"));
  const canvas = page.getByTestId("form-canvas");
  await page.locator("img[alt='Page 1']").waitFor({ timeout: 20_000 });
  await drag(canvas, [0.1, 0.3], [0.5, 0.34]);
  await page.getByRole("button", { name: "Checkbox" }).click();
  await canvas.click({ position: { x: 60, y: 400 } });
  await page.screenshot({ path: path.join(OUT, "form-builder.png") });
  assert.equal(await runAndSave(/^Create PDF forms/, "form.pdf"), "alpha-form.pdf");
  assert.equal(uploads.length, before, "create forms should run on the device");
});

await step("fill that form on the page, on the device", async () => {
  const before = uploads.length;
  await open("fill_forms", path.join(OUT, "form.pdf"));
  await page.locator('input[aria-label="text_1"]').fill("Ada Lovelace");
  await page.getByRole("checkbox", { name: "checkbox_1" }).first().click();
  await page.screenshot({ path: path.join(OUT, "form-filler.png") });
  assert.equal(await runAndSave(/^Fill PDF forms/, "filled.pdf"), "form-filled.pdf");
  assert.equal(uploads.length, before, "fill forms should run on the device");
});

await step("scan to PDF cleans up a photo on the device", async () => {
  const before = uploads.length;
  await open("scan_to_pdf", fixture("photo.jpg"));
  assert.equal(await runAndSave(/^Scan to PDF/, "scan.pdf"), "photo-scan.pdf");
  assert.equal(uploads.length, before, "scan should run on the device");
});

await step("split by text runs on the server", async () => {
  await open("split_by_text", fixture("alpha.pdf"));
  await page.locator("#opt-text").fill("Heading 2");
  const name = await runAndSave(/^Split by text/, "split.zip", 60_000);
  assert.match(name, /\.zip$/);
});

await step("digital signature shows the certificate options", async () => {
  await open("digital_sign", fixture("alpha.pdf"));
  await page.getByLabel("Certificate file").waitFor();
  await page.locator("#opt-signer_name").waitFor();
  await page.screenshot({ path: path.join(OUT, "digital-sign.png") });
});

assert.deepEqual(errors, [], `page errors: ${errors.join("\n")}`);
await browser.close();
console.log("All feature checks passed.");
