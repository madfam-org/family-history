import Link from "next/link";

import { brandName } from "@/lib/brand";

/** Fallback for URLs outside any locale tree; the proxy normally prevents reaching it. */
export default function GlobalNotFound() {
  return (
    <html lang="es-MX">
      <body className="flex min-h-screen items-center justify-center p-4">
        <main className="max-w-md text-center">
          <p className="text-sm text-muted">{brandName("es")}</p>
          <h1 className="mt-2 text-2xl font-semibold">No encontramos esta página</h1>
          <p lang="en" className="mt-1 text-muted">
            We could not find this page.
          </p>
          <p className="mt-6">
            <Link href="/es">Volver al inicio</Link> · <Link href="/en">Back to home</Link>
          </p>
        </main>
      </body>
    </html>
  );
}
