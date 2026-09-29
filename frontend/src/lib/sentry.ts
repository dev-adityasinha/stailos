/** Client-side error monitoring, free Sentry developer tier (5k events/month).
 *  Uses the framework-agnostic @sentry/react client rather than @sentry/nextjs
 *  to avoid its build-time webpack/instrumentation hooks — this app runs on
 *  a pre-release Next.js with breaking changes vs. what @sentry/nextjs
 *  expects, so plain runtime init is the more robust integration. No-op
 *  entirely when NEXT_PUBLIC_SENTRY_DSN is unset (default: free/local dev). */
import * as Sentry from "@sentry/react";

let initialized = false;

export function initSentry() {
  if (initialized || typeof window === "undefined") return;
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,
  });
  initialized = true;
}

export { Sentry };
