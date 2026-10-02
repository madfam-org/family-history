import type { ReactNode } from "react";

import "./globals.css";

/**
 * The real root layout is app/[locale]/layout.tsx (it owns <html lang>). This pass-through
 * exists so that app/not-found.tsx has a parent, per the next-intl App Router pattern.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
