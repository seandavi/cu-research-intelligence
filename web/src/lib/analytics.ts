// Google Analytics 4 (gtag.js). Every function is a safe no-op when the tag
// isn't loaded (dev, preview, tailnet hosts), so the app runs untracked there.
// No PII is sent — events carry ids and counts, not names or emails.

// Consolidated "Sean Davis — web" GA4 property (see monode
// infrastructure/ANALYTICS.md). Hard-coded: not a secret — the ID is visible in
// the client bundle by design. Hits are tagged with content_group so this site
// can be filtered within the shared property.
const GA_ID = "G-KLLV1GCF4E";
const CONTENT_GROUP = "uccc-insights";
let started = false;

// Only production hosts send hits: skip localhost, raw IPs (incl. the tailnet
// 100.x address), and preview/dev domains.
function isProductionHost(host: string): boolean {
  if (!host || host === "localhost" || host.endsWith(".localhost")) return false;
  if (/^[\d.]+$/.test(host) || host.includes(":")) return false; // IPv4 / IPv6
  return ![".workers.dev", ".netlify.app", ".ts.net"].some((s) => host.endsWith(s));
}

export function initAnalytics(): void {
  if (started || typeof document === "undefined") return;
  if (!isProductionHost(window.location.hostname)) return;
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
  window.gtag("config", GA_ID, { send_page_view: false, content_group: CONTENT_GROUP });
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

// For controls that fire per keystroke or per pixel (year inputs, range slider):
// send one event per settled value, keyed by event name.
const timers: Record<string, number> = {};
export function trackDebounced(name: string, params: Record<string, unknown> = {}, ms = 800): void {
  window.clearTimeout(timers[name]);
  timers[name] = window.setTimeout(() => track(name, params), ms);
}
