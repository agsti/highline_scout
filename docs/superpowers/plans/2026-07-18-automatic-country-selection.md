# Automatic Country Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select an available map country from a first-visit IPWho country lookup, without overriding a user's explicit selection or changing language selection.

**Architecture:** The server reads an optional ISO alpha-2 code from `data/<country>/country_code` while deriving the existing country catalog and exposes it through `/countries`. A focused frontend helper owns preference storage, IPWho response validation, and code-to-catalog matching; `App` invokes it only after the country catalog arrives. The initial Spain state remains visible while the best-effort lookup resolves.

**Tech Stack:** Python 3.12, FastAPI, React 18, TypeScript, Vitest, Testing Library, IPWho.is HTTPS API.

## Global Constraints

- `data/<country>/country_code` contains exactly one uppercase ISO 3166-1 alpha-2 code such as `ES`; it is country data, not a source-code registry.
- Countries without a valid readable code remain manually selectable and are omitted from automatic matching.
- Use `https://ipwho.is/` once only when no valid saved country preference exists; consume only `country_code`.
- A failed, timed-out, malformed, CORS-blocked, or unsupported lookup leaves `config.DEFAULT_COUNTRY` / `"spain"` selected.
- Persist only an explicit manual selection in `localStorage`; do not persist an automatic result or send it to PostHog.
- Do not request browser Geolocation permission or coordinates. Keep the language precedence unchanged: saved choice, browser preference, English.
- Preserve the existing app behavior that clears restriction state and refits/reloads layers when `country` changes.
- Maintain the repository’s 88-column lint style, strict mypy, Vulture cleanliness, TypeScript build, and i18n catalog parity.

---

## File structure

- `highliner/server/router/deps.py` — validates a country data directory’s optional `country_code` file and carries it on the cached `CountryEntry`.
- `highliner/server/router/countries.py` — serializes an available country’s optional code without changing its existing bounds contract.
- `tests/test_api.py` — creates country-code fixture files and verifies API behavior for valid, missing, and malformed metadata.
- `frontend/src/types/highliner.ts` — represents the optional API `country_code` field.
- `frontend/src/lib/countrySelection.ts` — isolates local preference reading/writing plus IPWho lookup, validation, timeout-safe matching, and no-throw fallback behavior.
- `frontend/src/lib/countrySelection.test.ts` — unit-tests country selection independently from React rendering.
- `frontend/src/App.tsx` — loads the catalog, applies a valid saved country or one transient automatic country result, and persists only menu changes.
- `frontend/src/App.test.tsx` — verifies App-level ordering, manual preference priority, and that automatic selection is not analytics.
- `frontend/src/lib/i18n/strings.ts` and `frontend/src/lib/i18n/i18n.test.tsx` — disclose the one country-only IPWho lookup in all three languages and keep catalog parity.
- `AGENTS.md` — documents the country-code file in the data layout for operators adding country data.

### Task 1: Expose country data codes through the existing catalog

**Files:**
- Modify: `highliner/server/router/deps.py:29-82`
- Modify: `highliner/server/router/countries.py:10-15`
- Modify: `tests/test_api.py:16-31, 192-207`

**Interfaces:**
- Produces: `CountryEntry(id: str, bounds_lonlat: LonLatBox, country_code: str | None)`.
- Produces: `read_country_code(country_dir: Path) -> str | None`, returning only `^[A-Z]{2}$` file content.
- Produces: `GET /countries -> {"countries": [{"id", "bounds_lonlat", "country_code"?}]}`; `country_code` is omitted when unavailable.

- [ ] **Step 1: Write failing API tests for country-code metadata**

  Add a test helper beside `_write_region` that writes `data_dir / country /
  "country_code"`, then extend the existing countries endpoint test with a
  valid Spanish file and an invalid French file:

  ```python
  def _write_country_code(data_dir: Path, country: str, code: str) -> None:
      country_dir = data_dir / country
      country_dir.mkdir(parents=True, exist_ok=True)
      (country_dir / "country_code").write_text(code, encoding="utf-8")

  def test_countries_exposes_only_valid_country_codes(tmp_path: Path) -> None:
      # Arrange the existing Spain and France fixture regions first.
      _write_country_code(tmp_path, "spain", "ES\n")
      _write_country_code(tmp_path, "france", "fr")

      countries = TestClient(create_app(data_dir=tmp_path)).get(
          "/countries"
      ).json()["countries"]

      assert countries == [
          {"id": "france", "bounds_lonlat": pytest.ANY},
          {"id": "spain", "bounds_lonlat": pytest.ANY,
           "country_code": "ES"},
      ]
  ```

  Do not use `pytest.ANY` literally if the installed pytest version lacks it;
  assert the IDs/codes and four-value bounds separately, as the adjacent test
  already does. Add a missing-file assertion in the same test: no `country_code`
  key is emitted for a country with no file.

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `uv run pytest tests/test_api.py -k countries -v`

  Expected: FAIL because `/countries` currently returns no `country_code`.

- [ ] **Step 3: Add strict file parsing to the cached country index**

  In `highliner/server/router/deps.py`, import `re`, extend the frozen data
  class, and add this helper before `countries_from_index`:

  ```python
  _COUNTRY_CODE_RE = re.compile(r"[A-Z]{2}\Z")

  def read_country_code(country_dir: Path) -> str | None:
      """Return a country's valid ISO alpha-2 code, if its data declares one."""
      try:
          code = (country_dir / "country_code").read_text(
              encoding="utf-8"
          ).strip()
      except OSError:
          return None
      return code if _COUNTRY_CODE_RE.fullmatch(code) else None
  ```

  Group `RegionEntry` values as today, retain one `country_dir` from the group
  (`entries[0].region_dir.parent`), and construct each `CountryEntry` with
  `read_country_code(country_dir)`. This does not create a source mapping and
  leaves directory discovery based solely on `grid.json`.

  In `highliner/server/router/countries.py`, serialize the optional value only
  when present:

  ```python
  {
      "id": entry.id,
      "bounds_lonlat": list(entry.bounds_lonlat),
      **({"country_code": entry.country_code}
         if entry.country_code is not None else {}),
  }
  ```

- [ ] **Step 4: Run backend verification**

  Run: `uv run pytest tests/test_api.py -k countries -v && just check`

  Expected: country metadata tests PASS; lint, strict typing, and dead-code
  checks PASS.

- [ ] **Step 5: Commit the backend catalog change**

  ```bash
  git add highliner/server/router/deps.py highliner/server/router/countries.py tests/test_api.py
  git commit -m "feat: expose country codes in catalog"
  ```

### Task 2: Build a testable frontend country-selection helper

**Files:**
- Create: `frontend/src/lib/countrySelection.ts`
- Create: `frontend/src/lib/countrySelection.test.ts`
- Modify: `frontend/src/types/highliner.ts:53-56`

**Interfaces:**
- Consumes: `CountryEntry` from `frontend/src/types/highliner.ts`.
- Produces: `COUNTRY_STORAGE_KEY = "country"`, `readSavedCountry()`,
  `saveCountry(country: string)`, `clearSavedCountry()`, and
  `detectCountry(countries: CountryEntry[], signal?: AbortSignal): Promise<string | null>`.
- `detectCountry` resolves a matching country ID or `null`; it never throws.

- [ ] **Step 1: Write failing unit tests for preference and IPWho behavior**

  Create `frontend/src/lib/countrySelection.test.ts` with deterministic
  country fixtures and direct global-fetch mocks:

  ```ts
  const countries = [
    { id: "spain", country_code: "ES", bounds_lonlat: [-9, 36, 4, 44] },
    { id: "france", country_code: "FR", bounds_lonlat: [-5, 42, 8, 51] },
    { id: "manual_only", bounds_lonlat: [0, 0, 1, 1] },
  ];

  it("returns an available saved preference", () => {
    window.localStorage.setItem(COUNTRY_STORAGE_KEY, "france");
    expect(readSavedCountry(countries)).toBe("france");
  });

  it("matches IPWho's country_code without persisting it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, country_code: "FR" }),
    }));

    await expect(detectCountry(countries)).resolves.toBe("france");
    expect(window.localStorage.getItem(COUNTRY_STORAGE_KEY)).toBeNull();
    expect(fetch).toHaveBeenCalledWith("https://ipwho.is/", {
      signal: undefined,
    });
  });

  it.each([
    [{ success: false }, "provider failure"],
    [{ success: true, country_code: "XX" }, "unsupported country"],
    [{ success: true, country_code: "fr" }, "malformed code"],
  ])("returns null for %s", async (body) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => body,
    }));
    await expect(detectCountry(countries)).resolves.toBeNull();
  });

  it("returns null when the request rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("CORS")));
    await expect(detectCountry(countries)).resolves.toBeNull();
  });
  ```

  Also test `readSavedCountry` returns `null` for a no-longer-available value,
  and that `saveCountry` is the only helper that writes local storage.

- [ ] **Step 2: Run the helper tests to verify they fail**

  Run: `cd frontend && npm test -- countrySelection.test.ts`

  Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement narrow storage and lookup helpers**

  Add `country_code?: string` to `CountryEntry`, then implement the helper
  without React dependencies. Use `try/catch` around both storage and fetch;
  accept only an object response with `success === true` and a two-uppercase-
  letter `country_code`; match it against `entry.country_code`:

  ```ts
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

  export async function detectCountry(
    countries: CountryEntry[], signal?: AbortSignal,
  ): Promise<string | null> {
    try {
      const response = await fetch(IPWHO_URL, { signal });
      const body: unknown = await response.json();
      if (!response.ok || !isIpWhoSuccess(body)) return null;
      return countries.find((entry) => entry.country_code === body.country_code)
        ?.id ?? null;
    } catch {
      return null;
    }
  }
  ```

  Define `isIpWhoSuccess(value: unknown): value is { success: true;
  country_code: string }` using `typeof value === "object"`, a non-null guard,
  a `Record<string, unknown>` cast, and the `COUNTRY_CODE` regex. `saveCountry`
  and `clearSavedCountry` swallow unavailable-storage exceptions. Do not import
  the analytics module and do not call `saveCountry` from `detectCountry`.

- [ ] **Step 4: Run frontend static and unit verification**

  Run: `cd frontend && npm test -- countrySelection.test.ts && npm run build`

  Expected: all helper tests PASS and `tsc -b`/Vite production build PASS.

- [ ] **Step 5: Commit the frontend selection primitive**

  ```bash
  git add frontend/src/types/highliner.ts frontend/src/lib/countrySelection.ts frontend/src/lib/countrySelection.test.ts
  git commit -m "feat: add automatic country detection helper"
  ```

### Task 3: Apply the helper in App without racing a manual choice

**Files:**
- Modify: `frontend/src/App.tsx:1-98`
- Modify: `frontend/src/App.test.tsx:1-130`
- Modify: `frontend/src/App.analytics.test.tsx:1-90`

**Interfaces:**
- Consumes: `readSavedCountry(countries)`, `saveCountry(country)`,
  `clearSavedCountry()`, and `detectCountry(countries, signal?)` from Task 2.
- Produces: App state with Spain as initial rendering fallback; manual selection
  persists and wins over automatic detection; automatic detection is transient.

- [ ] **Step 1: Extend App tests for selection order and analytics silence**

  Update the existing `./lib/api` mock to return an available France country
  code. Mock `./lib/countrySelection` as a named module so the timing is
  deterministic. Add these test cases:

  ```tsx
  it("applies the detected country after the catalog loads", async () => {
    apiMocks.fetchCountries.mockResolvedValueOnce([
      { id: "france", country_code: "FR", bounds_lonlat: [-5, 42, 8, 51] },
    ]);
    countryMocks.readSavedCountry.mockReturnValue(null);
    countryMocks.detectCountry.mockResolvedValue("france");

    renderApp();

    await waitFor(() => expect(countryMocks.detectCountry).toHaveBeenCalled());
    expect(lastMapProps().country).toBe("france");
    expect(countryMocks.saveCountry).not.toHaveBeenCalled();
  });

  it("uses an available saved country and skips IPWho", async () => {
    countryMocks.readSavedCountry.mockReturnValue("france");
    renderApp();
    await waitFor(() => expect(lastMapProps().country).toBe("france"));
    expect(countryMocks.detectCountry).not.toHaveBeenCalled();
  });
  ```

  In the analytics suite, arrange a detected country and assert
  `captureMock` has no event with a country/location property. Keep the current
  filter and restriction analytics assertions unchanged.

- [ ] **Step 2: Run the integration tests to verify they fail**

  Run: `cd frontend && npm test -- App.test.tsx App.analytics.test.tsx`

  Expected: FAIL because `App` does not yet use the new helper.

- [ ] **Step 3: Wire catalog loading, timeout, and explicit preference handling**

  In `App.tsx`, import `useRef` (already present) and the four helpers. Keep
  `const [country, setCountry] = useState("spain")`; do not read or write a
  country value during initial render. Replace the current countries effect
  with an abortable sequence:

  ```ts
  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 2_000);

    fetchCountries(controller.signal)
      .then(async (available) => {
        setCountries(available);
        const saved = readSavedCountry(available);
        if (saved) {
          setCountry(saved);
          return;
        }
        clearSavedCountry();
        const detected = await detectCountry(available, controller.signal);
        if (detected && !manualCountryRef.current) setCountry(detected);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          handleError(tRef.current("error", { detail: String(error) }));
        }
      })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [handleError]);
  ```

  Declare `const manualCountryRef = useRef(false)` before this effect. In
  `handleCountryChange`, set that ref to `true`, call `saveCountry(next)`, then
  retain the existing state and restriction resets. The guard prevents a late
  automatic response from undoing a menu choice. Do not capture any event for
  either automatic or manual selection in this feature.

  If `fetchCountries` needs to complete independently of a slow IPWho request,
  use *two* controllers: leave the existing catalog controller unchanged and
  create the 2-second controller only immediately before `detectCountry`.
  This is the preferred final form: a slow IPWho response must never turn a
  successful `/countries` request into an error or hide the selector.

- [ ] **Step 4: Run the full frontend suite and production build**

  Run: `just test-web && just build-web`

  Expected: all Vitest suites PASS and the production frontend build completes.

- [ ] **Step 5: Commit App integration**

  ```bash
  git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/App.analytics.test.tsx
  git commit -m "feat: select initial country from IP geolocation"
  ```

### Task 4: Disclose the behavior and document the data-file operation

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts:30-34, 118-122, 206-210`
- Modify: `frontend/src/lib/i18n/i18n.test.tsx:25-31`
- Modify: `AGENTS.md:Data layout section`

**Interfaces:**
- Produces: translated `aboutPrivacy` text that discloses IPWho receives the
  visitor IP once to choose only the initial country, and that the result is not
  stored or used for analytics.
- Produces: operator documentation for `data/<country>/country_code`.

- [ ] **Step 1: Write failing disclosure and parity assertions**

  Extend `discloses cookieless analytics in every language` so all translations
  still mention no cookies and now name IPWho. For English, make the exact
  assertion readable to users:

  ```ts
  expect(STRINGS.en.aboutPrivacy).toContain("IPWho");
  expect(STRINGS.en.aboutPrivacy).toMatch(/country/i);
  expect(STRINGS.en.aboutPrivacy).toMatch(/not stored/i);
  ```

- [ ] **Step 2: Run the i18n test to verify it fails**

  Run: `cd frontend && npm test -- src/lib/i18n/i18n.test.tsx`

  Expected: FAIL because the current privacy copy has no IPWho disclosure.

- [ ] **Step 3: Update the three translations and operational layout docs**

  Replace only `aboutPrivacy` in each catalog with equivalent, plain-language
  disclosure. Use these English words as the source meaning:

  ```ts
  aboutPrivacy:
    "We collect anonymous usage stats to improve the tool. No cookies, no tracking across visits. On a first visit, IPWho receives your IP address once to choose an initial country; it returns only the country, and we do not store or analyse that result.",
  ```

  Use faithful Catalan and Spanish translations that explicitly retain all four
  facts: no cookies/cross-visit tracking, one first-visit request, IPWho gets
  the IP only to return country, and the result is neither stored nor analysed.
  Keep all three catalogs’ keys identical.

  In `AGENTS.md`’s data layout tree, add:

  ```text
  data/<country>/country_code                         ISO 3166-1 alpha-2 code for automatic initial-country selection
  ```

  Add one sentence after the tree: a missing or invalid code preserves manual
  availability but excludes the country from IP-based automatic selection.

- [ ] **Step 4: Run final repository verification**

  Run: `just check && just test && just test-web && just build-web`

  Expected: lint, strict mypy, Vulture, backend tests, frontend tests, and the
  production frontend build all PASS.

- [ ] **Step 5: Commit disclosure and documentation**

  ```bash
  git add frontend/src/lib/i18n/strings.ts frontend/src/lib/i18n/i18n.test.tsx AGENTS.md
  git commit -m "docs: disclose automatic country selection"
  ```

### Task 5: Provision country metadata in deployed data

**Files:**
- Create at deployment time: `data/spain/country_code`
- Create at deployment time for every supported country: `data/<country>/country_code`

**Interfaces:**
- Consumes: one uppercase ISO alpha-2 code per country.
- Produces: country entries eligible for automatic selection through Task 1.

- [ ] **Step 1: List the currently deployed country directories**

  Run: `find data -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort`

  Expected: one line per country data partition, including `spain`.

- [ ] **Step 2: Create one validated file per listed country**

  Use the explicit code appropriate to each directory, for example:

  ```bash
  printf 'ES\n' > data/spain/country_code
  printf 'FR\n' > data/france/country_code
  printf 'IT\n' > data/italy/country_code
  printf 'GB\n' > data/united_kingdom/country_code
  ```

  Do not create a file for a country unless its directory is actually present;
  do not commit these files because `data/` is gitignored derived/deployment
  data.

- [ ] **Step 3: Verify the running catalog includes provisioned codes**

  Run: `uv run python -c 'from fastapi.testclient import TestClient; from highliner.server.app import create_app; print(TestClient(create_app()).get("/countries").json())'`

  Expected: each provisioned country object contains its uppercase
  `country_code`; any intentionally unprovisioned country remains in the list
  without that key.

- [ ] **Step 4: Record deployment completion without committing data**

  Confirm `git status --short` does not include `data/` and retain the Task 4
  documentation as the durable operational instruction.

## Plan self-review

- **Spec coverage:** Task 1 covers the data file and optional API field; Task 2
  covers country-only IPWho validation and safe fallbacks; Task 3 covers saved
  preference precedence, one-time transient auto selection, timeout, manual
  race protection, and analytics silence; Task 4 covers privacy disclosure and
  documentation; Task 5 covers actual data provisioning. Language behavior is
  explicitly left unchanged throughout.
- **Placeholder scan:** No deferred implementation, unspecified error handling,
  or unbound interface names remain. Commands and code-bearing steps name exact
  files and expected outcomes.
- **Type consistency:** `CountryEntry.country_code?: string` is optional in the
  TypeScript API contract, `CountryEntry.country_code: str | None` is optional
  in Python, and `detectCountry` consumes that optional field and returns a
  country ID or `null` in every caller.
