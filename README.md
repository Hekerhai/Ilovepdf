# Folio

Every PDF tool in one place: private by default, fast, and open-source underneath. Folio covers the iLovePDF,
Sejda and Smallpdf toolsets (59 tools), runs the common ones entirely in the browser so files never leave the
device, chains tools into reusable workflows, and adds what those products sell around the tools: eSign requests
with an audit trail, a document library with share links, a full PDF reader, imports from links and cloud
drives, a browser extension, accounts, paid plans, team workspaces and a public developer API with webhooks.

"Folio" is a working name. See [docs/RESEARCH.md](docs/RESEARCH.md) for the competitive research, the feature
matrix and the architecture.

## Quick start

```bash
cp .env.example .env        # set SECRET_KEY at minimum
docker compose up --build
```

Then open <http://localhost>. Magic-link emails land in Mailpit at <http://localhost:8025>, and the API docs are
at <http://localhost/api/docs>.

For a public deployment, set `SITE_ADDRESS` to your domain (Caddy fetches HTTPS certificates), `PUBLIC_URL` to
`https://your-domain`, `COOKIE_SECURE=true`, and change every password in `.env`.

## What's in the box

| Service | Role |
|---|---|
| `caddy` | HTTPS and routing: `/api/*` and `/v1/*` to the API, everything else to the web app |
| `web` | Next.js 15 app (responsive, installable PWA) |
| `api` | FastAPI: tools, jobs, accounts, billing, teams, workflows, public API |
| `worker` (x2) | RQ workers that run server-side tools |
| `janitor` | Deletes expired files and jobs every few minutes (GDPR auto-delete) |
| `postgres`, `redis` | Data and job queue. Files sit on a shared volume, or in S3/R2/B2 with `STORAGE_BACKEND=s3` |
| `gotenberg` | LibreOffice and Chromium for Office and HTML conversions |
| `mailpit` | Development SMTP inbox; point `SMTP_*` at a real provider in production |

### Tools

- **Organize:** merge, split (ranges, every N pages, by size, by bookmarks), split in half, split by text, remove,
  extract, organize (reorder, rotate, insert blank pages, combine files), rotate, flip, alternate and mix, N-up,
  resize, rename by content.
- **Optimize:** compress (never returns a bigger file), repair, grayscale, OCR (searchable PDF), deskew,
  accessibility check (report plus a fixed copy with title, language and display settings).
- **Convert to PDF:** images, scan (camera photo cleanup), Word, PowerPoint, Excel (including Pages, Keynote,
  Numbers, WPD and WPS), HTML/URL, ebooks (EPUB, MOBI, FB2, XPS, CBZ), and ZIP (every file inside, merged).
- **Convert from PDF:** images, Word, PowerPoint, Excel, text, Markdown, PDF/A, extract images.
- **Edit:** full editor (text, images, shapes, drawing, whiteout), annotate (sticky notes, highlight, underline,
  strike-out, text boxes, shapes, ink, with comments), watermark, page numbers, header and footer, Bates
  numbering, crop, metadata, bookmarks, delete annotations, flatten, sign, fill forms, create forms.
- **Security:** protect (AES-256), unlock, compare, redact (true removal by text, pattern or area), digital
  signatures (certificate-based) and signature verification.
- **AI:** summarize, translate, chat with a PDF, and generate quiz questions (Claude or any OpenAI-compatible
  model; off until a key is set).

Merge, split, remove, extract, rotate, organize, edit, sign, fill and create forms, scan, JPG to PDF and PDF to
JPG run on the device with pdf-lib and pdf.js when private mode is on. Everything else runs on the server, and
uploaded files are deleted after `FILE_TTL_HOURS` (2 by default) or straight away when the user clicks delete.

### Beyond the tools

- **eSign** (`/esign`): send a PDF to up to 20 people, in order or all at once, with signature, initials, date,
  name, text and checkbox fields. Optional access codes per signer, reminders, decline with a reason, reusable
  templates, the request ID printed on every page, and a sealed final copy (certified with a digital signature)
  with an audit-trail page. Signers need no account.
- **My documents** (`/documents`): keep results on purpose (500 MB free, 100 GB Pro, 1 TB Business), open them
  in any tool, and share with links that can have a password, an expiry date, a download limit or view-only mode,
  be sent by email, or be embedded on another site.
- **Reader** (`/reader`): a full PDF viewer with search, thumbnails, outline and zoom that runs on the device.
  The installed PWA opens PDFs from the desktop ("Open with") and from the share sheet on phones.
- **Imports:** every upload box also takes a link (Google Drive, Dropbox and OneDrive share links work), the
  Dropbox Chooser and the Google Drive Picker (when their keys are set), and My documents.
- **Browser extension** ([extension/](extension/)): "Open in Folio" from the toolbar or the right-click menu.
- **7-day pass:** one payment of $3 (₹199) for a week of Pro, for people who need it once.

### Plans

| | Guest | Free | Pro | Business |
|---|---|---|---|---|
| Price | – | – | $6/mo or $48/yr (₹399 / ₹3,199) | $5 per seat per month, 3 seats minimum (₹349) |
| File size | 25 MB | 50 MB | 1 GB | 2 GB |
| Files per task | 5 | 10 | 200 | 500 |
| Tasks per day | 10 | 25 | Unlimited | Unlimited |
| Premium tools, workflows | – | – | Yes | Yes |
| Signature requests / month | – | 3 | Unlimited | Unlimited |
| Document storage | – | 500 MB | 100 GB | 1 TB |
| API credits / month | – | 250 | 1,000 | 5,000 |
| Team workspace | – | – | – | Yes |

Plans live in [backend/app/plans.py](backend/app/plans.py); prices are sent to Stripe inline, so no products
need creating in the Stripe dashboard. Razorpay plans are created on first checkout.

## Configuration

All settings are environment variables; [.env.example](.env.example) lists them with comments.

- **Payments:** set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`, and/or the three `RAZORPAY_*` keys. Webhook
  URLs are `/api/billing/webhooks/stripe` and `/api/billing/webhooks/razorpay`. Checkout shows only the gateways
  that are configured.
- **Google sign-in:** set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, with redirect URI
  `${PUBLIC_URL}/api/auth/google/callback`. Email + password and magic links work without it.
- **AI:** `AI_PROVIDER=anthropic` with `AI_API_KEY`, or `AI_PROVIDER=openai` with `AI_BASE_URL` for any
  OpenAI-compatible server (including a local Ollama).
- **Email:** `SMTP_*` and `MAIL_FROM`.
- **Cloud pickers:** `DROPBOX_APP_KEY` for the Dropbox Chooser; `GOOGLE_PICKER_API_KEY` and `GOOGLE_APP_ID`
  (with `GOOGLE_CLIENT_ID`) for the Google Drive Picker. Restrict both keys to your domain. Files picked from
  Google Drive download straight into the browser; links are fetched by the API, which needs direct outbound
  internet and DNS, and refuses private addresses.

## Developer API

Create a key under **Account → API keys**, then:

```bash
curl -H "Authorization: Bearer fk_live_..." -F files=@a.pdf -F files=@b.pdf \
     -F tool=merge -F 'options={"add_bookmarks":true}' https://your-domain/v1/jobs
# → {"id": "...", "status": "queued"}
curl -H "Authorization: Bearer fk_live_..." https://your-domain/v1/jobs/<id>
curl -H "Authorization: Bearer fk_live_..." -o merged.pdf https://your-domain/v1/jobs/<id>/download
```

To chain tools in one task, send `steps` instead of `tool`, e.g.
`-F 'steps=[{"tool":"merge"},{"tool":"compress","options":{"level":"extreme"}}]'`. Each task costs one credit. The full reference is at
`/developers` in the web app and the OpenAPI schema at `/api/docs`.

Add `-F webhook_url=https://...` to be told when a task finishes instead of polling. Each call is signed: the
`Folio-Signature` header is `t=<unix time>,v1=<hex HMAC-SHA256 of "t.body">` with the secret from
`GET /v1/webhooks/secret`. `POST /v1/forms/fields` lists a PDF's form fields, so you can fill them with
`fill_forms`.

## Architecture

The backend follows SOLID with ports and adapters:

- Each tool is one class implementing `Tool` ([backend/app/tools/base.py](backend/app/tools/base.py)) and
  registers itself with `@register`. Adding a tool means adding a class; nothing else changes (open/closed).
- Infrastructure sits behind ports in [backend/app/domain/ports.py](backend/app/domain/ports.py): `FileStorage`,
  `JobQueue`, `DocumentConverter`, `AIProvider`, `Mailer`, `PaymentGateway`. Adapters live in `app/infra`, and
  [backend/app/container.py](backend/app/container.py) is the only place that wires them.
- Services (`app/services`) hold the business rules: quotas, jobs, auth, teams, billing, privacy.

The frontend mirrors it: a `ProcessingEngine` interface with `BrowserEngine` and `ServerEngine`, chosen per run
by `chooseEngine`. Tool option forms are generated from each tool's JSON schema, exported from the backend into
`frontend/src/lib/tools.generated.json`.

## Development

```bash
# Backend (needs ghostscript, qpdf, tesseract-ocr and libreoffice for the full tool set)
cd backend && pip install -r requirements-dev.txt
pytest && ruff check .
QUEUE_MODE=inline uvicorn app.main:app --reload       # no Redis needed in inline mode

# After changing a database model, add a migration (applied automatically on start)
python -m app.migrations new "describe the change"

# After changing a tool's options, refresh the frontend catalog
python -m app.tools.export > ../frontend/src/lib/tools.generated.json

# Frontend
cd frontend && npm install
npm run dev        # proxies /api to API_URL (default http://localhost:8000)
npm test && npm run build

# Browser tests against a running stack (signing links are read from the API log, where the dev mailer prints)
node e2e/smoke.mjs http://localhost <fixtures-dir> <screenshots-dir>
node e2e/features.mjs http://localhost <fixtures-dir> <out-dir>
node e2e/esign.mjs http://localhost <fixtures-dir> <out-dir> <api-log>
node e2e/parity.mjs http://localhost <fixtures-dir> <out-dir> <api-log>
```

CI (`.github/workflows/ci.yml`) runs lint, the backend and frontend tests, a production build and
`docker compose build` on every push and pull request. A test fails if a model changes without a migration.

## Licensing notes

Folio's own code can carry any license you choose, but two dependencies are AGPL-3.0:

- **Ghostscript** (compress, grayscale, PDF/A) runs as a separate process, which is generally treated as
  aggregation, not linking.
- **PyMuPDF** (used by PDF to Word via pdf2docx, redact, annotate, ebook to PDF and ZIP to PDF) is imported
  in-process. Running it as a hosted service means either releasing Folio's source under the AGPL or buying
  Artifex's commercial license. The imports are isolated in those tools, so they can be swapped out.

Everything else (pikepdf/qpdf, pypdfium2, pdfplumber, OCRmyPDF, Tesseract, LibreOffice via Gotenberg, pdf-lib,
pdf.js) is under permissive or weak-copyleft licenses. Details are in [docs/RESEARCH.md](docs/RESEARCH.md).
