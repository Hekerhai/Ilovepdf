import Link from "next/link";

import { BRAND } from "@/lib/brand";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-bold tracking-tight" aria-label={`${BRAND} home`}>
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="9" className="fill-brand-600" />
        <path d="M10 8h9l5 5v11a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2Z" fill="#fff" />
        <path d="M19 8v5h5" fill="#bccfff" />
        <path d="M12 17h8M12 21h6" stroke="#2840f0" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span className="text-lg">{BRAND}</span>
    </Link>
  );
}
