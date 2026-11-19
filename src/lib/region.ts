// Exact timezones first, then whole-continent prefixes, so that e.g.
// America/Toronto resolves to CA before the America/ fallback claims it.
const TIMEZONE_COUNTRIES: [prefix: string, country: string][] = [
  ["America/Toronto", "CA"],
  ["America/Vancouver", "CA"],
  ["America/Edmonton", "CA"],
  ["America/Winnipeg", "CA"],
  ["America/Halifax", "CA"],
  ["America/St_Johns", "CA"],
  ["America/Regina", "CA"],
  ["Europe/London", "GB"],
  ["Europe/Dublin", "IE"],
  ["Europe/Amsterdam", "NL"],
  ["Europe/Brussels", "BE"],
  ["Europe/Berlin", "DE"],
  ["Europe/Vienna", "AT"],
  ["Europe/Zurich", "CH"],
  ["Europe/Paris", "FR"],
  ["Europe/Madrid", "ES"],
  ["Europe/Rome", "IT"],
  ["Europe/Stockholm", "SE"],
  ["Europe/Warsaw", "PL"],
  ["Asia/Kolkata", "IN"],
  ["Asia/Calcutta", "IN"],
  ["Asia/Tokyo", "JP"],
  ["Asia/Singapore", "SG"],
  ["Asia/Dubai", "AE"],
  ["Australia/", "AU"],
  ["America/", "US"],
];

export const DEFAULT_COUNTRY = "US";
const STORAGE_KEY = "price-tracker.country";

export function countryForTimezone(timezone: string): string | null {
  const match = TIMEZONE_COUNTRIES.find(([prefix]) => timezone.startsWith(prefix));
  return match ? match[1] : null;
}

/** Region part of a BCP 47 tag: "nl-NL" -> "NL", "en" -> null. */
export function countryForLanguage(language: string): string | null {
  const region = language.split("-")[1];
  return region && /^[A-Za-z]{2}$/.test(region) ? region.toUpperCase() : null;
}

export function detectCountry(): string {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  const language = typeof navigator === "undefined" ? "" : navigator.language;
  return countryForTimezone(timezone) ?? countryForLanguage(language) ?? DEFAULT_COUNTRY;
}

export function loadSavedCountry(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode)
  }
}

export function saveCountry(country: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, country);
  } catch {
    // not being able to remember the choice is not worth surfacing
  }
}

/** The first candidate the backend supports, else its default. */
export function pickSupported(
  candidates: (string | null)[],
  supported: string[],
  fallback: string,
): string {
  return candidates.find((c): c is string => !!c && supported.includes(c)) ?? fallback;
}
