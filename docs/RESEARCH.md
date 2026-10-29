# Product research: iLovePDF + Sejda → Folio

Working name: **Folio** (configurable via `BRAND_NAME` / `NEXT_PUBLIC_BRAND_NAME`).
Other name candidates: **Pagewise**, **Inkwell**, **Plyo**. Domain availability not checked.

## 1. What the incumbents offer

### iLovePDF (ilovepdf.com)
| Category | Tools |
|---|---|
| Organize | Merge, Split, Remove pages, Extract pages, Organize, Scan to PDF |
| Optimize | Compress, Repair, OCR |
| Convert to PDF | JPG, Word, PowerPoint, Excel, HTML |
| Convert from PDF | JPG, Word, PowerPoint, Excel, PDF/A |
| Edit | Rotate, Page numbers, Watermark, Crop, Edit PDF, PDF Forms |
| Security | Unlock, Protect, Sign, Redact, Compare |
| Intelligence | AI Summarizer, Translate, PDF to Markdown |

Around the tools: Premium and Business plans, desktop (Mac/Windows) and mobile apps, iLoveAPI (developer API),
iLoveSign (e-signature), integrations (Zapier, Make, WordPress), and processed files deleted after ~2 hours.

### Sejda (sejda.com)
Adds to the above: Alternate & Mix, Split by bookmarks / in half / by size / by text, Fill & Sign, Create forms,
Deskew, Flatten, PDF to Text, Bates numbering, Create bookmarks, Edit metadata, Extract images, Flip, Grayscale,
Header & Footer, N-up, Rename, Resize, Delete annotations, and **Workflows** (chain tools).
Sejda sells a 7-day pass (one-time) plus web and desktop subscriptions; files deleted after processing.

## 2. What "better" means here (from CC)
1. **Faster**: page-level tools run in the browser (no upload, no queue), server tools run on a Redis queue
   with horizontally scalable workers.
2. **More private**: in-browser processing where possible; server files auto-deleted after `FILE_TTL_HOURS`
   (default 2); no third-party trackers; GDPR export/delete endpoints.
3. **Cleaner UI**: one consistent tool page driven by tool metadata, drag-and-drop, live page thumbnails.
4. **Batch workflows**: chain any server tools (e.g. OCR → compress → watermark → protect) and save the chain.
5. **More tools**: the union of iLovePDF + Sejda (~60 tools), see matrix below.

## 3. Feature matrix (v1 = this build, v2 = next)

Legend: **B** = runs in browser, **S** = runs on server worker. ★ = premium only.

| Tool | Where | Engine (open source) | Release |
|---|---|---|---|
| Merge | B + S | pdf-lib / pikepdf (qpdf) | v1 |
| Split by ranges / every N pages | B + S | pdf-lib / pikepdf | v1 |
| Split by size, by bookmarks, in half | S | pikepdf | v1 |
| Remove pages, Extract pages | B + S | pdf-lib / pikepdf | v1 |
| Organize (reorder / rotate / delete visually) | B + S | pdf-lib / pikepdf | v1 |
| Rotate, Flip | B + S | pdf-lib / pikepdf | v1 |
| Alternate & Mix | S | pikepdf | v1 |
| N-up, Resize, Crop | S | pikepdf | v1 |
| Compress (3 levels) | S | Ghostscript | v1 |
| Grayscale | S | Ghostscript | v1 |
| Repair | S | qpdf / pikepdf | v1 |
| OCR ★, Deskew ★ | S | OCRmyPDF + Tesseract | v1 |
| JPG/PNG → PDF, Scan to PDF | B + S | pdf-lib / img2pdf | v1 |
| Word / PowerPoint / Excel → PDF | S | LibreOffice (via Gotenberg) | v1 |
| HTML / URL → PDF | S | Chromium (via Gotenberg) | v1 |
| PDF → JPG / PNG | B + S | pdf.js / pypdfium2 | v1 |
| PDF → Word ★ | S | pdf2docx | v1 |
| PDF → PowerPoint ★ | S | pypdfium2 + python-pptx | v1 |
| PDF → Excel ★ | S | pdfplumber + openpyxl | v1 |
| PDF → Text, PDF → Markdown | S | pdfplumber | v1 |
| PDF → PDF/A ★ | S | Ghostscript / OCRmyPDF | v1 |
| Extract images | S | pikepdf | v1 |
| Watermark (text / image) | S | reportlab overlay + pikepdf | v1 |
| Page numbers, Header & Footer, Bates numbering | S | reportlab overlay + pikepdf | v1 |
| Edit metadata, Create bookmarks, Delete annotations, Flatten | S | pikepdf | v1 |
| Protect (AES-256 + permissions), Unlock | S | pikepdf (qpdf) | v1 |
| Sign (draw / type / image, placed visually) | S | reportlab + pikepdf | v1 |
| Digital certificate signature ★ | S | pyHanko | v2 |
| Compare (text diff) ★ | S | pdfplumber + difflib | v1 |
| Redact (true content removal) ★ | S | PyMuPDF | v2 |
| Edit PDF (text/shape editor), Fill forms, Create forms | B | pdf-lib + pdf.js | v2 |
| AI summarize / translate / chat ★ | S | pluggable provider (Claude, OpenAI-compatible, none) | v1 scaffold, needs key |
| Workflows (chain tools) ★ | S | built-in pipeline runner | v1 |

## 4. Plans and limits (proposal; all values are config, not code)

| | Guest | Free (account) | Pro | Business | API |
|---|---|---|---|---|---|
| Price (USD) | 0 | 0 | $6/mo, $48/yr | $5/seat/mo (min 3) | 250 free credits/mo, then $0.01/credit |
| Price (INR, Razorpay) | 0 | 0 | ₹399/mo, ₹3,199/yr | ₹349/seat/mo | same, in INR |
| Max file size | 25 MB | 50 MB | 1 GB | 2 GB | 1 GB |
| Files per task | 5 | 10 | 200 | 500 | 200 |
| Server tasks / day | 10 | 25 | unlimited (fair use) | unlimited | by credits |
| Premium tools ★ | – | – | ✓ | ✓ | ✓ |
| Saved workflows | – | – | 20 | unlimited, shared in team | via API |
| Team workspace | – | – | – | ✓ | – |

For reference, iLovePDF Premium and Sejda Web are both around $7/month on monthly billing (check their pricing pages
before launch), so Pro undercuts both. In-browser tools never count against quotas because they cost nothing to run.

## 5. Open-source stack

| Concern | Choice | License |
|---|---|---|
| Web app / PWA | Next.js + TypeScript + Tailwind | MIT |
| In-browser PDF | pdf-lib, pdf.js | MIT, Apache-2.0 |
| API | FastAPI (Python) | MIT |
| Queue / workers | Redis + RQ | BSD |
| DB | PostgreSQL + SQLAlchemy | PostgreSQL, MIT |
| Object storage | Local disk volume, or any S3 API (AWS S3, R2, B2) | Permissive (MinIO dropped: its public Docker images are no longer available) |
| PDF core | qpdf/pikepdf, pypdfium2, Ghostscript, OCRmyPDF + Tesseract | Apache/MPL/BSD, AGPL (Ghostscript CLI), MPL |
| Office/HTML → PDF | Gotenberg (LibreOffice + Chromium) | MIT |
| Email (dev) | Mailpit | MIT |

**License watch-outs**
- Ghostscript is AGPL; we only call it as a separate CLI process (no linking), which is the common SaaS setup.
  Artifex sells a commercial license if you want zero ambiguity.
- pdf2docx depends on PyMuPDF (AGPL). If the platform stays closed-source, buy a PyMuPDF commercial license or swap
  the `PdfToWord` engine (it sits behind an interface, so the swap is one class).

## 6. Architecture (SOLID)

```
frontend (Next.js PWA) ──/api──▶ api (FastAPI) ──▶ Postgres
      │  in-browser engines          │  enqueue
      ▼  (pdf-lib, pdf.js)           ▼
   user's device               Redis ──▶ worker(s) ──▶ engines (qpdf, gs, ocrmypdf, gotenberg…)
                                     │                    │
                                     └──── storage (local / S3) ◀─┘
                    janitor: deletes expired files every few minutes
```

- **S**ingle responsibility: each tool is one class; engines (Ghostscript, Gotenberg…) are adapters; billing,
  quotas, storage, auth are separate services.
- **O**pen/closed: new tools register themselves in the `ToolRegistry`; nothing else changes.
- **L**iskov: every tool implements the same `Tool` contract (options model + `run(ctx)`), so workflows can chain any of them.
- **I**nterface segregation: small ports (`FileStorage`, `JobQueue`, `PaymentGateway`, `AIProvider`, `DocumentConverter`).
- **D**ependency inversion: services depend on ports; concrete adapters are wired in one container (`app/container.py`)
  from settings.
