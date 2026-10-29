import type { Metadata, Viewport } from "next";

import { AppProviders } from "@/components/AppProviders";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { BRAND, SITE_URL } from "@/lib/brand";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: `${BRAND}: every PDF tool, private by default`, template: `%s | ${BRAND}` },
  description:
    "Merge, split, compress, convert, sign, OCR and edit PDFs for free. Many tools run in your browser so files never leave your device.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#020617" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">
        <AppProviders>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
        </AppProviders>
      </body>
    </html>
  );
}
