export const COUNTRY_OPTIONS = ["France", "Belgium", "Luxembourg", "Other"] as const;
export type CountryOption = (typeof COUNTRY_OPTIONS)[number];

export const EMPLOYEE_OPTIONS = [
  { id: "1-9", label: "1–9", min: 1, max: 9 },
  { id: "10-19", label: "10–19", min: 10, max: 19 },
  { id: "20-49", label: "20–49", min: 20, max: 49 },
  { id: "50-99", label: "50–99", min: 50, max: 99 },
  { id: "100-249", label: "100–249", min: 100, max: 249 },
  { id: "custom", label: "Custom range", min: null, max: null },
] as const;

export const TURNOVER_OPTIONS = [
  { id: "below1m", label: "Below €1M", min: null, max: 1_000_000 },
  { id: "above1m", label: "Above €1M", min: 1_000_000, max: null },
  { id: "above5m", label: "Above €5M", min: 5_000_000, max: null },
  { id: "above10m", label: "Above €10M", min: 10_000_000, max: null },
  { id: "custom", label: "Custom range", min: null, max: null },
] as const;

export const FIELD_OPTIONS = [
  "Company Name",
  "Director Name",
  "Email Address",
  "Phone Number",
  "Number of Employees",
  "Annual Turnover",
  "Company Address",
  "Company Website",
  "B2C Website",
] as const;

export const SIMULATION_STEPS = [
  "Validating source URLs",
  "Checking robots.txt rules",
  "Fetching permitted public pages",
  "Parsing company information",
  "Matching publicly linked B2C websites",
  "Reviewing available contact details",
] as const;

export const MAX_SOURCES = 10;

export type UrlCheck = { ok: true; url: string } | { ok: false; error: string };

/** Accepts http(s) URLs with a real-looking host (e.g. example.com). Adds https:// if missing. */
export function validateUrl(input: string): UrlCheck {
  const text = input.trim();
  if (!text) return { ok: false, error: "Enter a website address." };
  if (/\s/.test(text)) return { ok: false, error: "A URL cannot contain spaces." };

  const withProtocol = /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `https://${text}`;
  let parsed: URL;
  try {
    parsed = new URL(withProtocol);
  } catch {
    return { ok: false, error: "This is not a valid URL. Example: https://www.example.com" };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { ok: false, error: "Only http:// and https:// addresses are supported." };
  }
  const host = parsed.hostname;
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(host) || host.startsWith("-") || host.endsWith("-")) {
    return { ok: false, error: "The domain looks incomplete. Example: www.example.com" };
  }
  const tld = host.split(".").pop() ?? "";
  if (!/^[a-z]{2,}$/i.test(tld)) return { ok: false, error: "The domain ending (e.g. .com, .fr) looks invalid." };
  if (parsed.username || parsed.password) return { ok: false, error: "URLs with a username or password are not allowed." };

  return { ok: true, url: parsed.toString().replace(/\/$/, "") };
}
