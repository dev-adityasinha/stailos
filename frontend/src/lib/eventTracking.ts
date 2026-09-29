/** GA4 / Meta Pixel / Google Ads conversion tracking for public event pages.
 *  Entirely no-op when the corresponding NEXT_PUBLIC_* env var is unset —
 *  same "safe by default, real once configured" pattern as email/WhatsApp/
 *  Sentry providers on the backend. Nothing is loaded, no network calls, no
 *  cost, until the user pastes in real IDs. */

interface FbqFunction {
  (...args: unknown[]): void;
  queue: unknown[];
}

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    fbq?: FbqFunction;
  }
}

const GA4_ID = process.env.NEXT_PUBLIC_GA4_ID;
const META_PIXEL_ID = process.env.NEXT_PUBLIC_META_PIXEL_ID;
const GOOGLE_ADS_ID = process.env.NEXT_PUBLIC_GOOGLE_ADS_ID;
const GOOGLE_ADS_CONVERSION_LABEL = process.env.NEXT_PUBLIC_GOOGLE_ADS_CONVERSION_LABEL;

let initialized = false;

function loadScript(src: string) {
  const s = document.createElement("script");
  s.src = src;
  s.async = true;
  document.head.appendChild(s);
}

export function initEventTracking() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;

  if (GA4_ID || GOOGLE_ADS_ID) {
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag(...args: unknown[]) {
      window.dataLayer!.push(args);
    };
    window.gtag("js", new Date());
    if (GA4_ID) {
      loadScript(`https://www.googletagmanager.com/gtag/js?id=${GA4_ID}`);
      window.gtag("config", GA4_ID);
    }
    if (GOOGLE_ADS_ID) {
      loadScript(`https://www.googletagmanager.com/gtag/js?id=${GOOGLE_ADS_ID}`);
      window.gtag("config", GOOGLE_ADS_ID);
    }
  }

  if (META_PIXEL_ID) {
    const fbq: FbqFunction = Object.assign(
      (...args: unknown[]) => fbq.queue.push(args),
      { queue: [] as unknown[] }
    );
    window.fbq = fbq;
    loadScript("https://connect.facebook.net/en_US/fbevents.js");
    window.fbq("init", META_PIXEL_ID);
    window.fbq("track", "PageView");
  }
}

export function trackEventPageView(eventName: string) {
  window.gtag?.("event", "page_view", { event_category: "event_landing", event_label: eventName });
}

export function trackRegistration(eventName: string) {
  window.gtag?.("event", "generate_lead", { event_category: "event_registration", event_label: eventName });
  window.fbq?.("track", "Lead", { content_name: eventName });
  if (GOOGLE_ADS_ID && GOOGLE_ADS_CONVERSION_LABEL) {
    window.gtag?.("event", "conversion", {
      send_to: `${GOOGLE_ADS_ID}/${GOOGLE_ADS_CONVERSION_LABEL}`,
    });
  }
}
