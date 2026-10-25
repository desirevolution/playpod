import { english } from "./messages.ts";
export type Locale = "de" | "en";
export type LanguagePreference = Locale | "auto";
const STORAGE_KEY = "playpod.language";
export function detectLocale(languages: readonly string[]): Locale {
  for (const language of languages) {
    const code = language.toLowerCase().split(/[-_]/)[0];
    if (code === "de" || code === "en") return code;
  }
  return "en";
}
export function readPreference(): LanguagePreference {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "de" || saved === "en") return saved;
  } catch {}
  return "auto";
}
export function resolveLocale(preference: LanguagePreference): Locale {
  return preference === "auto"
    ? typeof navigator === "undefined" || typeof window === "undefined"
      ? "de"
      : detectLocale(
          navigator.languages?.length
            ? navigator.languages
            : [navigator.language],
        )
    : preference;
}
let preference = readPreference();
let locale = resolveLocale(preference);
export const getLocale = () => locale;
export const getLanguagePreference = () => preference;
export const localeTag = () => (locale === "de" ? "de-DE" : "en-GB");
export function setLanguage(value: LanguagePreference) {
  preference = value;
  locale = resolveLocale(value);
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {}
  applyLanguage();
  if (typeof window !== "undefined")
    window.dispatchEvent(new Event("playpod-language"));
}
export function applyLanguage() {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale;
  document
    .querySelector('link[rel="manifest"]')
    ?.setAttribute(
      "href",
      locale === "en" ? "/manifest-en.webmanifest" : "/manifest.webmanifest",
    );
}
export function t(
  source: string,
  values: Record<string, string | number> = {},
): string {
  const key = source.replace(/\s+/g, " ").trim();
  const translated =
    locale === "en" && Object.hasOwn(english, key) ? english[key] : key;
  const result =
    source.match(/^\s*/)?.[0] + translated + source.match(/\s*$/)?.[0];
  return result.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.hasOwn(values, name) ? String(values[name]) : match,
  );
}

// Preserve API payloads and third-party diagnostics; localize known UI errors at display time.
const originalMessages = new Map(
  Object.entries(english).map(([de, en]) => [en, de]),
);
export function localizeMessage(message: string | undefined | null): string {
  if (!message) return "";
  const source = originalMessages.get(message) ?? message;
  if (Object.hasOwn(english, source)) return t(source);
  const colon = source.indexOf(": ");
  if (colon > 0 && Object.hasOwn(english, source.slice(0, colon)))
    return t(source.slice(0, colon)) + ": " + source.slice(colon + 2);
  return message;
}

export function countText(
  count: number,
  singular: string,
  plural: string,
): string {
  return t(count === 1 ? singular : plural, { count });
}
