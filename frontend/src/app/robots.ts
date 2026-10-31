import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/brand";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/account", "/api/", "/v1/", "/teams", "/sign/", "/esign/", "/documents", "/s/"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
