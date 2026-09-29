import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Str0ng!Passw0rd9";

export function uniqueEmail(tag: string) {
  return `e2e-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

/** Registers a fresh workspace admin and logs in. Fresh admins land on the
 *  onboarding wizard by design; pass skipOnboarding=false to stay there. */
export async function registerAndLogin(
  page: Page, email: string, name: string, { skipOnboarding = true } = {}
) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Company name").fill(`${name} Realty`);
  await page.getByLabel("Email").fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Email").fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();

  // New workspace admins are routed to setup first.
  await expect(page).toHaveURL(/\/onboarding/);
  if (skipOnboarding) {
    await page.getByText("Skip for now").click();
    await expect(page).toHaveURL(/\/dashboard/);
  }
}
