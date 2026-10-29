/** Page-range parsing, mirroring the server (1-based input, 0-based output). */
export function parsePageList(spec: string | undefined, total: number): number[] {
  const text = (spec ?? "all").trim().toLowerCase() || "all";
  const out: number[] = [];
  const page = (token: string): number => {
    if (token === "last") return total;
    const n = Number(token);
    if (!Number.isInteger(n)) throw new Error(`'${token}' is not a page number.`);
    if (n < 1 || n > total) throw new Error(`Page ${n} is out of range (the document has ${total} pages).`);
    return n;
  };
  for (const raw of text.split(",")) {
    const part = raw.trim();
    if (!part) continue;
    if (part === "all") for (let i = 0; i < total; i++) out.push(i);
    else if (part === "odd") for (let i = 0; i < total; i += 2) out.push(i);
    else if (part === "even") for (let i = 1; i < total; i += 2) out.push(i);
    else if (part.includes("-")) {
      const [a, b] = part.split("-", 2).map((s) => s.trim());
      const start = a ? page(a) : 1;
      const end = b ? page(b) : total;
      const step = end >= start ? 1 : -1;
      for (let i = start; step > 0 ? i <= end : i >= end; i += step) out.push(i - 1);
    } else out.push(page(part) - 1);
  }
  if (!out.length) throw new Error("The page selection is empty.");
  return out;
}

export function parseRangeGroups(spec: string, total: number): number[][] {
  const groups = spec
    .split(",")
    .filter((p) => p.trim())
    .map((p) => parsePageList(p, total));
  if (!groups.length) throw new Error("Enter at least one page range, for example 1-3, 4-6.");
  return groups;
}
