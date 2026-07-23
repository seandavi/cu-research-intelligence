// Google Analytics 4 (gtag.js). The Measurement ID comes from
// VITE_GA_MEASUREMENT_ID; with none set, every function is a safe no-op so the
// app runs untracked in dev / when analytics isn't configured. No PII is sent —
// events carry ids and counts, not names or emails.

// GA4 Measurement ID. Defaults to the project property; override per-deployment
// with VITE_GA_MEASUREMENT_ID (set it to "off" to disable). Not a secret — the
// ID is visible in the client bundle by design.
const ENV_ID = import.meta.env.VITE_GA_MEASUREMENT_ID;
const GA_ID = ENV_ID === "off" ? undefined : (ENV_ID || "G-YTL0Z01D6X");
let started = false;

export function initAnalytics(): void {
  if (!GA_ID || started || typeof document === "undefined") return;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
  document.head.appendChild(s);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  // SPA: we send page_view manually on route change, so disable the automatic one.
  window.gtag("config", GA_ID, { send_page_view: false });
  started = true;
}

export function trackPageView(path: string, title?: string): void {
  window.gtag?.("event", "page_view", {
    page_path: path,
    page_title: title ?? document.title,
    page_location: window.location.href,
  });
}

export function track(name: string, params: Record<string, unknown> = {}): void {
  window.gtag?.("event", name, params);
}
