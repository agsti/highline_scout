import type { CountryEntry } from "../types/highliner";

export const COUNTRY_STORAGE_KEY = "country";

const IPWHO_URL = "https://ipwho.is/";
const COUNTRY_CODE = /^[A-Z]{2}$/;

export function readSavedCountry(countries: CountryEntry[]): string | null {
  try {
    const saved = window.localStorage.getItem(COUNTRY_STORAGE_KEY);
    return countries.some((entry) => entry.id === saved) ? saved : null;
  } catch {
    return null;
  }
}

export function saveCountry(country: string): void {
  try {
    window.localStorage.setItem(COUNTRY_STORAGE_KEY, country);
  } catch {
    // Storage can be unavailable in private browsing contexts.
  }
}

export function clearSavedCountry(): void {
  try {
    window.localStorage.removeItem(COUNTRY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in private browsing contexts.
  }
}

export async function detectCountry(
  countries: CountryEntry[],
  signal?: AbortSignal,
): Promise<string | null> {
  try {
    const response = await fetch(IPWHO_URL, { signal });
    const body: unknown = await response.json();
    if (!response.ok || !isIpWhoSuccess(body)) return null;
    return (
      countries.find((entry) => entry.country_code === body.country_code)?.id ??
      null
    );
  } catch {
    return null;
  }
}

function isIpWhoSuccess(
  value: unknown,
): value is { success: true; country_code: string } {
  if (typeof value !== "object" || value === null) return false;
  const response = value as Record<string, unknown>;
  return (
    response.success === true &&
    typeof response.country_code === "string" &&
    COUNTRY_CODE.test(response.country_code)
  );
}
