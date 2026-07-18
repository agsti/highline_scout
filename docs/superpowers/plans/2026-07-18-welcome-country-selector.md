# Welcome Country Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the app's live, persistent country selector in the blocking welcome dialog while keeping it available in the navigation menu.

**Architecture:** Extract the existing country control into a shared `CountrySelect` component, then render that component from both `NavMenu` and `SafetyDisclaimerDialog` with unique control ids. `App` remains the sole owner of the catalog, active country, and persistence callback and passes the same values into both surfaces.

**Tech Stack:** React 18, TypeScript, Radix Select, Tailwind CSS, Vitest, Testing Library, Vite

## Global Constraints

- Place the welcome selector between the safety list and acknowledgement button.
- A welcome selection immediately marks the choice as manual, saves it, and updates the active map country through the existing `handleCountryChange` path.
- Keep the navigation selector available after the welcome dialog closes.
- Use unique DOM ids for the welcome and navigation controls.
- Disable the selector while the country catalog is empty.
- Continue displaying the country ids supplied by the backend catalog.
- Add no translation keys and emit no country-selection analytics events.
- Preserve the modal focus trap, inert background, body scroll lock, hidden close control, and Escape/outside-click prevention.
- Keep the acknowledgement button as the welcome dialog's only close path.

---

### Task 1: Share the country selector with the welcome dialog

**Files:**
- Create: `frontend/src/components/CountrySelect.tsx`
- Modify: `frontend/src/components/NavMenu.tsx`
- Modify: `frontend/src/components/SafetyDisclaimerDialog.tsx`
- Test: `frontend/src/components/SafetyDisclaimerDialog.test.tsx`

**Interfaces:**
- Consumes: `CountryEntry[]`, the active country id, and `(country: string) => void`.
- Produces: `CountrySelect({ controlId, countries, country, onCountryChange }): JSX.Element` and optional welcome-dialog props that forward the same catalog state.

- [ ] **Step 1: Add failing welcome-dialog rendering coverage**

Add this type import and catalog near the imports in
`frontend/src/components/SafetyDisclaimerDialog.test.tsx`:

```tsx
import type { CountryEntry } from "@/types/highliner";

const countries: CountryEntry[] = [
  { id: "spain", country_code: "ES", bounds_lonlat: [-9, 36, 4, 44] },
  { id: "france", country_code: "FR", bounds_lonlat: [-5, 42, 8, 51] },
];
```

Add these tests inside the existing `describe("SafetyDisclaimerDialog", ...)` block:

```tsx
it("shows the active country and available countries", async () => {
  const user = userEvent.setup();
  window.localStorage.setItem("lang", "en");

  render(
    <I18nProvider>
      <SafetyDisclaimerDialog
        open
        onAccept={vi.fn()}
        countries={countries}
        country="spain"
        onCountryChange={vi.fn()}
      />
    </I18nProvider>,
  );

  const selector = screen.getByRole("combobox", { name: "Country" });
  expect(selector).toHaveTextContent("spain");

  await user.click(selector);
  expect(screen.getByRole("option", { name: "spain" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "france" })).toBeInTheDocument();
});

it("reports a country selected from the welcome dialog", async () => {
  const user = userEvent.setup();
  const onCountryChange = vi.fn();
  window.localStorage.setItem("lang", "en");

  render(
    <I18nProvider>
      <SafetyDisclaimerDialog
        open
        onAccept={vi.fn()}
        countries={countries}
        country="spain"
        onCountryChange={onCountryChange}
      />
    </I18nProvider>,
  );

  await user.click(screen.getByRole("combobox", { name: "Country" }));
  await user.click(screen.getByRole("option", { name: "france" }));

  expect(onCountryChange).toHaveBeenCalledOnce();
  expect(onCountryChange).toHaveBeenCalledWith("france");
});

it("disables country selection while the catalog is loading", () => {
  window.localStorage.setItem("lang", "en");

  render(
    <I18nProvider>
      <SafetyDisclaimerDialog
        open
        onAccept={vi.fn()}
        countries={[]}
        country="spain"
        onCountryChange={vi.fn()}
      />
    </I18nProvider>,
  );

  expect(screen.getByRole("combobox", { name: "Country" })).toBeDisabled();
});
```

- [ ] **Step 2: Run the focused test and verify the missing behavior**

Run:

```bash
cd frontend && npm test -- src/components/SafetyDisclaimerDialog.test.tsx
```

Expected: FAIL because the welcome dialog does not render a combobox named `Country`.

- [ ] **Step 3: Create the shared country control**

Create `frontend/src/components/CountrySelect.tsx`:

```tsx
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import type { CountryEntry } from "@/types/highliner";

interface CountrySelectProps {
  controlId: string;
  countries: CountryEntry[];
  country: string;
  onCountryChange: (country: string) => void;
}

export function CountrySelect({
  controlId,
  countries,
  country,
  onCountryChange,
}: CountrySelectProps) {
  const { t } = useI18n();

  return (
    <div>
      <label
        htmlFor={controlId}
        className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground"
      >
        {t("country")}
      </label>
      <Select
        value={country}
        onValueChange={onCountryChange}
        disabled={countries.length === 0}
      >
        <SelectTrigger
          id={controlId}
          aria-label={t("country")}
          className="mt-1.5 h-8"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {countries.map((entry) => (
            <SelectItem key={entry.id} value={entry.id}>
              {entry.id}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
```

- [ ] **Step 4: Replace the navigation's inline selector**

In `frontend/src/components/NavMenu.tsx`, remove `Select`, `SelectContent`,
`SelectItem`, `SelectTrigger`, and `SelectValue` from the UI imports. Add:

```tsx
import { CountrySelect } from "./CountrySelect";
```

Replace the current country label and `Select` inside its padded wrapper with:

```tsx
<CountrySelect
  controlId="nav-country"
  countries={countries}
  country={country}
  onCountryChange={onCountryChange}
/>
```

Keep the existing `<div className="px-3.5 py-2.5">` wrapper around it.

- [ ] **Step 5: Render the shared selector in the welcome dialog**

In `frontend/src/components/SafetyDisclaimerDialog.tsx`, add imports:

```tsx
import type { CountryEntry } from "@/types/highliner";
import { CountrySelect } from "./CountrySelect";
```

Extend the props and defaults without forcing unrelated component tests to
repeat catalog setup:

```tsx
interface SafetyDisclaimerDialogProps {
  open: boolean;
  onAccept: () => void;
  countries?: CountryEntry[];
  country?: string;
  onCountryChange?: (country: string) => void;
}

export function SafetyDisclaimerDialog({
  open,
  onAccept,
  countries = [],
  country = "spain",
  onCountryChange = () => {},
}: SafetyDisclaimerDialogProps) {
```

Insert this between the closing `</ul>` and the acknowledgement `<Button>`:

```tsx
<CountrySelect
  controlId="welcome-country"
  countries={countries}
  country={country}
  onCountryChange={onCountryChange}
/>
```

Do not alter the surrounding dialog content, dismissal handlers, or button.

- [ ] **Step 6: Run focused component and navigation tests**

Run:

```bash
cd frontend && npm test -- \
  src/components/SafetyDisclaimerDialog.test.tsx \
  src/components/NavMenu.test.tsx \
  src/components/FloatingNav.test.tsx
```

Expected: all three test files PASS, including the new welcome selector cases.

- [ ] **Step 7: Commit the shared UI**

```bash
git add frontend/src/components/CountrySelect.tsx \
  frontend/src/components/NavMenu.tsx \
  frontend/src/components/SafetyDisclaimerDialog.tsx \
  frontend/src/components/SafetyDisclaimerDialog.test.tsx
git commit -m "feat: show country selector in welcome dialog"
```

---

### Task 2: Wire welcome selection through App state and persistence

**Files:**
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `SafetyDisclaimerDialog` props `countries`, `country`, and `onCountryChange` from Task 1.
- Produces: welcome selections routed through the existing `handleCountryChange(next: string): void` callback.

- [ ] **Step 1: Make the App test double expose welcome country props**

Replace the `SafetyDisclaimerDialog` mock in `frontend/src/App.test.tsx` with:

```tsx
vi.mock("./components/SafetyDisclaimerDialog", () => ({
  SafetyDisclaimerDialog: ({
    countries = [],
    country = "missing",
    onCountryChange = () => {},
  }: {
    countries?: Array<{ id: string }>;
    country?: string;
    onCountryChange?: (country: string) => void;
  }) => (
    <div>
      <span data-testid="welcome-country">
        {country}:{countries.map((entry) => entry.id).join(",")}
      </span>
      <button type="button" onClick={() => onCountryChange("france")}>
        choose France
      </button>
    </div>
  ),
}));
```

- [ ] **Step 2: Add a failing App integration test**

Add this test after the existing saved-country test in `frontend/src/App.test.tsx`:

```tsx
it("persists and applies a country chosen in the welcome dialog", async () => {
  const user = userEvent.setup();
  apiMocks.fetchCountries.mockResolvedValueOnce([
    { id: "spain", country_code: "ES", bounds_lonlat: [-9, 36, 4, 44] },
    { id: "france", country_code: "FR", bounds_lonlat: [-5, 42, 8, 51] },
  ]);

  renderApp();

  await waitFor(() => {
    expect(screen.getByTestId("welcome-country")).toHaveTextContent(
      "spain:spain,france",
    );
  });
  await user.click(screen.getByRole("button", { name: "choose France" }));

  expect(countryMocks.saveCountry).toHaveBeenCalledOnce();
  expect(countryMocks.saveCountry).toHaveBeenCalledWith("france");
  await waitFor(() => expect(lastMapProps().country).toBe("france"));
});
```

- [ ] **Step 3: Run the App test and verify the props are absent**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx
```

Expected: FAIL because `welcome-country` contains `missing:` instead of the
App-owned country and catalog.

- [ ] **Step 4: Pass App-owned country state into the welcome dialog**

Replace the current `SafetyDisclaimerDialog` call at the bottom of
`frontend/src/App.tsx` with:

```tsx
<SafetyDisclaimerDialog
  open={disclaimerOpen}
  onAccept={() => setDisclaimerOpen(false)}
  countries={countries}
  country={country}
  onCountryChange={handleCountryChange}
/>
```

Do not add another handler, persistence call, effect, or analytics event.

- [ ] **Step 5: Run the focused App and dialog tests**

Run:

```bash
cd frontend && npm test -- \
  src/App.test.tsx \
  src/components/SafetyDisclaimerDialog.test.tsx
```

Expected: both test files PASS. The App test must show that the modal receives
the loaded catalog, calls `saveCountry("france")`, and updates the map country.

- [ ] **Step 6: Run full frontend verification**

Run:

```bash
just test-web
just build-web
```

Expected: the complete Vitest suite passes and the TypeScript/Vite production
build succeeds without errors.

- [ ] **Step 7: Inspect the final diff**

Run:

```bash
git diff --check
git diff --stat HEAD~1
```

Expected: no whitespace errors; changes are limited to the selector component,
welcome and navigation consumers, App wiring, and their tests.

- [ ] **Step 8: Commit App wiring**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: apply welcome country selection"
```
