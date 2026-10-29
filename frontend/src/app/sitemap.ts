import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/brand";
import { catalog } from "@/lib/tools";

export default function sitemap(): MetadataRoute.Sitemap {
  const pages = ["", "/pricing", "/developers", "/workflows", "/privacy"];
  return [
    ...pages.map((p) => ({ url: `${SITE_URL}${p}`, changeFrequency: "weekly" as const })),
    ...catalog.tools.map((t) => ({ url: `${SITE_URL}/tools/${t.id}`, changeFrequency: "monthly" as const })),
  ];
}
