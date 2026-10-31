# Open in Folio (browser extension)

A small Manifest V3 extension for Chrome, Edge, Brave and other Chromium browsers.

- **Toolbar button** – when the tab shows a PDF, open it in Folio's reader or a tool (compress, PDF to Word, edit,
  annotate, sign, OCR, summarize).
- **Right-click menu** – "Open in Folio" on any link or page, with the same tools.
- **Settings** – the address of your Folio install (default `http://localhost:3000`).

The extension only opens `<folio>/tools/<tool>?import=<link>`. Folio's server fetches the link (refusing private
addresses), so the PDF must be publicly reachable; files behind a login or on `file://` can be opened with the
reader's file picker instead. It asks for no host permissions and reads nothing from the pages you visit.

## Install for development

1. Open `chrome://extensions` and turn on **Developer mode**.
2. **Load unpacked** and choose this `extension/` folder.

## Publish

Zip the folder's contents (`cd extension && zip -r ../folio-extension.zip .`) and upload it to the Chrome Web Store
developer dashboard. Change `DEFAULT_BASE` in `shared.js` to your public address first.
