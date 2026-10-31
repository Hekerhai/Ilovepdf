"use client";

import "pdfjs-dist/web/pdf_viewer.css";

import { ChevronDown, ChevronUp, Download, List, LayoutGrid, Minus, Plus, RotateCw, Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { loadPdfjs } from "@/lib/pdfjs";

type Viewer = import("pdfjs-dist/web/pdf_viewer.mjs").PDFViewer;
type Bus = import("pdfjs-dist/web/pdf_viewer.mjs").EventBus;
type Doc = Awaited<ReturnType<Awaited<ReturnType<typeof loadPdfjs>>["getDocument"]>["promise"]>;
type OutlineItem = { title: string; dest: unknown; items: OutlineItem[] };
type Panel = "thumbs" | "outline" | null;

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

/**
 * A full PDF reader that runs entirely in the browser: scrolling pages, selectable text, working links, search with
 * highlights, zoom, rotation, thumbnails and the document outline.
 */
export function PdfViewer({
  data,
  name,
  onDownload,
  compact = false,
  className = "",
}: {
  data: ArrayBuffer;
  name: string;
  onDownload?: () => void;
  compact?: boolean;
  className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const viewerEl = useRef<HTMLDivElement>(null);
  const viewer = useRef<Viewer | null>(null);
  const bus = useRef<Bus | null>(null);
  const linkService = useRef<{ goToDestination: (d: string | unknown[]) => unknown } | null>(null);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsPassword, setNeedsPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [scale, setScale] = useState(1);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<{ current: number; total: number } | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
  const [outline, setOutline] = useState<OutlineItem[]>([]);

  const open = useCallback(
    async (pw?: string) => {
      setError(null);
      try {
        const pdfjs = await loadPdfjs();
        // The viewer module reads the core library from this global.
        (globalThis as unknown as { pdfjsLib: typeof pdfjs }).pdfjsLib = pdfjs;
        const { EventBus, PDFViewer: ViewerClass, PDFLinkService, PDFFindController } = await import("pdfjs-dist/web/pdf_viewer.mjs");
        const loaded = await pdfjs.getDocument({ data: new Uint8Array(data.slice(0)), password: pw }).promise;
        if (!container.current || !viewerEl.current) return;
        const eventBus = new EventBus();
        const links = new PDFLinkService({ eventBus, externalLinkTarget: 2 /* new window */ });
        const find = new PDFFindController({ eventBus, linkService: links });
        const v = new ViewerClass({ container: container.current, viewer: viewerEl.current, eventBus, linkService: links, findController: find, removePageBorders: false });
        links.setViewer(v);
        eventBus.on("pagesinit", () => {
          v.currentScaleValue = compact ? "page-width" : "auto";
        });
        eventBus.on("pagechanging", (e: { pageNumber: number }) => setPage(e.pageNumber));
        eventBus.on("scalechanging", (e: { scale: number }) => setScale(e.scale));
        eventBus.on("updatefindmatchescount", (e: { matchesCount: { current: number; total: number } }) => setMatches(e.matchesCount));
        eventBus.on("updatefindcontrolstate", (e: { matchesCount: { current: number; total: number } }) => setMatches(e.matchesCount));
        v.setDocument(loaded);
        links.setDocument(loaded);
        viewer.current = v;
        bus.current = eventBus;
        linkService.current = links;
        setDoc(loaded);
        setPages(loaded.numPages);
        setNeedsPassword(false);
        loaded.getOutline().then((o) => setOutline((o as OutlineItem[] | null) ?? []));
      } catch (e) {
        const err = e as { name?: string; code?: number };
        if (err.name === "PasswordException") {
          setNeedsPassword(true);
          if (pw) setError("That password isn't right.");
        } else setError("This file couldn't be opened. It may be damaged or not a PDF.");
      }
    },
    [data, compact],
  );

  useEffect(() => {
    open();
    return () => {
      viewer.current?.setDocument(null as never);
      viewer.current = null;
      setDoc((d) => (d?.destroy(), null));
    };
  }, [open]);

  const search = (previous = false, again = true) => {
    if (!query.trim()) return setMatches(null);
    bus.current?.dispatch("find", { source: null, type: again ? "again" : "", query, caseSensitive: false, entireWord: false, highlightAll: true, findPrevious: previous, matchDiacritics: false });
  };

  const zoom = (dir: 1 | -1) => {
    const v = viewer.current;
    if (!v) return;
    const next = dir > 0 ? ZOOMS.find((z) => z > v.currentScale + 0.01) : [...ZOOMS].reverse().find((z) => z < v.currentScale - 0.01);
    if (next) v.currentScale = next;
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f" && doc) {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => document.getElementById("pdf-search")?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [doc]);

  return (
    <div className={`flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-white px-2 py-1.5 text-sm dark:border-slate-800 dark:bg-slate-950" role="toolbar" aria-label="Reader">
        {!compact && (
          <>
            <IconButton label="Thumbnails" active={panel === "thumbs"} onClick={() => setPanel(panel === "thumbs" ? null : "thumbs")} icon={<LayoutGrid className="h-4 w-4" />} />
            {outline.length > 0 && <IconButton label="Outline" active={panel === "outline"} onClick={() => setPanel(panel === "outline" ? null : "outline")} icon={<List className="h-4 w-4" />} />}
          </>
        )}
        <span className="flex items-center gap-1 px-1">
          <input
            aria-label="Page number"
            className="w-12 rounded border border-slate-300 bg-transparent px-1 py-0.5 text-center dark:border-slate-700"
            value={page}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (viewer.current && n >= 1 && n <= pages) viewer.current.currentPageNumber = n;
              setPage(n || page);
            }}
          />
          <span className="text-slate-500">/ {pages || "–"}</span>
        </span>
        <IconButton label="Zoom out" onClick={() => zoom(-1)} icon={<Minus className="h-4 w-4" />} />
        <button type="button" className="w-14 rounded px-1 py-1 text-center tabular-nums hover:bg-slate-100 dark:hover:bg-slate-800" title="Fit to width" onClick={() => viewer.current && (viewer.current.currentScaleValue = "page-width")}>
          {Math.round(scale * 100)}%
        </button>
        <IconButton label="Zoom in" onClick={() => zoom(1)} icon={<Plus className="h-4 w-4" />} />
        {!compact && <IconButton label="Rotate" onClick={() => viewer.current && (viewer.current.pagesRotation = (viewer.current.pagesRotation + 90) % 360)} icon={<RotateCw className="h-4 w-4" />} />}
        <span className="min-w-0 flex-1 truncate px-2 text-slate-500" title={name}>
          {name}
        </span>
        {searchOpen ? (
          <form
            className="flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              search(false, false);
            }}
          >
            <input id="pdf-search" className="w-40 rounded border border-slate-300 bg-transparent px-2 py-0.5 dark:border-slate-700" placeholder="Search" aria-label="Search in document" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && e.shiftKey && (e.preventDefault(), search(true))} />
            <span className="w-16 text-xs text-slate-500" aria-live="polite">
              {matches ? (matches.total ? `${matches.current} of ${matches.total}` : "No results") : ""}
            </span>
            <IconButton label="Previous result" onClick={() => search(true)} icon={<ChevronUp className="h-4 w-4" />} />
            <IconButton label="Next result" onClick={() => search(false)} icon={<ChevronDown className="h-4 w-4" />} />
            <IconButton label="Close search" onClick={() => (setSearchOpen(false), setQuery(""), setMatches(null), bus.current?.dispatch("find", { type: "", query: "", highlightAll: false }))} icon={<X className="h-4 w-4" />} />
          </form>
        ) : (
          <IconButton label="Search" onClick={() => (setSearchOpen(true), setTimeout(() => document.getElementById("pdf-search")?.focus(), 0))} icon={<Search className="h-4 w-4" />} />
        )}
        {onDownload && <IconButton label="Download" onClick={onDownload} icon={<Download className="h-4 w-4" />} />}
      </div>
      <div className="relative flex min-h-0 flex-1">
        {panel && doc && (
          <aside className="w-44 shrink-0 overflow-y-auto border-r border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
            {panel === "thumbs" ? (
              <Thumbnails doc={doc} current={page} onPick={(n) => viewer.current && (viewer.current.currentPageNumber = n)} />
            ) : (
              <OutlineTree items={outline} onPick={(dest) => linkService.current?.goToDestination(dest as string | unknown[])} />
            )}
          </aside>
        )}
        <div className="relative min-w-0 flex-1">
          <div ref={container} className="absolute inset-0 overflow-auto" data-testid="pdf-viewer">
            <div ref={viewerEl} className="pdfViewer" />
          </div>
          {(error || needsPassword) && (
            <div className="absolute inset-0 flex items-center justify-center p-6">
              <div className="card w-full max-w-sm space-y-3 p-5 text-center text-sm">
                {needsPassword ? (
                  <form
                    className="space-y-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      open(password);
                    }}
                  >
                    <p className="font-medium">This PDF is password protected</p>
                    <input type="password" className="input" aria-label="PDF password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
                    {error && <p className="text-rose-600">{error}</p>}
                    <button className="btn-primary w-full">Open</button>
                  </form>
                ) : (
                  <p className="text-rose-600">{error}</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function IconButton({ label, icon, onClick, active }: { label: string; icon: React.ReactNode; onClick: () => void; active?: boolean }) {
  return (
    <button type="button" title={label} aria-label={label} aria-pressed={active} onClick={onClick} className={`rounded p-1.5 ${active ? "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}>
      {icon}
    </button>
  );
}

function Thumbnails({ doc, current, onPick }: { doc: Doc; current: number; onPick: (n: number) => void }) {
  const [srcs, setSrcs] = useState<Record<number, string>>({});
  const refs = useRef<Record<number, HTMLButtonElement | null>>({});

  useEffect(() => {
    const seen = new Set<number>();
    const io = new IntersectionObserver(async (entries) => {
      for (const entry of entries) {
        const n = Number((entry.target as HTMLElement).dataset.page);
        if (!entry.isIntersecting || seen.has(n)) continue;
        seen.add(n);
        const { renderPage } = await import("@/lib/pdfjs");
        const canvas = await renderPage(doc, n, 0.25);
        setSrcs((s) => ({ ...s, [n]: canvas.toDataURL("image/jpeg", 0.7) }));
      }
    });
    Object.values(refs.current).forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [doc]);

  useEffect(() => {
    refs.current[current]?.scrollIntoView({ block: "nearest" });
  }, [current]);

  return (
    <div className="space-y-2">
      {Array.from({ length: doc.numPages }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          data-page={n}
          ref={(el) => {
            refs.current[n] = el;
          }}
          onClick={() => onPick(n)}
          className={`block w-full rounded border-2 p-1 text-center text-xs ${n === current ? "border-brand-500" : "border-transparent hover:border-slate-300"}`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {srcs[n] ? <img src={srcs[n]} alt={`Page ${n}`} className="mx-auto shadow" /> : <span className="mx-auto block aspect-[1/1.41] w-full bg-slate-100 dark:bg-slate-800" />}
          <span className="mt-1 block text-slate-500">{n}</span>
        </button>
      ))}
    </div>
  );
}

function OutlineTree({ items, onPick, depth = 0 }: { items: OutlineItem[]; onPick: (dest: unknown) => void; depth?: number }) {
  return (
    <ul className="space-y-0.5 text-sm">
      {items.map((item, i) => (
        <li key={i}>
          <button type="button" className="w-full truncate rounded px-1 py-0.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800" style={{ paddingLeft: 4 + depth * 12 }} onClick={() => onPick(item.dest)} title={item.title}>
            {item.title}
          </button>
          {item.items?.length > 0 && <OutlineTree items={item.items} onPick={onPick} depth={depth + 1} />}
        </li>
      ))}
    </ul>
  );
}
