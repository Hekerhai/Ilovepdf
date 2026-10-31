// Shared by the popup and the background worker.
export const DEFAULT_BASE = "http://localhost:3000";

export const TOOLS = [
  { id: "reader", title: "Read", path: "/reader" },
  { id: "compress", title: "Compress", path: "/tools/compress" },
  { id: "pdf_to_word", title: "PDF to Word", path: "/tools/pdf_to_word" },
  { id: "edit_pdf", title: "Edit", path: "/tools/edit_pdf" },
  { id: "annotate_pdf", title: "Annotate", path: "/tools/annotate_pdf" },
  { id: "sign", title: "Sign", path: "/tools/sign" },
  { id: "ocr", title: "OCR", path: "/tools/ocr" },
  { id: "ai_summarize", title: "Summarize with AI", path: "/tools/ai_summarize" },
];

export async function base() {
  const { base } = await chrome.storage.sync.get("base");
  return (base || DEFAULT_BASE).replace(/\/+$/, "");
}

/** Folio fetches the link itself (blocking private addresses), so only public links work. */
export async function openIn(toolPath, link) {
  const url = `${await base()}${toolPath}?import=${encodeURIComponent(link)}`;
  await chrome.tabs.create({ url });
}

export const looksLikePdf = (url) => /^https?:/i.test(url || "") && /\.pdf($|[?#])/i.test(new URL(url).pathname + new URL(url).search);
