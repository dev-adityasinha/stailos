import { expect, test, type Page } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

function uniqueSlug(tag: string) {
  return `e2e-${tag}-${Date.now()}`;
}

async function createAndPublishEvent(page: Page, name: string, slug: string) {
  await page.goto("/events");
  await page.getByRole("button", { name: /new event/i }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Public URL slug").fill(slug);
  await page.getByLabel("Venue").fill("Test Venue");
  await page.locator('input[type="datetime-local"]').nth(0).fill("2026-09-10T10:00");
  await page.locator('input[type="datetime-local"]').nth(1).fill("2026-09-10T13:00");
  await page.getByRole("button", { name: /create event/i }).click();

  await page.getByText(name).click();
  await expect(page).toHaveURL(/\/events\/manage\/.+/);

  await page.locator("select").selectOption("published");
  await page.getByRole("button", { name: /save changes/i }).click();
  await expect(page.getByText("Saved")).toBeVisible({ timeout: 5_000 });
}

test.describe("Events", () => {
  test("admin creates and publishes an event, a visitor registers publicly", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("events-admin"), "E2E Events Admin");

    const eventName = `Playwright Summit ${Date.now()}`;
    const slug = uniqueSlug("summit");
    await createAndPublishEvent(page, eventName, slug);

    // Public landing page — no auth, fresh navigation.
    await page.goto(`/events/${slug}`);
    await expect(page.getByRole("heading", { name: eventName })).toBeVisible();

    await page.fill('input[placeholder="Full name"]', "Visitor Investor");
    await page.fill('input[placeholder="Email"]', uniqueEmail("visitor"));
    await page.fill('input[placeholder="Phone (for WhatsApp confirmation)"]', "9876543210");
    await page.getByRole("button", { name: /register now/i }).click();

    await page.waitForURL("**/confirmation", { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: /you're registered/i })).toBeVisible();
    await expect(page.getByAltText("Your check-in QR code")).toBeVisible();

    // Back in the admin dashboard, the registration must show up.
    await page.goto("/events");
    await page.getByText(eventName).click();
    await page.getByRole("button", { name: /^registrations$/i }).click();
    await expect(page.getByText("Visitor Investor")).toBeVisible();
  });

  test("event with speakers renders them on the public page", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("events-admin2"), "E2E Events Admin 2");

    const eventName = `Speaker Summit ${Date.now()}`;
    const slug = uniqueSlug("speakers");
    await createAndPublishEvent(page, eventName, slug);

    const speakerForm = page.locator('form:has(input[placeholder="Name"])');
    await speakerForm.getByPlaceholder("Name").fill("Aditya Rao");
    await speakerForm.getByPlaceholder("Title").fill("Chief Investment Officer");
    await speakerForm.locator('button[type="submit"]').click();
    await expect(page.getByText("Aditya Rao")).toBeVisible();

    await page.goto(`/events/${slug}`);
    await expect(page.getByText("Aditya Rao")).toBeVisible();
    await expect(page.getByText("Chief Investment Officer")).toBeVisible();
  });
});
