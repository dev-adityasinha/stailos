"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import { Sentry, initSentry } from "@/lib/sentry";

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    initSentry();
    Sentry.captureException(error);
    console.error(error);
  }, [error]);

  return (
    // global-error replaces the root layout when active — must include its own html/body.
    <html lang="en">
      <body
        style={{
          display: "flex",
          minHeight: "100vh",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
          background: "#0b0f19",
          color: "#e5e7eb",
        }}
      >
        <div style={{ textAlign: "center", maxWidth: 420, padding: 24 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: 13, color: "#9ca3af", marginBottom: 20 }}>
            An unexpected error occurred. It has been reported and we&apos;ll
            take a look.
          </p>
          <button
            onClick={() => unstable_retry()}
            style={{
              background: "#3b82f6",
              color: "white",
              border: "none",
              borderRadius: 8,
              padding: "8px 16px",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
