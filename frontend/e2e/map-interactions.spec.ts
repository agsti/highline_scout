import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("lang", "en"));
});

test("map interactions", async ({ page }) => {
  const initialDensityResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/density" && response.status() === 200;
  });
  await page.goto("/?lat=41.59&lng=1.83&z=12");
  await page.getByRole("button", { name: "I understand" }).click();

  await initialDensityResponse;
  await expect(page.locator(".leaflet-overlay-pane path")).toHaveCount(1);

  const zonesResponse = page.waitForResponse((response) =>
    response.url().includes("/zones?") && response.status() === 200,
  );
  await page.getByRole("button", { name: "Zoom in" }).click();
  await zonesResponse;
  await expect(page.locator(".leaflet-overlay-pane path")).toHaveCount(2);

  const exposureThumb = page.getByRole("slider").nth(2);
  await exposureThumb.focus();
  await exposureThumb.press("End");
  for (let step = 0; step < 230; step += 1) {
    await exposureThumb.press("ArrowLeft");
  }

  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/zones" && url.searchParams.get("min_exposure") === "70";
  });
  await page.getByRole("button", { name: "Apply filters" }).click();
  await filteredResponse;
  await expect(page.locator(".leaflet-overlay-pane path")).toHaveCount(1);

  const densityResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/density"
      && response.status() === 200,
  );
  await page.getByRole("button", { name: "Zoom out" }).click();
  await densityResponse;
  await expect(page.locator(".leaflet-overlay-pane path")).toHaveCount(1);
});
