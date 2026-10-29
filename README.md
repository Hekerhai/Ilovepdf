# Folio

Every PDF tool in one place: private by default, fast, and open-source underneath. Folio covers the full
iLovePDF and Sejda toolset (46 tools), runs the common ones entirely in the browser so files never leave the
device, chains tools into reusable workflows, and ships with accounts, paid plans, team workspaces and a public
developer API.

"Folio" is a working name. See [docs/RESEARCH.md](docs/RESEARCH.md) for the alternatives, the competitive
research, the feature matrix and the architecture.

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
| `postgres`, `redis`, `minio` | Data, queue, file storage (S3-compatible) |
| `gotenberg` | LibreOffice and Chromium for Office and HTML conversions |
| `mailpit` | Development SMTP inbox; point `SMTP_*` at a real provider in production |

### Tools

- **Organize:** merge, split (ranges, every N pages, by size, by bookmarks), split in half, remove, extract,
  organize (reorder, rotate, insert blank pages, combine files), rotate, flip, alternate and mix, N-up, resize.
- **Optimize:** compress (never returns a bigger file), repair, grayscale, OCR (searchable PDF), deskew.
- **Convert to PDF:** images, Word, PowerPoint, Excel, HTML/URL.
- **Convert from PDF:** images, Word, PowerPoint, Excel, text, Markdown, PDF/A, extract images.
- **Edit:** watermark (text or image), page numbers, header and footer, Bates numbering, crop, metadata,
  bookmarks, delete annotations, flatten, sign (draw, type or upload).
- **Security:** protect (AES-256), unlock, compare, redact (true removal by text, pattern or area).
- **AI:** summarize, translate, chat with a PDF (Claude or any OpenAI-compatible model; off until a key is set).

Merge, split, remove, extract, rotate, organize, JPG to PDF and PDF to JPG run on the device with pdf-lib and
pdf.js when private mode is on. Everything else runs on the server, and uploaded files are deleted after
`FILE_TTL_HOURS` (2 by default) or straight away when the user clicks delete.

### Plans

| | Guest | Free | Pro | Business |
|---|---|---|---|---|
| Price | – | – | $6/mo or $48/yr (₹399 / ₹3,199) | $5 per seat per month, 3 seats minimum (₹349) |
| File size | 25 MB | 50 MB | 1 GB | 2 GB |
| Files per task | 5 | 10 | 200 | 500 |
| Tasks per day | 10 | 25 | Unlimited | Unlimited |
| Premium tools, workflows | – | – | Yes | Yes |
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

# After changing a tool's options, refresh the frontend catalog
python -m app.tools.export > ../frontend/src/lib/tools.generated.json

# Frontend
cd frontend && npm install
npm run dev        # proxies /api to API_URL (default http://localhost:8000)
npm test && npm run build

# End-to-end smoke test against a running stack
node e2e/smoke.mjs http://localhost <fixtures-dir> <screenshots-dir>
```

## Licensing notes

Folio's own code can carry any license you choose, but two dependencies are AGPL-3.0:

- **Ghostscript** (compress, grayscale, PDF/A) runs as a separate process, which is generally treated as
  aggregation, not linking.
- **PyMuPDF** (used by PDF to Word via pdf2docx, and by redact) is imported in-process. Running it as a hosted
  service means either releasing Folio's source under the AGPL or buying Artifex's commercial license. The
  imports are isolated in those two tools, so they can be swapped out.

Everything else (pikepdf/qpdf, pypdfium2, pdfplumber, OCRmyPDF, Tesseract, LibreOffice via Gotenberg, pdf-lib,
pdf.js) is under permissive or weak-copyleft licenses. Details are in [docs/RESEARCH.md](docs/RESEARCH.md).
