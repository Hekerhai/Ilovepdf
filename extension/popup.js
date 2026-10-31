import { base, DEFAULT_BASE, looksLikePdf, openIn, TOOLS } from "./shared.js";

const target = document.getElementById("target");
const grid = document.getElementById("tools");
const input = document.getElementById("base");

const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
const url = tab?.url || "";
const usable = /^https?:/i.test(url);
target.textContent = !usable
  ? "Open a PDF on the web, or right-click a PDF link."
  : looksLikePdf(url)
    ? `This PDF: ${decodeURIComponent(new URL(url).pathname.split("/").pop())}`
    : "This page isn't a PDF. Right-click a PDF link instead.";

for (const tool of TOOLS) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = tool.title;
  button.disabled = !usable || !looksLikePdf(url);
  button.addEventListener("click", () => openIn(tool.path, url).then(() => window.close()));
  grid.appendChild(button);
}

input.value = await base();
document.getElementById("save").addEventListener("click", async () => {
  const value = input.value.trim() || DEFAULT_BASE;
  try {
    new URL(value);
  } catch {
    input.setCustomValidity("Enter a full address, like https://pdf.example.com");
    return input.reportValidity();
  }
  await chrome.storage.sync.set({ base: value });
  window.close();
});
