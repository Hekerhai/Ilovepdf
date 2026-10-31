/** Bring files in from somewhere other than the device: a link, Dropbox, Google Drive. */
import { ApiError } from "./api";

/** Fetch a public link (or a Drive, Dropbox or OneDrive share link) through the server, which blocks private addresses. */
export async function fromUrl(url: string): Promise<File> {
  const res = await fetch("/api/import/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    credentials: "same-origin",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body?.error?.message ?? `Import failed (${res.status})`, res.status, body?.error?.code ?? "error");
  }
  const name = decodeURIComponent(res.headers.get("x-file-name") ?? "download");
  const blob = await res.blob();
  return new File([blob], name, { type: blob.type });
}

const scripts = new Map<string, Promise<void>>();
function loadScript(src: string, attrs: Record<string, string> = {}): Promise<void> {
  if (!scripts.has(src)) {
    scripts.set(
      src,
      new Promise((resolve, reject) => {
        const el = document.createElement("script");
        el.src = src;
        el.async = true;
        Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
        el.onload = () => resolve();
        el.onerror = () => (scripts.delete(src), reject(new Error(`Couldn't load ${new URL(src).hostname}. Check your connection or ad blocker.`)));
        document.head.appendChild(el);
      }),
    );
  }
  return scripts.get(src)!;
}

type DropboxFile = { link: string; name: string; bytes: number };
declare global {
  interface Window {
    Dropbox?: { choose(options: { success(files: DropboxFile[]): void; cancel?(): void; linkType: "direct" | "preview"; multiselect: boolean; extensions?: string[] }): void };
    gapi?: { load(name: string, cb: () => void): void };
    google?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  }
}

/** Dropbox Chooser. Returns direct links, which the server fetches (they aren't fetchable cross-origin everywhere). */
export async function pickDropbox(appKey: string, opts: { multiple: boolean; extensions: string[] }): Promise<File[]> {
  await loadScript("https://www.dropbox.com/static/api/2/dropins.js", { id: "dropboxjs", "data-app-key": appKey });
  const picked = await new Promise<DropboxFile[]>((resolve) =>
    window.Dropbox!.choose({ linkType: "direct", multiselect: opts.multiple, extensions: opts.extensions, success: resolve, cancel: () => resolve([]) }),
  );
  const files: File[] = [];
  for (const f of picked) {
    const file = await fromUrl(f.link);
    files.push(new File([file], f.name, { type: file.type }));
  }
  return files;
}

const GOOGLE_EXPORT: Record<string, [string, string]> = {
  "application/vnd.google-apps.document": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"],
  "application/vnd.google-apps.spreadsheet": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"],
  "application/vnd.google-apps.presentation": ["application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"],
  "application/vnd.google-apps.drawing": ["application/pdf", ".pdf"],
};

/**
 * Google Drive Picker. Files are downloaded straight from Google into the browser with a short-lived token that can
 * only see the files the user picked (drive.file scope), so nothing passes through our server unless a tool needs it.
 */
export async function pickGoogleDrive(cfg: { client_id: string; api_key: string; app_id: string | null }, opts: { multiple: boolean }): Promise<File[]> {
  await Promise.all([loadScript("https://apis.google.com/js/api.js"), loadScript("https://accounts.google.com/gsi/client")]);
  await new Promise<void>((resolve) => window.gapi!.load("picker", resolve));
  const g = window.google;
  const token = await new Promise<string>((resolve, reject) => {
    const client = g.accounts.oauth2.initTokenClient({
      client_id: cfg.client_id,
      scope: "https://www.googleapis.com/auth/drive.file",
      callback: (r: { access_token?: string; error?: string }) => (r.access_token ? resolve(r.access_token) : reject(new Error(r.error ?? "Google sign-in was cancelled."))),
    });
    client.requestAccessToken();
  });
  const docs: { id: string; name: string; mimeType: string }[] = await new Promise((resolve) => {
    const builder = new g.picker.PickerBuilder()
      .addView(new g.picker.DocsView().setIncludeFolders(false))
      .setOAuthToken(token)
      .setDeveloperKey(cfg.api_key)
      .setCallback((data: { action: string; docs?: { id: string; name: string; mimeType: string }[] }) => {
        if (data.action === g.picker.Action.PICKED) resolve(data.docs ?? []);
        else if (data.action === g.picker.Action.CANCEL) resolve([]);
      });
    if (cfg.app_id) builder.setAppId(cfg.app_id);
    if (opts.multiple) builder.enableFeature(g.picker.Feature.MULTISELECT_ENABLED);
    builder.build().setVisible(true);
  });
  const files: File[] = [];
  for (const d of docs) {
    const exported = GOOGLE_EXPORT[d.mimeType];
    const url = exported
      ? `https://www.googleapis.com/drive/v3/files/${d.id}/export?mimeType=${encodeURIComponent(exported[0])}`
      : `https://www.googleapis.com/drive/v3/files/${d.id}?alt=media`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new Error(`Google Drive couldn't send “${d.name}” (${res.status}).`);
    const name = exported && !d.name.toLowerCase().endsWith(exported[1]) ? d.name + exported[1] : d.name;
    files.push(new File([await res.blob()], name, { type: exported?.[0] ?? d.mimeType }));
  }
  return files;
}
