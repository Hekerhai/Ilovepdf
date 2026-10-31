// Browser test for requesting signatures: node e2e/esign.mjs [baseUrl] [fixturesDir] [outDir] [apiLog]
// Signing links are read from the API log, where the development mailer prints every email.
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
const errors = [];

const browser = await chromium.launch();
const viewport = { width: 1280, height: 1500 };

async function newPage() {
  const context = await browser.newContext({ acceptDownloads: true, viewport });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(String(e)));
  return page;
}

async function step(name, fn) {
  process.stdout.write(`• ${name} … `);
  await fn();
  console.log("ok");
}

function linkFor(email) {
  const log = readFileSync(LOG, "utf8");
  const blocks = log.split("EMAIL to=").filter((b) => b.startsWith(email));
  const match = blocks.at(-1)?.match(/\/sign\/([\w-]+)/);
  assert.ok(match, `no signing link for ${email}`);
  return `${BASE}/sign/${match[1]}`;
}

const owner = await newPage();
const stamp = Date.now();

await step("sign up and open the send wizard", async () => {
  const r = await owner.request.post(`${BASE}/api/auth/register`, { data: { email: `owner${stamp}@example.com`, password: "correct horse", name: "Olivia Owner" } });
  assert.equal(r.status(), 200);
  await owner.goto(`${BASE}/esign`);
  await owner.getByText("0 of 3 used this month").waitFor();
  await owner.getByRole("link", { name: "New request" }).click();
  await owner.locator("input[type=file]").first().setInputFiles(path.join(FIX, "alpha.pdf"));
});

await step("add two signers, in order", async () => {
  await owner.getByLabel("Signer 1 name").fill("Grace Hopper");
  await owner.getByLabel("Signer 1 email").fill("grace@example.com");
  await owner.getByRole("button", { name: "Add someone" }).click();
  await owner.getByLabel("Signer 2 name").fill("Alan Turing");
  await owner.getByLabel("Signer 2 email").fill("alan@example.com");
  await owner.getByLabel("Sign in this order").check();
  await owner.getByRole("button", { name: "Next: place fields" }).click();
});

await step("place fields for each signer and send", async () => {
  const canvas = owner.getByTestId("esign-canvas");
  await owner.locator("img[alt='Page 1']").waitFor({ timeout: 20_000 });
  const box = await canvas.boundingBox();
  const at = (fx, fy) => owner.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
  await at(0.25, 0.7); // signature tool is selected first
  await owner.getByRole("button", { name: "Date signed" }).click();
  await at(0.25, 0.78);
  await owner.getByRole("button", { name: "Text", exact: true }).click();
  await at(0.65, 0.78);
  await owner.getByLabel("Field label").fill("Job title");
  await owner.getByRole("button", { name: /Alan Turing/ }).click();
  await owner.getByRole("button", { name: "Signature", exact: true }).click();
  await at(0.65, 0.7);
  await owner.screenshot({ path: path.join(OUT, "esign-fields.png") });
  await owner.getByRole("button", { name: "Send to 2 people" }).click();
  await owner.getByText("Sent. Everyone gets an email").waitFor();
  await owner.getByText("Not yet sent").waitFor(); // Alan waits for Grace
});

await step("first signer signs without an account", async () => {
  const grace = await newPage();
  await grace.goto(linkFor("grace@example.com"));
  await grace.getByText("Signing as Grace Hopper").waitFor();
  await grace.locator("img[alt='Page 1']").waitFor({ timeout: 20_000 });
  assert.ok(await grace.getByRole("button", { name: "Finish signing" }).isHidden(), "finish waits for every field");
  await grace.getByRole("button", { name: "Signature" }).first().click();
  await grace.getByRole("button", { name: "Type" }).click();
  await grace.getByPlaceholder("Type your name").fill("Grace Hopper");
  await grace.getByRole("button", { name: "Use this signature" }).click();
  await grace.getByLabel("Job title").fill("Rear Admiral");
  await grace.getByRole("checkbox", { name: /I agree to sign/ }).check();
  await grace.screenshot({ path: path.join(OUT, "esign-signer.png") });
  await grace.getByRole("button", { name: "Finish signing" }).click();
  await grace.getByText("Thanks, you've signed").waitFor();
});

await step("second signer gets their link only now, and signs", async () => {
  const alan = await newPage();
  await alan.goto(linkFor("alan@example.com"));
  await alan.locator("img[alt='Page 1']").waitFor({ timeout: 20_000 });
  await alan.getByRole("button", { name: "Signature" }).first().click();
  const pad = alan.locator("canvas").last();
  const b = await pad.boundingBox();
  await alan.mouse.move(b.x + 40, b.y + 100);
  await alan.mouse.down();
  for (const [x, y] of [[120, 40], [200, 110], [300, 50]]) await alan.mouse.move(b.x + x, b.y + y, { steps: 5 });
  await alan.mouse.up();
  await alan.getByRole("button", { name: "Use this signature" }).click();
  await alan.getByRole("checkbox", { name: /I agree to sign/ }).check();
  await alan.getByRole("button", { name: "Finish signing" }).click();
  await alan.getByText("Thanks, you've signed").waitFor();
});

await step("owner sees it completed and downloads the sealed copy", async () => {
  await owner.reload();
  await owner.getByText("Completed and sealed").waitFor();
  await owner.screenshot({ path: path.join(OUT, "esign-done.png") });
  const res = await owner.request.get(owner.url().replace(/\/esign\/([\w-]+).*/, "/api/esign/requests/$1/document"));
  assert.equal(res.status(), 200);
  const { writeFileSync } = await import("node:fs");
  writeFileSync(path.join(OUT, "esign-signed.pdf"), await res.body());
  await owner.goto(`${BASE}/esign`);
  await owner.getByText("1 of 3 used this month").waitFor();
});

assert.deepEqual(errors, [], `page errors: ${errors.join("\n")}`);
await browser.close();
console.log("All eSign checks passed.");
