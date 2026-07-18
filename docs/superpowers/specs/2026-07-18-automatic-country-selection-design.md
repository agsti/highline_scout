# Automatic country selection design

## Goal

Choose an initial map country from a visitor's coarse IP-derived country, while
preserving explicit user choice and keeping Spain as the reliable fallback.

## Country metadata

Each country that supports automatic selection has a one-line metadata file:

```text
data/<country>/country_code
```

The file contains the uppercase ISO 3166-1 alpha-2 code, for example `ES` for
Spain. It belongs with the country data so adding a country does not require a
frontend or backend code mapping.

The server reads and validates this file while it discovers country data. The
`/countries` response adds an optional `country_code` field for each country.
Countries without a readable, valid country-code file remain available in the
manual country selector but are not eligible for automatic selection.

## Initial-selection flow

1. The app loads available countries from `/countries`.
2. If the user has already explicitly selected a country in local storage and
   it is still available, that saved choice is used. No geolocation lookup is
   made.
3. Otherwise, the frontend makes one best-effort, short-timeout request to
   `https://ipwho.is/`. It reads only `country_code` from the response.
4. The app compares that code to the country codes returned by `/countries`.
   A match becomes the initial country for the current session.
5. A timeout, network/CORS failure, malformed response, unsupported code, or
   unavailable matching country leaves Spain selected.
6. Selecting a country in the existing menu saves that explicit choice locally.
   It overrides future automatic selection.

The automatic choice is not persisted: it is a first-visit default, not a
claimed preference. Country changes must continue to clear country-specific
restriction state and update the map as they do now.

## Privacy and user experience

The lookup does not ask for browser location permission and does not request or
use coordinates. The visitor's IP is necessarily sent to IPWho for this one
country-level lookup, so the privacy disclosure will say this plainly. The
application does not store the location result, include it in PostHog events,
or repeat the request after a manual selection.

Language selection is unchanged: the saved language wins, followed by browser
language preferences, then English. It is independent of country selection.

## Error handling and tests

The lookup is non-blocking: Spain renders immediately while the country list and
best-effort lookup resolve. The app only applies an automatic result when it
still has no saved/manual country choice.

Tests cover:

- server discovery and API serialization of valid, missing, and invalid
  `country_code` files;
- matching a successful IPWho country code to an available country;
- Spain fallback for failed, slow, malformed, or unsupported responses;
- a saved/manual preference preventing the lookup and taking precedence; and
- no persistence or analytics capture for an automatic selection.

## Out of scope

This feature does not use the browser Geolocation API, precise coordinates,
city/region lookup, VPN detection, or automatic language changes. IPWho's
shared free CORS allowance is not an availability guarantee; failure always
falls back safely to Spain.
