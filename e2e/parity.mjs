// Browser test for the Smallpdf-parity round: node e2e/parity.mjs [baseUrl] [fixturesDir] [outDir] [apiLog]
// Fixtures: alpha.pdf, photo.jpg, book.epub and bundle.zip (alpha.pdf + photo.jpg + one unsupported file).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] ?? "http://localhost:3000";
const FIX = process.argv[3] ?? "/tmp/e2e";
const OUT = process.argv[4] ?? FIX;
const LOG = process.argv[5] ?? "/tmp/e2e/api.log";
const fixture = (n) => path.join(FIX, n);
const errors = [];

const browser = await chromium.launch();
async function newPage(viewport = { width: 1280, height: 1400 }) {
  const context = await browser.newContext({ acceptDownloads: true, viewport, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(String(e)));
  return page;
}
async function step(name, fn) {
  process.stdout.write(`• ${name} … `);
  await fn();
  console.log("ok");
}
async function runAndSave(page, buttonName, file, timeout = 60_000) {
  const download = page.waitForEvent("download", { timeout });
  await page.getByRole("button", { name: buttonName }).last().click();
  const d = await download;
  await d.saveAs(path.join(OUT, file));
  return d.suggestedFilename();
}
function signLink(email) {
  const blocks = readFileSync(LOG, "utf8").split("EMAIL to=").filter((b) => b.startsWith(email));
  const match = blocks.at(-1)?.match(/\/sign\/([\w-]+)/);
  assert.ok(match, `no signing link for ${email}`);
  return { url: `${BASE}/sign/${match[1]}`, text: blocks.at(-1) };
}

const owner = await newPage();
const stamp = Date.now();
await owner.request.post(`${BASE}/api/auth/register`, { data: { email: `parity${stamp}@example.com`, password: "correct horse", name: "Pat Parity" } });

await step("reader: open a PDF on the device and search it", async () => {
  await owner.goto(`${BASE}/reader`);
  await owner.locator("input[type=file]").first().setInputFiles(fixture("alpha.pdf"));
  await owner.getByText("Nothing was uploaded").waitFor();
  await owner.locator(".pdfViewer .page").first().waitFor({ timeout: 20_000 });
  await owner.getByRole("button", { name: "Search", exact: true }).click();
  await owner.getByLabel("Search in document").fill("Alpha");
  await owner.getByLabel("Search in document").press("Enter");
  await owner.getByText(/^1 of \d+$/).waitFor({ timeout: 10_000 });
  await owner.getByRole("button", { name: "Next result" }).click();
  await owner.getByText(/^2 of \d+$/).waitFor();
  await owner.screenshot({ path: path.join(OUT, "reader.png") });
});

await step("import from a link refuses private addresses", async () => {
  await owner.goto(`${BASE}/tools/compress`);
  await owner.getByRole("button", { name: "A link" }).click();
  await owner.getByLabel("File link").fill("http://127.0.0.1:8000/api/health");
  await owner.getByRole("button", { name: "Add", exact: true }).click();
  await owner.getByText("private address").waitFor();
  await owner.getByRole("button", { name: "My documents" }).waitFor(); // signed in, so documents are offered
});

await step("annotate: a note and a highlight, processed into a PDF", async () => {
  await owner.goto(`${BASE}/tools/annotate_pdf`);
  await owner.locator("input[type=file]").first().setInputFiles(fixture("alpha.pdf"));
  await owner.locator("img[alt='Page 1']").waitFor({ timeout: 20_000 });
  const canvas = owner.getByTestId("editor-canvas");
  await owner.getByRole("button", { name: "Note" }).click();
  await canvas.click({ position: { x: 420, y: 160 } });
  await owner.getByRole("button", { name: "Highlight" }).click();
  const box = await canvas.boundingBox();
  await owner.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.08);
  await owner.mouse.down();
  await owner.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.11, { steps: 5 });
  await owner.mouse.up();
  await owner.screenshot({ path: path.join(OUT, "annotate.png") });
  assert.match(await runAndSave(owner, /^Annotate PDF/, "annotated.pdf"), /\.pdf$/);
});

await step("ebook and ZIP converters", async () => {
  await owner.goto(`${BASE}/tools/ebook_to_pdf`);
  await owner.locator("input[type=file]").first().setInputFiles(fixture("book.epub"));
  assert.equal(await runAndSave(owner, /^Ebook to PDF/, "book.pdf"), "book.pdf");
  await owner.goto(`${BASE}/tools/zip_to_pdf`);
  await owner.locator("input[type=file]").first().setInputFiles(fixture("bundle.zip"));
  assert.match(await runAndSave(owner, /^ZIP to PDF/, "bundle.pdf"), /\.pdf$/);
});

let shareUrl;
await step("save a result to My documents and share it with a password", async () => {
  await owner.getByRole("button", { name: /Save to My documents/ }).click();
  await owner.getByText(/Saved/).first().waitFor();
  await owner.goto(`${BASE}/documents`);
  await owner.getByText("bundle.pdf").waitFor();
  await owner.getByRole("button", { name: "Share bundle.pdf" }).click();
  const dialog = owner.getByRole("dialog");
  await dialog.getByPlaceholder("At least 4 characters").fill("open sesame");
  await dialog.getByRole("button", { name: "Create link" }).click();
  await dialog.getByText("Link created").waitFor();
  shareUrl = (await dialog.locator("code").first().textContent()).trim();
  assert.match(shareUrl, /\/s\/[\w-]+$/);
});

await step("open the share link: password first, then the viewer, and the embed view", async () => {
  const visitor = await newPage();
  const url = shareUrl.replace(/^https?:\/\/[^/]+/, BASE);
  await visitor.goto(url);
  await visitor.getByLabel("Password").fill("wrong");
  await visitor.getByRole("button", { name: "Open" }).click();
  await visitor.getByText("isn't right").waitFor();
  await visitor.getByLabel("Password").fill("open sesame");
  await visitor.getByRole("button", { name: "Open" }).click();
  await visitor.locator("[data-testid=pdf-viewer] .page").first().waitFor({ timeout: 20_000 });
  await visitor.screenshot({ path: path.join(OUT, "shared.png") });
  const embed = await newPage({ width: 800, height: 600 });
  const r = await embed.goto(`${url}?embed=1`);
  assert.equal(r.headers()["content-security-policy"], "frame-ancestors *");
  await embed.getByLabel("Password").waitFor();
  const home = await embed.request.get(`${BASE}/`);
  assert.equal(home.headers()["content-security-policy"], "frame-ancestors 'self'");
});

let template;
await step("eSign: access code, and save the request as a template", async () => {
  await owner.goto(`${BASE}/esign/new`);
  await owner.locator("input[type=file]").first().setInputFiles(fixture("alpha.pdf"));
  await owner.getByLabel("Signer 1 name").fill("Cora Client");
  await owner.getByLabel("Signer 1 email").fill(`cora${stamp}@example.com`);
  await owner.getByLabel("Ask for an access code").check();
  await owner.getByLabel("Signer 1 access code").fill("7391");
  await owner.getByRole("button", { name: "Next: place fields" }).click();
  const canvas = owner.getByTestId("esign-canvas");
  await canvas.waitFor();
  await owner.waitForTimeout(500);
  await canvas.click({ position: { x: 200, y: 600 } });
  await owner.getByRole("button", { name: "Save as template" }).click();
  await owner.getByLabel("Template name").fill("Client NDA");
  await owner.getByLabel("Role 1").fill("Client");
  await owner.getByRole("button", { name: "Save template" }).click();
  await owner.getByText("Saved “Client NDA”").waitFor();
  await owner.getByRole("button", { name: /Send to 1 person/ }).click();
  await owner.waitForURL(/\/esign\/\w+\?sent=1/);
  await owner.getByText("code", { exact: true }).waitFor();
});

await step("signer must enter the access code, then signs", async () => {
  const { url, text } = signLink(`cora${stamp}@example.com`);
  assert.ok(text.includes("access code") && !text.includes("7391"), "the email mentions the code but doesn't contain it");
  const signer = await newPage();
  await signer.goto(url);
  await signer.getByLabel("Access code").fill("0000");
  await signer.getByRole("button", { name: "Open the document" }).click();
  await signer.getByText("isn't right").waitFor();
  await signer.getByLabel("Access code").fill("7391");
  await signer.getByRole("button", { name: "Open the document" }).click();
  await signer.getByText("Signing as Cora Client").waitFor();
  await signer.getByRole("button", { name: "Signature" }).first().click();
  const pad = signer.getByRole("dialog").locator("canvas");
  if (await pad.count()) {
    const b = await pad.boundingBox();
    await signer.mouse.move(b.x + 20, b.y + b.height / 2);
    await signer.mouse.down();
    await signer.mouse.move(b.x + 120, b.y + 20, { steps: 6 });
    await signer.mouse.move(b.x + 220, b.y + b.height - 20, { steps: 6 });
    await signer.mouse.up();
  } else {
    await signer.getByRole("dialog").getByRole("textbox").first().fill("Cora Client");
  }
  await signer.getByRole("button", { name: "Use this signature" }).click();
  await signer.getByLabel(/I agree to sign/).check();
  await signer.getByRole("button", { name: "Finish signing" }).click();
  await signer.getByText("Thanks, you've signed").waitFor();
});

await step("the template appears and prefills a new request", async () => {
  await owner.goto(`${BASE}/esign`);
  await owner.getByText("Client NDA").waitFor();
  await owner.getByText(/Client · 1 field/).waitFor();
  await owner.getByRole("link", { name: "Use" }).click();
  await owner.getByText("Using the template “Client NDA”").waitFor();
  await owner.getByText("Client", { exact: true }).waitFor();
  assert.equal(await owner.getByRole("button", { name: "Add someone" }).count(), 0);
});

await browser.close();
assert.deepEqual(errors, [], `page errors: ${errors.join("\n")}`);
console.log("All parity checks passed.");
