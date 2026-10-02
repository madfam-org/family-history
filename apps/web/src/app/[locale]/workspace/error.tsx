"use client";

import { useEffect } from "react";

/** Last-resort boundary for unexpected failures in the app. Bilingual because messages may be unavailable. */
export default function WorkspaceError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("app render failed", error.digest ?? "");
  }, [error]);
  return (
    <div role="alert" className="flex max-w-xl flex-col gap-3">
      <h1 className="text-2xl font-bold">Algo salió mal</h1>
      <p lang="en" className="text-muted">
        Something went wrong.
      </p>
      {error.digest ? <p className="fh-date text-muted">{error.digest}</p> : null}
      <button type="button" onClick={reset} className="fh-button self-start">
        Intentar de nuevo · Try again
      </button>
    </div>
  );
}
